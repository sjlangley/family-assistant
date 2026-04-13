from fastapi import APIRouter, HTTPException, status

from assistant.constants import SYSTEM_PROMPT
from assistant.models.chat import ChatRequest, ChatResponse
from assistant.models.llm import (
    ChatCompletionRequestSystemMessage,
    LLMCompletionError,
)
from assistant.security.session_auth import CurrentUser
from assistant.services import get_llm_service
from assistant.services.llm_service import (
    llm_completion_error_to_http_exception,
)
from assistant.settings import settings

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
