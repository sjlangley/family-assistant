import logging
from typing import AsyncGenerator

import httpx
import pydantic

from assistant.models.llm import (
    CreateChatCompletionRequest,
    CreateChatCompletionResponse,
    LLMCompletionError,
    LLMCompletionErrorKind,
    LLMCompletionResult,
    StreamParserOutput,
)
from assistant.services.stream_parser import StreamParser

logger = logging.getLogger(__name__)


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

    def _build_request_body(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> dict:
        """Construct the OpenAI-compatible request body."""
        request = CreateChatCompletionRequest(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            tools=tools,
            tool_choice=tool_choice,
        )
        return request.model_dump(exclude_none=True)

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
        request_body = self._build_request_body(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            tools=tools,
            tool_choice=tool_choice,
        )

        try:
            response = await self.client.post(
                f'{self.base_url}/v1/chat/completions',
                json=request_body,
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
            response_obj = CreateChatCompletionResponse.model_validate(
                response_dict
            )
        except pydantic.ValidationError as exc:
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.invalid_response,
                message='LLM response has unexpected response shape',
            ) from exc

        # Extract first choice
        if not response_obj.choices:
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.invalid_response,
                message='LLM backend did not return any choices',
            )

        choice = response_obj.choices[0]
        return LLMCompletionResult(
            content=choice.message.content or '',
            model=response_obj.model,
            prompt_tokens=response_obj.usage.prompt_tokens,
            completion_tokens=response_obj.usage.completion_tokens,
            total_tokens=response_obj.usage.total_tokens,
            tool_calls=choice.message.tool_calls,
            finish_reason=choice.finish_reason,
        )

    async def stream_messages(
        self,
        *,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int | None,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> AsyncGenerator[StreamParserOutput, None]:
        """Execute a streaming chat completion request.

        This is the streaming equivalent of complete_messages. It yields
        incremental parser outputs including thought, tokens, and tool calls.

        Args:
            messages: List of messages including system prompt
            model: Model identifier
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tools: Optional list of tool definitions
            tool_choice: Optional tool choice specification

        Yields:
            StreamParserOutput for each chunk of the response

        Raises:
            LLMCompletionError: On transport or backend errors
        """
        request_body = self._build_request_body(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            tools=tools,
            tool_choice=tool_choice,
        )

        parser = StreamParser()

        try:
            async with self.client.stream(
                'POST',
                f'{self.base_url}/v1/chat/completions',
                json=request_body,
            ) as response:
                if response.status_code != 200:
                    # Drain response to get error message if possible
                    await response.aread()
                    raise LLMCompletionError(
                        kind=LLMCompletionErrorKind.backend_error,
                        message='LLM backend returned an error',
                        backend_status_code=response.status_code,
                    )

                async for line in response.aiter_lines():
                    if not line.startswith('data: '):
                        continue

                    data = line[6:].strip()
                    if data == '[DONE]':
                        break

                    try:
                        chunk_dict = pydantic.TypeAdapter(dict).validate_json(
                            data
                        )
                        output = parser.parse_chunk(chunk_dict)
                        yield output
                    except Exception as exc:
                        # Skip malformed chunks in the stream
                        logger.debug(
                            'Skipping malformed chunk in stream: %s',
                            data,
                            exc_info=exc,
                        )
                        continue

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
        except httpx.HTTPError as exc:
            if isinstance(exc, LLMCompletionError):
                raise
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.backend_error,
                message=f'LLM transport error: {exc}',
            ) from exc
