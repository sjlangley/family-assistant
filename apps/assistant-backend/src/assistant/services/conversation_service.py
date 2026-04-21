import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from typing import AsyncGenerator, cast
import uuid

from fastapi import BackgroundTasks, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.constants import MAXIMUM_TOOL_ROUNDS, SYSTEM_PROMPT
from assistant.models.annotations import AssistantAnnotations
from assistant.models.conversation import (
    ConversationSummary,
    ConversationWithMessagesResponse,
    CreateConversationWithMessageRequest,
    CreateMessageRequest,
    GetConversationMessagesResponse,
    ListConversationsResponse,
    MessageRead,
)
from assistant.models.conversation_sql import Conversation, Message
from assistant.models.llm import (
    ChatCompletionMessageToolCall,
    ChatCompletionRequestSystemMessage,
    LLMCompletionError,
    LLMCompletionErrorKind,
    ToolChoice,
)
from assistant.models.tool import ToolExecutionResult
from assistant.routers.web_utils import llm_completion_error_to_http_exception
from assistant.services.assistant_annotations import (
    AssistantAnnotationService,
)
from assistant.services.context_assembly import ContextAssemblyService
from assistant.services.llm_service import LLMService
from assistant.services.memory_storage import MemoryStorage
from assistant.services.tool_service import ToolService
from assistant.services.tools.errors import UnsupportedToolError
from assistant.services.tools.factory import DisabledToolError
from assistant.settings import settings
from assistant.utils.sse import SSEEncoder

logger = logging.getLogger(__name__)


@dataclass
class _LLMLoopResult:
    """Internal result from the LLM tool loop.

    Wraps the final assistant response along with tool execution history
    for annotation building and error tracking.
    """

    content: str
    executed_tools: list[ToolExecutionResult]
    error: LLMCompletionError | None = None
    attempted_tool_execution: bool = False  # True if tool loop was entered
    finish_reason: str | None = None


def conversation_title_from_first_message(content: str) -> str:
    title = content.strip()
    return title[:60] or 'New chat'


class ConversationService:
    def __init__(
        self,
        llm_service: LLMService,
        context_assembly: ContextAssemblyService,
        tool_service: ToolService,
        annotation_service: AssistantAnnotationService | None = None,
        memory_storage: MemoryStorage | None = None,
    ) -> None:
        self.llm_service = llm_service
        self.context_assembly = context_assembly
        self.tool_service = tool_service
        self.annotation_service = (
            annotation_service or AssistantAnnotationService()
        )
        self.memory_storage = memory_storage

    async def list_conversations(
        self,
        session: AsyncSession,
        *,
        user_id: str,
    ) -> ListConversationsResponse:
        stmt = (
            select(Conversation)
            # pyrefly: ignore [bad-argument-type]
            .where(Conversation.user_id == user_id)
            # pyrefly: ignore [missing-attribute]
            .order_by(Conversation.updated_at.desc())
        )
        result = await session.execute(stmt)
        conversations = list(result.scalars().all())

        return ListConversationsResponse(
            items=[self._conversation_summary(c) for c in conversations]
        )

    async def get_conversation_messages(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        conversation_id: uuid.UUID,
    ) -> GetConversationMessagesResponse:
        conversation = await self._get_conversation_for_user(
            session,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        messages = await self._get_messages_for_conversation(
            session,
            conversation_id=conversation_id,
        )

        return GetConversationMessagesResponse(
            conversation=self._conversation_summary(conversation),
            items=[self._message_read(m) for m in messages],
        )

    async def create_conversation_with_message(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        payload: CreateConversationWithMessageRequest,
        background_tasks: BackgroundTasks | None = None,
    ) -> ConversationWithMessagesResponse:
        content = payload.content.strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Message content cannot be empty',
            )

        # Transaction 1: Create conversation and user message
        conversation = Conversation(
            user_id=user_id,
            title=conversation_title_from_first_message(content),
        )
        session.add(conversation)
        await session.flush()

        user_message = Message(
            conversation_id=conversation.id,
            role='user',
            content=content,
            sequence_number=1,
        )
        session.add(user_message)
        await session.commit()
        await session.refresh(conversation)
        await session.refresh(user_message)

        conversation_id = conversation.id

        # Assemble context for new conversation (includes facts if any)
        context_result = (
            await self.context_assembly.assemble_context_new_conversation(
                session,
                user_id=user_id,
                user_message=content,
            )
        )

        max_tokens = payload.max_tokens or settings.llm_max_tokens

        # Make LLM call outside of transaction
        loop_result = await self._call_llm_chat_completion(
            messages=context_result.messages,
            temperature=payload.temperature,
            max_tokens=max_tokens,
        )

        # Build annotations or failure metadata
        annotations_dict = None
        error_text = None
        if loop_result.error:
            annotations_obj = self.annotation_service.build_failure_annotations(
                error=loop_result.error,
                executed_tools=loop_result.executed_tools,
                attempted_tool_execution=loop_result.attempted_tool_execution,
            )
            if loop_result.finish_reason:
                annotations_obj.finish_reason = loop_result.finish_reason
            annotations_dict = annotations_obj.model_dump()
            error_text = self.annotation_service.format_error_detail(
                loop_result.error
            )
        else:
            annotations_obj = self.annotation_service.build_success_annotations(
                executed_tools=loop_result.executed_tools,
                fact_ids=context_result.fact_ids,
            )
            if loop_result.finish_reason:
                annotations_obj.finish_reason = loop_result.finish_reason
            annotations_dict = annotations_obj.model_dump()

        # Transaction 2: Create assistant message and update conversation
        assistant_message = Message(
            conversation_id=conversation_id,
            role='assistant',
            content=loop_result.content
            or ('Unable to generate a response. Please try again.'),
            sequence_number=2,
            error=error_text,
            annotations=annotations_dict,
        )
        session.add(assistant_message)

        # Update conversation's updated_at timestamp
        await session.execute(
            update(Conversation)
            # pyrefly: ignore [bad-argument-type]
            .where(Conversation.id == conversation_id)
            .values(updated_at=func.now())
        )

        await session.commit()
        await session.refresh(conversation)
        await session.refresh(user_message)
        await session.refresh(assistant_message)

        # Schedule background extraction only on successful completion
        # (no terminal LLM/tool error)
        if not loop_result.error and background_tasks and self.memory_storage:
            background_tasks.add_task(
                self.extract_and_save_background,
                user_id=user_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message.id,
                latest_user_message_id=user_message.id,
            )

        # If there was a terminal error, raise HTTP exception after persisting
        if loop_result.error:
            raise llm_completion_error_to_http_exception(loop_result.error)

        return ConversationWithMessagesResponse(
            conversation=self._conversation_summary(conversation),
            user_message=self._message_read(user_message),
            assistant_message=self._message_read(assistant_message),
        )

    async def add_message_to_conversation(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        conversation_id: uuid.UUID,
        payload: CreateMessageRequest,
        background_tasks=None,
    ) -> ConversationWithMessagesResponse:
        content = payload.content.strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Message content cannot be empty',
            )

        # Transaction 1: Create user message
        conversation = await self._get_conversation_for_user(
            session,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        existing_messages = await self._get_messages_for_conversation(
            session,
            conversation_id=conversation_id,
        )

        next_seq = (
            1
            if not existing_messages
            else existing_messages[-1].sequence_number + 1
        )

        user_message = Message(
            conversation_id=conversation_id,
            role='user',
            content=content,
            sequence_number=next_seq,
        )
        session.add(user_message)
        await session.commit()
        await session.refresh(user_message)

        # Assemble context using summary, facts, and recent turns
        # Note: new_user_message=None because it's already in the DB
        context_result = await self.context_assembly.assemble_context(
            session,
            user_id=user_id,
            conversation_id=conversation_id,
            new_user_message=None,
        )

        max_tokens = payload.max_tokens or settings.llm_max_tokens

        # Make LLM call outside of transaction
        loop_result = await self._call_llm_chat_completion(
            messages=context_result.messages,
            temperature=payload.temperature,
            max_tokens=max_tokens,
        )

        # Build annotations or failure metadata
        annotations_dict = None
        error_text = None
        if loop_result.error:
            annotations_obj = self.annotation_service.build_failure_annotations(
                error=loop_result.error,
                executed_tools=loop_result.executed_tools,
                attempted_tool_execution=loop_result.attempted_tool_execution,
            )
            if loop_result.finish_reason:
                annotations_obj.finish_reason = loop_result.finish_reason
            annotations_dict = annotations_obj.model_dump()
            error_text = self.annotation_service.format_error_detail(
                loop_result.error
            )
        else:
            annotations_obj = self.annotation_service.build_success_annotations(
                executed_tools=loop_result.executed_tools,
                fact_ids=context_result.fact_ids,
            )
            if loop_result.finish_reason:
                annotations_obj.finish_reason = loop_result.finish_reason
            annotations_dict = annotations_obj.model_dump()

        # Transaction 2: Create assistant message and update conversation
        assistant_message = Message(
            conversation_id=conversation_id,
            role='assistant',
            content=loop_result.content
            or ('Unable to generate a response. Please try again.'),
            sequence_number=next_seq + 1,
            error=error_text,
            annotations=annotations_dict,
        )
        session.add(assistant_message)

        await session.execute(
            update(Conversation)
            # pyrefly: ignore [bad-argument-type]
            .where(Conversation.id == conversation_id)
            .values(updated_at=func.now())
        )

        await session.commit()
        await session.refresh(conversation)
        await session.refresh(user_message)
        await session.refresh(assistant_message)

        # Schedule background extraction only on successful completion
        # (no terminal LLM/tool error)
        if not loop_result.error and background_tasks and self.memory_storage:
            background_tasks.add_task(
                self.extract_and_save_background,
                user_id=user_id,
                conversation_id=conversation_id,
                assistant_message_id=assistant_message.id,
                latest_user_message_id=user_message.id,
            )

        # If there was a terminal error, raise HTTP exception after persisting
        if loop_result.error:
            raise llm_completion_error_to_http_exception(loop_result.error)

        return ConversationWithMessagesResponse(
            conversation=self._conversation_summary(conversation),
            user_message=self._message_read(user_message),
            assistant_message=self._message_read(assistant_message),
        )

    async def create_conversation_with_message_stream(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        payload: CreateConversationWithMessageRequest,
        background_tasks: BackgroundTasks | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream assistant response while persisting lifecycle in two phases.

        Phase 1 (immediate): persist conversation + user message.
        Phase 2 (deferred): persist assistant message only on terminal success,
        or terminal failure if output has already started.
        """
        content = payload.content.strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Message content cannot be empty',
            )

        conversation = Conversation(
            user_id=user_id,
            title=conversation_title_from_first_message(content),
        )
        session.add(conversation)
        await session.flush()

        user_message = Message(
            conversation_id=conversation.id,
            role='user',
            content=content,
            sequence_number=1,
        )
        session.add(user_message)
        await session.commit()
        await session.refresh(user_message)

        context_result = (
            await self.context_assembly.assemble_context_new_conversation(
                session,
                user_id=user_id,
                user_message=content,
            )
        )

        max_tokens = payload.max_tokens or settings.llm_max_tokens

        async for event in self._stream_assistant_lifecycle(
            session=session,
            user_id=user_id,
            conversation=conversation,
            user_message_id=user_message.id,
            assistant_sequence_number=2,
            context_messages=context_result.messages,
            fact_ids=context_result.fact_ids,
            temperature=payload.temperature,
            max_tokens=max_tokens,
            background_tasks=background_tasks,
        ):
            yield event

    async def add_message_to_conversation_stream(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        conversation_id: uuid.UUID,
        payload: CreateMessageRequest,
        background_tasks: BackgroundTasks | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream assistant response for an existing conversation lifecycle."""
        content = payload.content.strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Message content cannot be empty',
            )

        conversation = await self._get_conversation_for_user(
            session,
            user_id=user_id,
            conversation_id=conversation_id,
        )

        existing_messages = await self._get_messages_for_conversation(
            session,
            conversation_id=conversation_id,
        )
        next_seq = (
            1
            if not existing_messages
            else existing_messages[-1].sequence_number + 1
        )

        user_message = Message(
            conversation_id=conversation_id,
            role='user',
            content=content,
            sequence_number=next_seq,
        )
        session.add(user_message)
        await session.commit()
        await session.refresh(user_message)

        context_result = await self.context_assembly.assemble_context(
            session,
            user_id=user_id,
            conversation_id=conversation_id,
            new_user_message=None,
        )

        max_tokens = payload.max_tokens or settings.llm_max_tokens

        async for event in self._stream_assistant_lifecycle(
            session=session,
            user_id=user_id,
            conversation=conversation,
            user_message_id=user_message.id,
            assistant_sequence_number=next_seq + 1,
            context_messages=context_result.messages,
            fact_ids=context_result.fact_ids,
            temperature=payload.temperature,
            max_tokens=max_tokens,
            background_tasks=background_tasks,
        ):
            yield event

    async def _stream_assistant_lifecycle(
        self,
        *,
        session: AsyncSession,
        user_id: str,
        conversation: Conversation,
        user_message_id: uuid.UUID,
        assistant_sequence_number: int,
        context_messages: list[dict],
        fact_ids: list[uuid.UUID],
        temperature: float,
        max_tokens: int | None,
        background_tasks: BackgroundTasks | None = None,
    ) -> AsyncGenerator[str, None]:
        """Run streaming loop and persist assistant row only at terminal states."""
        logger.debug(
            'stream lifecycle start: conversation_id=%s user_message_id=%s seq=%s',
            conversation.id,
            user_message_id,
            assistant_sequence_number,
        )
        content_parts: list[str] = []
        thought_parts: list[str] = []
        executed_tools: list[ToolExecutionResult] = []
        attempted_tool_execution = False
        model_name: str | None = None
        usage_payload: dict | None = None
        finish_reason: str | None = None
        stream_started = False
        emitted_tokens = 0
        emitted_thoughts = 0
        emitted_tool_calls = 0

        try:
            async for event in self._call_llm_chat_completion_stream(
                messages=context_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                event_type = event['type']
                if event_type == 'thought':
                    thought = cast(str, event['data'])
                    thought_parts.append(thought)
                    stream_started = True
                    emitted_thoughts += 1
                    yield SSEEncoder.encode('thought', thought)
                    continue

                if event_type == 'token':
                    token = cast(str, event['data'])
                    content_parts.append(token)
                    stream_started = True
                    emitted_tokens += 1
                    yield SSEEncoder.encode('token', token)
                    continue

                if event_type == 'tool_call':
                    stream_started = True
                    attempted_tool_execution = True
                    emitted_tool_calls += 1
                    yield SSEEncoder.encode('tool_call', event['data'])
                    continue

                if event_type == 'meta':
                    if event['data'].get('model') is not None:
                        model_name = cast(str, event['data']['model'])
                    usage = event['data'].get('usage')
                    if usage is not None:
                        usage_payload = cast(dict, usage)
                    executed_tools = cast(
                        list[ToolExecutionResult],
                        event['data']['executed_tools'],
                    )
                    attempted_tool_execution = cast(
                        bool, event['data']['attempted_tool_execution']
                    )
                    if event['data'].get('finish_reason') is not None:
                        finish_reason = cast(
                            str, event['data']['finish_reason']
                        )

        except LLMCompletionError as error:
            logger.debug(
                'stream lifecycle llm error: conversation_id=%s stream_started=%s token_events=%s thought_events=%s tool_call_events=%s kind=%s detail=%s',
                conversation.id,
                stream_started,
                emitted_tokens,
                emitted_thoughts,
                emitted_tool_calls,
                error.kind.value,
                error.message,
            )
            if stream_started:
                await self._persist_streaming_assistant_message(
                    session=session,
                    conversation=conversation,
                    sequence_number=assistant_sequence_number,
                    content=''.join(content_parts)
                    or 'Unable to generate a response. Please try again.',
                    thought=''.join(thought_parts) or None,
                    fact_ids=fact_ids,
                    executed_tools=executed_tools,
                    attempted_tool_execution=attempted_tool_execution,
                    error=error,
                    finish_reason=None,
                )

            yield SSEEncoder.encode(
                'error',
                {
                    'detail': self.annotation_service.format_error_detail(
                        error
                    ),
                    'kind': error.kind.value,
                },
            )
            return

        except asyncio.CancelledError:
            logger.debug(
                'stream lifecycle cancelled: conversation_id=%s stream_started=%s token_events=%s thought_events=%s tool_call_events=%s',
                conversation.id,
                stream_started,
                emitted_tokens,
                emitted_thoughts,
                emitted_tool_calls,
            )
            if stream_started:
                cancellation_error = LLMCompletionError(
                    kind=LLMCompletionErrorKind.backend_error,
                    message='Streaming response interrupted by client disconnect',
                )
                await self._persist_streaming_assistant_message(
                    session=session,
                    conversation=conversation,
                    sequence_number=assistant_sequence_number,
                    content=''.join(content_parts)
                    or 'Unable to generate a response. Please try again.',
                    thought=''.join(thought_parts) or None,
                    fact_ids=fact_ids,
                    executed_tools=executed_tools,
                    attempted_tool_execution=attempted_tool_execution,
                    error=cancellation_error,
                    finish_reason=None,
                )
            raise

        assistant_message = await self._persist_streaming_assistant_message(
            session=session,
            conversation=conversation,
            sequence_number=assistant_sequence_number,
            content=''.join(content_parts)
            or 'Unable to generate a response. Please try again.',
            thought=''.join(thought_parts) or None,
            fact_ids=fact_ids,
            executed_tools=executed_tools,
            attempted_tool_execution=attempted_tool_execution,
            error=None,
            finish_reason=finish_reason,
        )
        logger.debug(
            'stream lifecycle done: conversation_id=%s assistant_message_id=%s token_events=%s thought_events=%s tool_call_events=%s content_len=%s',
            conversation.id,
            assistant_message.id,
            emitted_tokens,
            emitted_thoughts,
            emitted_tool_calls,
            len(assistant_message.content or ''),
        )

        if background_tasks and self.memory_storage:
            background_tasks.add_task(
                self.extract_and_save_background,
                user_id=user_id,
                conversation_id=conversation.id,
                assistant_message_id=assistant_message.id,
                latest_user_message_id=user_message_id,
            )

        done_payload: dict[str, object] = {
            'conversation_id': str(conversation.id),
            'message_id': str(assistant_message.id),
            'content': assistant_message.content,
            'annotations': assistant_message.annotations,
        }
        if model_name:
            done_payload['model'] = model_name
        if usage_payload:
            done_payload['usage'] = usage_payload

        yield SSEEncoder.encode('done', done_payload)

    async def _persist_streaming_assistant_message(
        self,
        *,
        session: AsyncSession,
        conversation: Conversation,
        sequence_number: int,
        content: str,
        thought: str | None,
        fact_ids: list[uuid.UUID],
        executed_tools: list[ToolExecutionResult],
        attempted_tool_execution: bool,
        error: LLMCompletionError | None,
        finish_reason: str | None,
    ) -> Message:
        """Persist an assistant message row for terminal stream completion."""
        if error:
            annotations_obj = self.annotation_service.build_failure_annotations(
                error=error,
                executed_tools=executed_tools,
                attempted_tool_execution=attempted_tool_execution,
            )
            error_text = self.annotation_service.format_error_detail(error)
        else:
            annotations_obj = self.annotation_service.build_success_annotations(
                executed_tools=executed_tools,
                fact_ids=fact_ids,
            )
            error_text = None

        if thought:
            annotations_obj.thought = thought

        if finish_reason:
            annotations_obj.finish_reason = finish_reason

        assistant_message = Message(
            conversation_id=conversation.id,
            role='assistant',
            content=content,
            sequence_number=sequence_number,
            error=error_text,
            annotations=annotations_obj.model_dump(),
        )
        session.add(assistant_message)
        conversation.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(assistant_message)
        return assistant_message

    async def _get_conversation_for_user(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        conversation_id: uuid.UUID,
    ) -> Conversation:
        stmt = select(Conversation).where(
            # pyrefly: ignore [bad-argument-type]
            Conversation.id == conversation_id,
            # pyrefly: ignore [bad-argument-type]
            Conversation.user_id == user_id,
        )
        result = await session.execute(stmt)
        conversation = result.scalar_one_or_none()

        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Conversation not found',
            )

        return conversation

    async def _get_messages_for_conversation(
        self,
        session: AsyncSession,
        *,
        conversation_id: uuid.UUID,
    ) -> list[Message]:
        stmt = (
            select(Message)
            # pyrefly: ignore [bad-argument-type]
            .where(Message.conversation_id == conversation_id)
            # pyrefly: ignore [missing-attribute]
            .order_by(Message.sequence_number.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _call_llm_chat_completion(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int | None,
    ) -> _LLMLoopResult:
        """Call LLM completion and execute tools in a bounded loop.

        Returns a structured result with final content, executed tools,
        and any errors encountered. Does not raise HTTP exceptions for
        LLM/tool failures - those are handled at the persistence layer.
        """
        system_message = ChatCompletionRequestSystemMessage(
            role='system', content=SYSTEM_PROMPT
        )
        llm_messages = [system_message.model_dump()] + messages
        available_tools = self.tool_service.get_available_tools()
        tools = available_tools if available_tools else None

        executed_tools: list[ToolExecutionResult] = []
        attempted_tool_execution = False

        for _ in range(MAXIMUM_TOOL_ROUNDS):
            try:
                completion_kwargs = {
                    'messages': llm_messages,
                    'model': settings.llm_model,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                }
                if tools:
                    completion_kwargs['tools'] = [
                        tool.model_dump() for tool in tools
                    ]
                    completion_kwargs['tool_choice'] = ToolChoice.auto

                result = await self.llm_service.complete_messages(
                    **completion_kwargs
                )
                logger.debug(
                    'conversation llm turn complete: finish_reason=%s usage(prompt=%s completion=%s total=%s) tool_calls=%s',
                    result.finish_reason,
                    result.prompt_tokens,
                    result.completion_tokens,
                    result.total_tokens,
                    len(result.tool_calls or []),
                )
                if result.finish_reason == 'length':
                    logger.debug(
                        'conversation llm turn likely truncated: max_tokens=%s total_tokens=%s',
                        max_tokens,
                        result.total_tokens,
                    )

                # No tool calls - return final response
                if not result.tool_calls:
                    return _LLMLoopResult(
                        content=result.content,
                        executed_tools=executed_tools,
                        error=None,
                        attempted_tool_execution=attempted_tool_execution,
                        finish_reason=result.finish_reason,
                    )

                # Tool calls requested - mark as attempted and process
                attempted_tool_execution = True
                llm_messages.append(
                    {
                        'role': 'assistant',
                        'content': result.content,
                        'tool_calls': result.tool_calls,
                    }
                )

                for tool_call in result.tool_calls:
                    logger.debug(
                        'llm requested tool execution: name=%s tool_call_id=%s',
                        tool_call.function.name,
                        tool_call.id,
                    )
                    # Parse and validate tool arguments safely
                    try:
                        parsed_arguments = json.loads(
                            tool_call.function.arguments
                        )
                        # Validate parsed arguments are a dict
                        if not isinstance(parsed_arguments, dict):
                            raise ValueError(
                                f'Tool arguments must be a JSON object, '
                                f'got {type(parsed_arguments).__name__}'
                            )
                    except (json.JSONDecodeError, ValueError) as exc:
                        # Tool parsing error - return as terminal failure
                        error = LLMCompletionError(
                            kind=LLMCompletionErrorKind.invalid_response,
                            message=f'Unable to parse tool arguments for {tool_call.function.name}: {str(exc)}',
                        )
                        return _LLMLoopResult(
                            content='',
                            executed_tools=executed_tools,
                            error=error,
                            attempted_tool_execution=attempted_tool_execution,
                        )

                    try:
                        tool_result = await self.tool_service.execute_tool(
                            name=tool_call.function.name,
                            arguments=parsed_arguments,
                        )
                        executed_tools.append(tool_result)
                    except (UnsupportedToolError, DisabledToolError) as exc:
                        # Tool config error - deterministic, non-retryable
                        error = LLMCompletionError(
                            kind=LLMCompletionErrorKind.invalid_response,
                            message=f'Tool error: {str(exc)}',
                        )
                        return _LLMLoopResult(
                            content='',
                            executed_tools=executed_tools,
                            error=error,
                            attempted_tool_execution=attempted_tool_execution,
                        )
                    except Exception as exc:
                        # Other tool execution error - return as terminal failure
                        error = LLMCompletionError(
                            kind=LLMCompletionErrorKind.backend_error,
                            message=f'Error executing tool {tool_call.function.name}: {str(exc)}',
                        )
                        return _LLMLoopResult(
                            content='',
                            executed_tools=executed_tools,
                            error=error,
                            attempted_tool_execution=attempted_tool_execution,
                        )

                    llm_messages.append(
                        {
                            'role': 'tool',
                            'tool_call_id': tool_call.id,
                            'content': tool_result.llm_context or '',
                        }
                    )

            except LLMCompletionError as exc:
                # LLM service error - return as terminal failure
                return _LLMLoopResult(
                    content='',
                    executed_tools=executed_tools,
                    error=exc,
                    attempted_tool_execution=attempted_tool_execution,
                )

        # Exceeded tool rounds - return as terminal failure
        error = LLMCompletionError(
            kind=LLMCompletionErrorKind.backend_error,
            message=f'Assistant exceeded maximum tool rounds ({MAXIMUM_TOOL_ROUNDS})',
        )
        return _LLMLoopResult(
            content='',
            executed_tools=executed_tools,
            error=error,
            attempted_tool_execution=attempted_tool_execution,
        )

    async def _call_llm_chat_completion_stream(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int | None,
    ) -> AsyncGenerator[dict, None]:
        """Call streaming completion seam, executing tools between stream rounds."""
        system_message = ChatCompletionRequestSystemMessage(
            role='system', content=SYSTEM_PROMPT
        )
        llm_messages = [system_message.model_dump()] + messages
        available_tools = self.tool_service.get_available_tools()
        tools = available_tools if available_tools else None
        executed_tools: list[ToolExecutionResult] = []
        attempted_tool_execution = False

        for _ in range(MAXIMUM_TOOL_ROUNDS):
            round_tool_calls: dict[str, ChatCompletionMessageToolCall] = {}
            round_content_parts: list[str] = []
            finish_reason: str | None = None

            completion_kwargs = {
                'messages': llm_messages,
                'model': settings.llm_model,
                'temperature': temperature,
                'max_tokens': max_tokens,
            }
            if tools:
                completion_kwargs['tools'] = [
                    tool.model_dump() for tool in tools
                ]
                completion_kwargs['tool_choice'] = ToolChoice.auto

            async for output in self.llm_service.stream_messages(
                **completion_kwargs
            ):
                if output.finish_reason is not None:
                    finish_reason = output.finish_reason
                    logger.debug(
                        'conversation streaming turn complete: finish_reason=%s usage=%s',
                        output.finish_reason,
                        output.usage.model_dump() if output.usage else None,
                    )
                    if output.finish_reason == 'length':
                        logger.debug(
                            'conversation streaming turn likely truncated: max_tokens=%s',
                            max_tokens,
                        )

                if output.thought:
                    yield {'type': 'thought', 'data': output.thought}

                if output.token:
                    round_content_parts.append(output.token)
                    yield {'type': 'token', 'data': output.token}

                if output.model or output.usage:
                    yield {
                        'type': 'meta',
                        'data': {
                            'model': output.model,
                            'usage': output.usage.model_dump()
                            if output.usage
                            else None,
                            'executed_tools': executed_tools,
                            'attempted_tool_execution': attempted_tool_execution,
                            'finish_reason': finish_reason,
                        },
                    }

                if output.tool_calls:
                    for tool_call in output.tool_calls:
                        round_tool_calls[tool_call.id] = tool_call

            if not round_tool_calls:
                yield {
                    'type': 'meta',
                    'data': {
                        'executed_tools': executed_tools,
                        'attempted_tool_execution': attempted_tool_execution,
                        'finish_reason': finish_reason,
                    },
                }
                return

            attempted_tool_execution = True
            llm_messages.append(
                {
                    'role': 'assistant',
                    'content': ''.join(round_content_parts) or None,
                    'tool_calls': list(round_tool_calls.values()),
                }
            )

            for tool_call in round_tool_calls.values():
                yield {
                    'type': 'tool_call',
                    'data': {
                        'id': tool_call.id,
                        'name': tool_call.function.name,
                        'status': 'requested',
                    },
                }
                try:
                    parsed_arguments = self._parse_tool_arguments(tool_call)
                except LLMCompletionError as exc:
                    yield {
                        'type': 'tool_call',
                        'data': {
                            'id': tool_call.id,
                            'name': tool_call.function.name,
                            'status': 'failed',
                            'detail': str(exc),
                        },
                    }
                    raise
                yield {
                    'type': 'tool_call',
                    'data': {
                        'id': tool_call.id,
                        'name': tool_call.function.name,
                        'status': 'running',
                    },
                }
                try:
                    tool_result = await self.tool_service.execute_tool(
                        name=tool_call.function.name,
                        arguments=parsed_arguments,
                    )
                except (UnsupportedToolError, DisabledToolError) as exc:
                    yield {
                        'type': 'tool_call',
                        'data': {
                            'id': tool_call.id,
                            'name': tool_call.function.name,
                            'status': 'failed',
                            'detail': str(exc),
                        },
                    }
                    raise LLMCompletionError(
                        kind=LLMCompletionErrorKind.invalid_response,
                        message=f'Tool error: {str(exc)}',
                    ) from exc
                except Exception as exc:
                    yield {
                        'type': 'tool_call',
                        'data': {
                            'id': tool_call.id,
                            'name': tool_call.function.name,
                            'status': 'failed',
                            'detail': str(exc),
                        },
                    }
                    raise LLMCompletionError(
                        kind=LLMCompletionErrorKind.backend_error,
                        message=f'Error executing tool {tool_call.function.name}: {str(exc)}',
                    ) from exc

                executed_tools.append(tool_result)
                yield {
                    'type': 'tool_call',
                    'data': {
                        'id': tool_call.id,
                        'name': tool_call.function.name,
                        'status': 'completed'
                        if tool_result.status.value == 'success'
                        else 'failed',
                    },
                }
                yield {
                    'type': 'meta',
                    'data': {
                        'executed_tools': executed_tools,
                        'attempted_tool_execution': attempted_tool_execution,
                    },
                }

                llm_messages.append(
                    {
                        'role': 'tool',
                        'tool_call_id': tool_call.id,
                        'content': tool_result.llm_context or '',
                    }
                )

        raise LLMCompletionError(
            kind=LLMCompletionErrorKind.backend_error,
            message=f'Assistant exceeded maximum tool rounds ({MAXIMUM_TOOL_ROUNDS})',
        )

    @staticmethod
    def _parse_tool_arguments(
        tool_call,
    ) -> dict:
        """Parse tool arguments from an OpenAI-compatible tool call delta."""
        try:
            parsed_arguments = json.loads(tool_call.function.arguments)
            if not isinstance(parsed_arguments, dict):
                raise ValueError(
                    f'Tool arguments must be a JSON object, got {type(parsed_arguments).__name__}'
                )
            return parsed_arguments
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.invalid_response,
                message=f'Unable to parse tool arguments for {tool_call.function.name}: {str(exc)}',
            ) from exc

    @staticmethod
    def _conversation_summary(
        conversation: Conversation,
    ) -> ConversationSummary:
        return ConversationSummary(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    @staticmethod
    def _message_read(message: Message) -> MessageRead:
        return MessageRead(
            id=message.id,
            role=cast('str', message.role),
            content=message.content,
            sequence_number=message.sequence_number,
            created_at=message.created_at,
            error=message.error,
            annotations=message.annotations,
        )

    async def extract_and_save_background(
        self,
        *,
        user_id: str,
        conversation_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        latest_user_message_id: uuid.UUID | None = None,
    ) -> None:
        """Background extraction job: extract summary and facts after successful response.

        This method runs after the assistant message has been persisted, outside the
        request path. It:
        1. Loads a fresh database session
        2. Reloads conversation and messages from canonical Postgres
        3. Extracts refreshed summary using LLMService
        4. Extracts durable facts worth saving
        5. Persists to Postgres via MemoryStorage
        6. Mirrors summary/facts to Chroma for retrieval support
        7. Updates assistant message annotations with truthful memory_saved data

        Failures at any point are logged but do not affect the already-persisted
        conversation or user-visible chat responses.

        Args:
            user_id: User ID for isolation
            conversation_id: Conversation UUID
            assistant_message_id: UUID of assistant message to extract from
            latest_user_message_id: Optional UUID of latest user message (context hint)
        """
        try:
            # Import here to avoid circular imports and to get fresh session
            from assistant.utils.database import get_db_session

            async with get_db_session() as session:
                # Reload conversation and messages from canonical Postgres
                _ = await self._get_conversation_for_user(
                    session,
                    user_id=user_id,
                    conversation_id=conversation_id,
                )

                messages = await self._get_messages_for_conversation(
                    session,
                    conversation_id=conversation_id,
                )

                # Find the assistant message we just created
                assistant_msg = next(
                    (m for m in messages if m.id == assistant_message_id),
                    None,
                )
                if not assistant_msg:
                    logger.warning(
                        f'Background extraction: assistant message '
                        f'{assistant_message_id} not found in conversation '
                        f'{conversation_id}'
                    )
                    return

                # Extract summary and facts from the latest turns
                extraction_prompt = self._build_extraction_prompt(
                    messages=messages,
                    assistant_message=assistant_msg,
                )

                try:
                    # Call LLM for extraction
                    completion_result = (
                        await self.llm_service.complete_messages(
                            messages=extraction_prompt,
                            model=settings.llm_model,
                            temperature=0.3,  # Lower temperature for extraction
                            max_tokens=1000,
                        )
                    )

                    # Parse extraction output
                    summary_text, facts = self._parse_extraction_result(
                        completion_result.content
                    )

                    # Track what we actually save
                    summary_saved = False
                    persisted_summary = None
                    facts_count = 0
                    persisted_facts = []

                    # Persist summary if extracted
                    if summary_text and self.memory_storage:
                        persisted_summary = await self.memory_storage.upsert_conversation_summary(
                            session=session,
                            conversation_id=conversation_id,
                            user_id=user_id,
                            summary_text=summary_text,
                            source_message_id=assistant_message_id,
                        )
                        summary_saved = True

                    # Persist each durable fact if extracted
                    if facts and self.memory_storage:
                        from assistant.models.memory_sql import (
                            DurableFactConfidence,
                            DurableFactSourceType,
                        )

                        for fact_data in facts:
                            try:
                                persisted_fact = await self.memory_storage.upsert_durable_fact(
                                    session=session,
                                    user_id=user_id,
                                    subject=fact_data.get('subject', ''),
                                    fact_text=fact_data.get('fact', ''),
                                    confidence=DurableFactConfidence(
                                        fact_data.get('confidence', 'medium')
                                    ),
                                    source_type=DurableFactSourceType.CONVERSATION,
                                    source_conversation_id=conversation_id,
                                    source_message_id=assistant_message_id,
                                    source_excerpt=assistant_msg.content[:240]
                                    if assistant_msg.content
                                    else None,
                                )
                                persisted_facts.append(persisted_fact)
                                facts_count += 1
                            except Exception as e:
                                logger.warning(
                                    f'Failed to save durable fact: {str(e)}'
                                )

                    # Commit the session to persist all writes
                    await session.commit()

                    # Index persisted memory into Chroma for retrieval support
                    if self.memory_storage:
                        if persisted_summary:
                            try:
                                self.memory_storage.index_conversation_summary(
                                    persisted_summary
                                )
                            except Exception as e:
                                logger.error(
                                    f'Failed to index conversation summary in '
                                    f'Chroma: {str(e)}'
                                )

                        for persisted_fact in persisted_facts:
                            try:
                                self.memory_storage.index_durable_fact(
                                    persisted_fact
                                )
                            except Exception as e:
                                logger.error(
                                    f'Failed to index durable fact in Chroma: '
                                    f'{str(e)}'
                                )

                    logger.info(
                        f'Background extraction completed for conversation '
                        f'{conversation_id}: summary_saved={summary_saved}, '
                        f'facts_count={facts_count}'
                    )

                    # Now enrich the assistant message annotations with memory_saved
                    # This must happen AFTER commit to ensure all memory writes are canonical
                    if summary_saved or facts_count > 0:
                        try:
                            await self._enrich_assistant_annotations_with_memory_saved(
                                session=session,
                                assistant_message_id=assistant_message_id,
                                summary_saved=summary_saved,
                                facts_count=facts_count,
                            )
                        except (ValidationError, TypeError) as e:
                            logger.error(
                                f'Failed to enrich assistant annotations with '
                                f'memory_saved: {str(e)}'
                            )
                            # Do not propagate - annotation enrichment failure
                            # should not affect the already-successful extraction

                except Exception as e:
                    logger.error(
                        f'Background extraction failed for conversation '
                        f'{conversation_id}: {str(e)}'
                    )
                    await session.rollback()

        except Exception as e:
            logger.error(
                f'Background extraction job failed for conversation '
                f'{conversation_id}: {str(e)}'
            )

    def _build_extraction_prompt(
        self,
        messages: list[Message],
        assistant_message: Message,
    ) -> list[dict]:
        """Build an LLM prompt for extracting summary and facts.

        Slices the conversation relative to the target assistant message,
        not the current tail. This ensures that if new messages are added
        before extraction completes, we still extract context for the
        correct exchange and correctly attribute facts/summary to the
        target message.

        Returns a minimal prompt structure for extraction.
        """
        # Find the index of the target assistant message
        msg_index = next(
            (i for i, m in enumerate(messages) if m.id == assistant_message.id),
            -1,
        )

        if msg_index == -1:
            # Fallback: should not happen, but use last 4 as safety net
            logger.warning(
                f'Target assistant message {assistant_message.id} not found '
                f'in message list during extraction prompt build'
            )
            recent = messages[-4:] if len(messages) > 4 else messages
        else:
            # Include up to 3 messages before the target assistant message,
            # plus the message itself. This gives us the user's request + our
            # response in context.
            start_idx = max(0, msg_index - 3)
            recent = messages[start_idx : msg_index + 1]

        # Build a simple extraction prompt
        user_content = (
            'Please extract:\n'
            '1. A brief one-sentence summary of this conversation update\n'
            '2. Any important facts to remember about the user\n\n'
            'Format as JSON:\n'
            '{"summary": "...", "facts": [{"subject": "...", "fact": "...", "confidence": "high|medium|low"}]}\n\n'
            'Recent exchange:\n'
        )

        for msg in recent:
            role_label = 'User' if msg.role == 'user' else 'Assistant'
            user_content += f'{role_label}: {msg.content}\n'

        return [
            {
                'role': 'system',
                'content': (
                    'You are a memory extraction assistant. '
                    'Extract brief, factual summaries and user facts '
                    'from conversations. Be concise and accurate.'
                ),
            },
            {'role': 'user', 'content': user_content},
        ]

    def _parse_extraction_result(
        self, result_text: str
    ) -> tuple[str | None, list[dict] | None]:
        """Parse LLM extraction result into summary and facts.

        Returns:
          Tuple of (summary_text, facts_list)
          Both can be None if extraction fails or produces empty results.
        """
        try:
            # Try to extract JSON from result
            start_idx = result_text.find('{')
            end_idx = result_text.rfind('}') + 1

            if start_idx == -1 or end_idx == 0:
                logger.warning('No JSON found in extraction result')
                return None, None

            json_str = result_text[start_idx:end_idx]
            data = json.loads(json_str)

            summary = data.get('summary')
            facts = data.get('facts', [])

            # Filter out empty facts
            facts = [f for f in facts if f.get('fact') and f.get('subject')]

            return summary, facts if facts else None

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f'Failed to parse extraction result: {str(e)}')
            return None, None

    async def _enrich_assistant_annotations_with_memory_saved(
        self,
        session: AsyncSession,
        *,
        assistant_message_id: uuid.UUID,
        summary_saved: bool = False,
        facts_count: int = 0,
    ) -> None:
        """Enrich persisted assistant message annotations with truthful memory_saved data.

        After successful background extraction and persistence, update the assistant
        message row to include memory_saved annotations reflecting what was actually
        persisted. This is read-modify-write to preserve existing annotations
        (sources, tools, memory_hits, failure).

        Args:
            session: Database session
            assistant_message_id: UUID of the assistant message to enrich
            summary_saved: Whether conversation summary was saved/updated
            facts_count: Number of durable facts that were saved/updated
        """
        # Read the current message row
        stmt = select(Message).where(
            # pyrefly: ignore [bad-argument-type]
            Message.id == assistant_message_id
        )
        result = await session.execute(stmt)
        message = result.scalar_one_or_none()

        if not message:
            logger.warning(
                f'Assistant message {assistant_message_id} not found '
                f'for annotation enrichment'
            )
            return

        # Get current annotations or start with empty
        current_annotations_dict = message.annotations or {}

        try:
            # Parse current annotations to AssistantAnnotations model
            current_annotations = AssistantAnnotations(
                # pyrefly: ignore [bad-unpacking]
                **current_annotations_dict
            )
        except Exception:
            # If current annotations are malformed, log but continue with clean slate
            logger.warning(
                f'Failed to parse current annotations for message '
                f'{assistant_message_id}, using fresh annotations'
            )
            current_annotations = AssistantAnnotations()

        # Build memory_saved annotations from what was actually saved
        memory_saved = self.annotation_service.build_memory_saved_annotations(
            summary_saved=summary_saved, facts_count=facts_count
        )

        # Merge: preserve all existing fields, update only memory_saved
        enriched_annotations = AssistantAnnotations(
            thought=current_annotations.thought,  # PRESERVE: reasoning trace
            sources=current_annotations.sources,
            tools=current_annotations.tools,
            memory_hits=current_annotations.memory_hits,
            memory_saved=memory_saved,  # NEW: add memory_saved from extraction
            failure=current_annotations.failure,
        )

        # Update the message row with enriched annotations
        enriched_dict = enriched_annotations.model_dump()
        await session.execute(
            update(Message)
            # pyrefly: ignore [bad-argument-type]
            .where(Message.id == assistant_message_id)
            .values(annotations=enriched_dict)
        )
        await session.commit()

        logger.info(
            f'Enriched assistant message {assistant_message_id} with '
            f'memory_saved annotations'
        )
