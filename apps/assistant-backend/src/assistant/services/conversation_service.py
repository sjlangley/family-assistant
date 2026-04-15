import json
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
    ToolChoice,
)
from assistant.routers.web_utils import llm_completion_error_to_http_exception
from assistant.services.context_assembly import ContextAssemblyService
from assistant.services.llm_service import LLMService
from assistant.services.tool_service import ToolService
from assistant.settings import settings


def conversation_title_from_first_message(content: str) -> str:
    title = content.strip()
    return title[:60] or 'New chat'


class ConversationService:
    def __init__(
        self,
        llm_service: LLMService,
        context_assembly: ContextAssemblyService,
        tool_service: ToolService,
    ) -> None:
        self.llm_service = llm_service
        self.context_assembly = context_assembly
        self.tool_service = tool_service

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
        assistant_content = await self._call_llm_chat_completion(
            messages=context_result.messages,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )

        # Transaction 2: Create assistant message and update conversation
        assistant_message = Message(
            conversation_id=conversation_id,
            role='assistant',
            content=assistant_content,
            sequence_number=2,
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
        assistant_content = await self._call_llm_chat_completion(
            messages=context_result.messages,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )

        # Transaction 2: Create assistant message and update conversation
        assistant_message = Message(
            conversation_id=conversation_id,
            role='assistant',
            content=assistant_content,
            sequence_number=next_seq + 1,
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
    ) -> str:
        """Call LLM completion and return assistant content.

        Prepares system prompt and delegates to the shared LLM completion seam.
        """
        system_message = ChatCompletionRequestSystemMessage(
            role='system', content=SYSTEM_PROMPT
        )
        llm_messages = [system_message.model_dump()] + messages
        available_tools = self.tool_service.get_available_tools()
        tools = available_tools if available_tools else None

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
                if not result.tool_calls:
                    return result.content

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
                    except json.JSONDecodeError as exc:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=(
                                f'Invalid tool arguments JSON: '
                                f'{tool_call.function.name}'
                            ),
                        ) from exc
                    except ValueError as exc:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=str(exc),
                        ) from exc
                    try:
                        tool_result = await self.tool_service.execute_tool(
                            name=tool_call.function.name,
                            arguments=parsed_arguments,
                        )
                    except Exception as exc:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f'Error executing tool {tool_call.function.name}: {str(exc)}',
                        ) from exc

                    llm_messages.append(
                        {
                            'role': 'tool',
                            'tool_call_id': tool_call.id,
                            'content': tool_result.llm_context or '',
                        }
                    )

            except LLMCompletionError as exc:
                raise llm_completion_error_to_http_exception(exc) from exc

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f'Assistant exceeded maximum tool rounds ({MAXIMUM_TOOL_ROUNDS})',
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
