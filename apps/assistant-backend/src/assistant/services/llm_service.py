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

    def __init__(
        self,
        base_url: str,
        timeout_seconds: int,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds)

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
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
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
            tools: Optional list of tool definitions to include in the request
            tool_choice: Optional specification of which tool to use, if any
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
            tools=tools,
            tool_choice=tool_choice,
        )

        try:
            response = await self.client.post(
                f'{self.base_url}/v1/chat/completions',
                json=request_body.model_dump(exclude_none=True),
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.timeout,
                message='LLM request timed out',
            ) from exc
        except httpx.ConnectError as exc:
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

        # Parse JSON response
        try:
            response_dict = response.json()
        except Exception as exc:
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.invalid_response,
                message='LLM response has unexpected response shape',
            ) from exc

        # Validate response shape
        try:
            response = CreateChatCompletionResponse.model_validate(
                response_dict
            )
        except pydantic.ValidationError as exc:
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.invalid_response,
                message='LLM response has unexpected response shape',
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
            tool_calls=choice.message.tool_calls,
            finish_reason=choice.finish_reason,
        )
