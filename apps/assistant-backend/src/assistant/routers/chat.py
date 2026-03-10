from fastapi import APIRouter, HTTPException, Request, status
import httpx
import pydantic

from assistant.models.chat import ChatRequest, ChatResponse
from assistant.models.llm import (
    CreateChatCompletionRequest,
    CreateChatCompletionResponse,
)
from assistant.security.session_auth import require_auth
from assistant.settings import settings

router = APIRouter()


@router.post('/completions', response_model=ChatResponse)
async def create_chat_completion(
    request: Request,
    payload: ChatRequest,
) -> ChatResponse:
    require_auth(request)
    if not payload.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='At least one message is required',
        )

    request_body: CreateChatCompletionRequest = CreateChatCompletionRequest(
        model=settings.llm_model,
        messages=[message.model_dump() for message in payload.messages],
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        stream=False,
    )

    try:
        async with httpx.AsyncClient(
            timeout=settings.llm_timeout_seconds
        ) as client:
            response = await client.post(
                f'{settings.llm_base_url}/v1/chat/completions',
                json=request_body.model_dump(),
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail='LLM request timed out',
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail='Failed to reach LLM backend',
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                'message': 'LLM backend returned an error',
                'status_code': response.status_code,
                'body': response.text,
            },
        )

    data = response.json()

    try:
        llm_response = CreateChatCompletionResponse.model_validate(data)
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
        content=choice.message.content,
        model=llm_response.model,
        prompt_tokens=llm_response.usage.prompt_tokens,
        completion_tokens=llm_response.usage.completion_tokens,
        total_tokens=llm_response.usage.total_tokens,
    )
