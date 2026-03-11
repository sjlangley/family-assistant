"""REST API handler for user conversations."""

import uuid

from fastapi import APIRouter, Request, status

from assistant.models.conversation import (
    ConversationWithMessagesResponse,
    CreateConversationWithMessageRequest,
    CreateMessageRequest,
    GetConversationMessagesResponse,
    ListConversationsResponse,
)
from assistant.security.session_auth import CurrentUser
from assistant.services import get_conversation_service
from assistant.utils.database import DBSession

router = APIRouter()


@router.get(
    '',
    response_description='List of conversations for the user',
    response_model=ListConversationsResponse,
)
async def list_conversations(
    request: Request,
    user: CurrentUser,
    session: DBSession,
) -> ListConversationsResponse:
    """List all conversations for the current user."""
    conversation_service = get_conversation_service()
    return await conversation_service.list_conversations(
        session=session,
        user_id=user.userid,
    )


@router.get(
    '/{conversation_id}/messages',
    response_model=GetConversationMessagesResponse,
)
async def get_conversation_messages(
    request: Request,
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: DBSession,
) -> GetConversationMessagesResponse:
    conversation_service = get_conversation_service()
    return await conversation_service.get_conversation_messages(
        session=session,
        user_id=user.userid,
        conversation_id=conversation_id,
    )


@router.post(
    '/with-message',
    response_description='Return HTTP Status Code 200 (OK)',
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationWithMessagesResponse,
    include_in_schema=False,
)
async def create_conversation_with_message(
    request: Request,
    payload: CreateConversationWithMessageRequest,
    user: CurrentUser,
    session: DBSession,
) -> ConversationWithMessagesResponse:
    """Create a new conversation with an initial user message."""
    conversation_service = get_conversation_service()
    return await conversation_service.create_conversation_with_message(
        session=session,
        user_id=user.userid,
        payload=payload,
    )


@router.post(
    '/{conversation_id}/messages',
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationWithMessagesResponse,
)
async def add_message_to_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    payload: CreateMessageRequest,
    user: CurrentUser,
    session: DBSession,
) -> ConversationWithMessagesResponse:
    conversation_service = get_conversation_service()
    return await conversation_service.add_message_to_conversation(
        session=session,
        user_id=user.userid,
        conversation_id=conversation_id,
        payload=payload,
    )
