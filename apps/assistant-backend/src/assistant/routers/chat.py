import asyncio

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from assistant.constants import SYSTEM_PROMPT
from assistant.models.chat import ChatRequest, ChatResponse
from assistant.models.llm import (
    ChatCompletionRequestSystemMessage,
    LLMCompletionError,
)
from assistant.routers.web_utils import llm_completion_error_to_http_exception
from assistant.security.session_auth import CurrentUser
from assistant.services import get_llm_service
from assistant.settings import settings
from assistant.utils.sse import SSEEncoder

router = APIRouter()


@router.post('/completions', response_model=ChatResponse)
async def create_chat_completion(
    payload: ChatRequest,
    _: CurrentUser,
) -> ChatResponse:
    if not payload.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='At least one message is required',
        )

    system_message = ChatCompletionRequestSystemMessage(
        role='system', content=SYSTEM_PROMPT
    )
    messages = [system_message.model_dump()] + [
        message.model_dump() for message in payload.messages
    ]

    # Explicit exception handling pattern - converts service errors to HTTP.
    # Global exception handler planned for Step 6 to eliminate duplication.
    try:
        result = await get_llm_service().complete_messages(
            messages=messages,
            model=settings.llm_model,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )
    except LLMCompletionError as exc:
        raise llm_completion_error_to_http_exception(exc) from exc

    return ChatResponse(
        content=result.content,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
    )


@router.get('/debug-stream')
async def debug_stream(_: CurrentUser):
    """Debug endpoint to verify the SSE delivery pipeline.

    Streams a sequence of dummy events: thought, tokens, and done.
    """

    async def event_generator():
        # 1. Thought
        yield SSEEncoder.encode('thought', 'Thinking about a debug response...')
        await asyncio.sleep(0.5)

        # 2. Tokens
        tokens = ['Hello', '!', ' This', ' is', ' a', ' debug', ' stream', '.']
        for token in tokens:
            yield SSEEncoder.encode('token', token)
            await asyncio.sleep(0.2)

        # 3. Done
        yield SSEEncoder.encode(
            'done',
            {
                'message_id': 'debug-123',
                'content': 'Hello! This is a debug stream.',
            },
        )

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',  # Disable buffering in Nginx
        },
    )
