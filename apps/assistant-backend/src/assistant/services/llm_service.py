from fastapi import HTTPException, status
import httpx
import pydantic

from assistant.models.llm import (
    CreateChatCompletionRequest,
    CreateChatCompletionResponse,
    LLMCompletionError,
    LLMCompletionErrorKind,
    LLMCompletionResult,
)


class LLMService:
    """Service for interacting with the LLM backend."""

    def __init__(self, base_url: str, timeout_seconds: int):
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.client = httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        """Close the underlying HTTP client and release network resources."""
        await self.client.aclose()

    async def complete_messages(
        self,
        *,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int | None,
    ) -> LLMCompletionResult:
        """Execute a chat completion request.

        This is the canonical LLM completion seam. It owns:
        - Request construction
        - LLM transport call
        - Response validation
        - First-choice extraction
        - Error classification

        The caller prepares the final messages list including system prompt.

        Args:
            messages: List of messages including system prompt
            model: Model identifier
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            LLMCompletionResult with content and usage stats

        Raises:
            LLMCompletionError: On any failure (timeout, unreachable,
                backend error, or invalid response)
        """
        request_body = CreateChatCompletionRequest(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        try:
            response_dict = await self._post_completion(
                request_body.model_dump(exclude_none=True)
            )
        except TimeoutError as exc:
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.timeout,
                message='LLM request timed out',
            ) from exc
        except ConnectionError as exc:
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.unreachable,
                message='Failed to reach LLM backend',
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.backend_error,
                message='LLM backend returned an error',
                backend_status_code=exc.response.status_code,
            ) from exc

        # Validate response shape
        try:
            response = CreateChatCompletionResponse.model_validate(
                response_dict
            )
        except pydantic.ValidationError as exc:
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.invalid_response,
                message='LLM backend returned an unexpected response shape',
            ) from exc

        # Extract first choice
        if not response.choices:
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.invalid_response,
                message='LLM backend did not return any choices',
            )

        choice = response.choices[0]
        return LLMCompletionResult(
            content=choice.message.content or '',
            model=response.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
        )

    async def _post_completion(self, request_body: dict) -> dict:
        """Private helper for raw HTTP POST to completion endpoint."""
        try:
            response = await self.client.post(
                f'{self.base_url}/v1/chat/completions',
                json=request_body,
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError('LLM request timed out') from exc
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            raise ConnectionError('Failed to reach LLM backend') from exc

    async def create_chat_completion(self, request_body: dict) -> dict:
        """Legacy method for backward compatibility.

        Deprecated: Use complete_messages() for new code.
        """
        return await self._post_completion(request_body)


def llm_completion_error_to_http_exception(
    error: LLMCompletionError,
) -> HTTPException:
    """Convert LLMCompletionError to FastAPI HTTPException.

    Preserves current error response behavior for all error kinds.
    """
    if error.kind == LLMCompletionErrorKind.timeout:
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail='LLM request timed out',
        )
    elif error.kind == LLMCompletionErrorKind.unreachable:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail='Failed to reach LLM backend',
        )
    elif error.kind == LLMCompletionErrorKind.backend_error:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                'message': 'LLM backend returned an error',
                'status_code': error.backend_status_code,
            },
        )
    else:  # invalid_response
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error.message,
        )
