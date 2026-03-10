from fastapi import APIRouter, HTTPException, status
import httpx
import pydantic

from assistant.constants import SYSTEM_PROMPT
from assistant.models.chat import ChatRequest, ChatResponse
from assistant.models.llm import (
    ChatCompletionRequestSystemMessage,
    CreateChatCompletionRequest,
    CreateChatCompletionResponse,
)
from assistant.security.session_auth import CurrentUser
from assistant.services import llm_service
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
    request_body: CreateChatCompletionRequest = CreateChatCompletionRequest(
        model=settings.llm_model,
        messages=messages,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        stream=False,
    )

    try:
        response = await llm_service.create_chat_completion(
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
    return ChatResponse(
        # pyrefly: ignore [bad-argument-type]
        content=choice.message.content or '',
        model=llm_response.model,
        prompt_tokens=llm_response.usage.prompt_tokens,
        completion_tokens=llm_response.usage.completion_tokens,
        total_tokens=llm_response.usage.total_tokens,
    )
