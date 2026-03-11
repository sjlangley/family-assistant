from typing import cast
import uuid

from fastapi import HTTPException, status
import httpx
import pydantic
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.constants import SYSTEM_PROMPT
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
    CreateChatCompletionRequest,
    CreateChatCompletionResponse,
)
from assistant.services.llm_service import LLMService
from assistant.settings import settings


def conversation_title_from_first_message(content: str) -> str:
    title = content.strip()
    return title[:60] or 'New chat'


class ConversationService:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

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

        # Make LLM call outside of transaction
        assistant_content = await self._call_llm_chat_completion(
            messages=[{'role': 'user', 'content': content}],
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

        # Make LLM call outside of transaction
        llm_messages = [
            {'role': m.role, 'content': m.content} for m in existing_messages
        ]
        llm_messages.append({'role': 'user', 'content': content})

        assistant_content = await self._call_llm_chat_completion(
            messages=llm_messages,
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
        system_message = ChatCompletionRequestSystemMessage(
            role='system', content=SYSTEM_PROMPT
        )
        llm_messages = [system_message.model_dump()] + messages
        request_body: CreateChatCompletionRequest = CreateChatCompletionRequest(
            model=settings.llm_model,
            messages=llm_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        try:
            response = await self.llm_service.create_chat_completion(
                request_body.model_dump(exclude_none=True)
            )
        except TimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail='LLM request timed out',
            ) from exc
        except ConnectionError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='Failed to reach LLM backend',
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    'message': 'LLM backend returned an error',
                    'status_code': exc.response.status_code,
                },
            ) from exc

        try:
            llm_response = CreateChatCompletionResponse.model_validate(response)
        except pydantic.ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='LLM backend returned an unexpected response shape',
            ) from exc

        if not llm_response.choices:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='LLM backend did not return any choices',
            )

        choice = llm_response.choices[0]
        return choice.message.content or ''

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
        )
