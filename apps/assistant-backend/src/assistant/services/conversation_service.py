from dataclasses import dataclass
import json
import logging
from typing import cast
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.constants import MAXIMUM_TOOL_ROUNDS, SYSTEM_PROMPT
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
        background_tasks=None,
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

        # Make LLM call outside of transaction
        loop_result = await self._call_llm_chat_completion(
            messages=context_result.messages,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
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
            annotations_dict = annotations_obj.model_dump()
            error_text = self.annotation_service.format_error_detail(
                loop_result.error
            )
        else:
            annotations_obj = self.annotation_service.build_success_annotations(
                executed_tools=loop_result.executed_tools,
                fact_ids=context_result.fact_ids,
            )
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

        # Make LLM call outside of transaction
        loop_result = await self._call_llm_chat_completion(
            messages=context_result.messages,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
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
            annotations_dict = annotations_obj.model_dump()
            error_text = self.annotation_service.format_error_detail(
                loop_result.error
            )
        else:
            annotations_obj = self.annotation_service.build_success_annotations(
                executed_tools=loop_result.executed_tools,
                fact_ids=context_result.fact_ids,
            )
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

                # No tool calls - return final response
                if not result.tool_calls:
                    return _LLMLoopResult(
                        content=result.content,
                        executed_tools=executed_tools,
                        error=None,
                    )

                # Tool calls requested - add assistant response and execute
                llm_messages.append(
                    {
                        'role': 'assistant',
                        'content': result.content,
                        'tool_calls': result.tool_calls,
                    }
                )

                for tool_call in result.tool_calls:
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
                            attempted_tool_execution=True,
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
                            attempted_tool_execution=True,
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
                            attempted_tool_execution=True,
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
        )

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
                # For now, use a simple extraction prompt
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

                    # Persist summary if extracted
                    if summary_text and self.memory_storage:
                        await self.memory_storage.upsert_conversation_summary(
                            session=session,
                            conversation_id=conversation_id,
                            user_id=user_id,
                            summary_text=summary_text,
                            source_message_id=assistant_message_id,
                        )

                    # Persist each durable fact if extracted
                    if facts and self.memory_storage:
                        from assistant.models.memory_sql import (
                            DurableFactConfidence,
                            DurableFactSourceType,
                        )

                        for fact_data in facts:
                            try:
                                await self.memory_storage.upsert_durable_fact(
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
                            except Exception as e:
                                logger.warning(
                                    f'Failed to save durable fact: {str(e)}'
                                )

                    # Commit the session to persist all writes
                    await session.commit()

                    logger.info(
                        f'Background extraction completed for conversation '
                        f'{conversation_id}'
                    )

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

        Returns a minimal prompt structure for extraction.
        """
        # Build a simple extraction prompt
        user_content = (
            'Please extract:\n'
            '1. A brief one-sentence summary of this conversation update\n'
            '2. Any important facts to remember about the user\n\n'
            'Format as JSON:\n'
            '{"summary": "...", "facts": [{"subject": "...", "fact": "...", "confidence": "high|medium|low"}]}\n\n'
            'Recent exchange:\n'
        )

        # Add last few messages for context
        recent = messages[-4:] if len(messages) > 4 else messages
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
            import json

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

        except Exception as e:
            logger.warning(f'Failed to parse extraction result: {str(e)}')
            return None, None
