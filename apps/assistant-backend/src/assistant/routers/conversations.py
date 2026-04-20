"""REST API handler for user conversations."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Request, status
from fastapi.responses import StreamingResponse

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
logger = logging.getLogger(__name__)

STREAMING_RESPONSE_SCHEMA = {
    'description': 'JSON response or SSE stream when `stream=true`.',
    'content': {
        'application/json': {
            'schema': ConversationWithMessagesResponse.model_json_schema()
        },
        'text/event-stream': {
            'schema': {
                'type': 'string',
                'example': 'event: token\ndata: "Hello"\n\n',
            }
        },
    },
}


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
    response_description='Return HTTP Status Code 201 (OK)',
    status_code=status.HTTP_201_CREATED,
    response_model=None,
    responses={status.HTTP_201_CREATED: STREAMING_RESPONSE_SCHEMA},
    include_in_schema=True,
)
async def create_conversation_with_message(
    request: Request,
    payload: CreateConversationWithMessageRequest,
    user: CurrentUser,
    session: DBSession,
    background_tasks: BackgroundTasks,
) -> ConversationWithMessagesResponse | StreamingResponse:
    """Create a new conversation with an initial user message."""
    conversation_service = get_conversation_service()
    logger.debug(
        'create_conversation_with_message called: stream=%s content_len=%s',
        payload.stream,
        len(payload.content or ''),
    )
    if payload.stream:
        logger.debug('Dispatching create_conversation_with_message_stream')
        return StreamingResponse(
            conversation_service.create_conversation_with_message_stream(
                session=session,
                user_id=user.userid,
                payload=payload,
                background_tasks=background_tasks,
            ),
            status_code=status.HTTP_201_CREATED,
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
            },
        )

    return ConversationWithMessagesResponse.model_validate(
        await conversation_service.create_conversation_with_message(
            session=session,
            user_id=user.userid,
            payload=payload,
            background_tasks=background_tasks,
        )
    )


@router.post(
    '/{conversation_id}/messages',
    status_code=status.HTTP_201_CREATED,
    response_model=None,
    responses={status.HTTP_201_CREATED: STREAMING_RESPONSE_SCHEMA},
)
async def add_message_to_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    payload: CreateMessageRequest,
    user: CurrentUser,
    session: DBSession,
    background_tasks: BackgroundTasks,
) -> ConversationWithMessagesResponse | StreamingResponse:
    conversation_service = get_conversation_service()
    logger.debug(
        'add_message_to_conversation called: conversation_id=%s stream=%s content_len=%s',
        conversation_id,
        payload.stream,
        len(payload.content or ''),
    )
    if payload.stream:
        logger.debug(
            'Dispatching add_message_to_conversation_stream for conversation_id=%s',
            conversation_id,
        )
        return StreamingResponse(
            conversation_service.add_message_to_conversation_stream(
                session=session,
                user_id=user.userid,
                conversation_id=conversation_id,
                payload=payload,
                background_tasks=background_tasks,
            ),
            status_code=status.HTTP_201_CREATED,
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
            },
        )

    return ConversationWithMessagesResponse.model_validate(
        await conversation_service.add_message_to_conversation(
            session=session,
            user_id=user.userid,
            conversation_id=conversation_id,
            payload=payload,
            background_tasks=background_tasks,
        )
    )
