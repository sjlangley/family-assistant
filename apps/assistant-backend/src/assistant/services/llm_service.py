import json
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


def _extract_error_metadata(
    body_text: str | None,
) -> tuple[str | None, str | None]:
    """Extract non-sensitive provider error metadata for logs."""
    if not body_text:
        return None, None

    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError:
        return None, None

    if not isinstance(payload, dict):
        return None, None

    error_obj = payload.get('error')
    if isinstance(error_obj, dict):
        code = error_obj.get('code')
        error_type = error_obj.get('type')
        return (
            str(code) if code is not None else None,
            str(error_type) if error_type is not None else None,
        )

    code = payload.get('code')
    error_type = payload.get('type')
    return (
        str(code) if code is not None else None,
        str(error_type) if error_type is not None else None,
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
            error_body = exc.response.text[:1000] if exc.response else None
            error_code, error_type = _extract_error_metadata(error_body)
            logger.error(
                'LLM backend HTTP error: status=%s provider_error_code=%s provider_error_type=%s',
                exc.response.status_code if exc.response else None,
                error_code,
                error_type,
            )
            if error_body:
                logger.debug('LLM backend HTTP error body: %s', error_body)
            if error_body:
                lowered = error_body.lower()
                if (
                    'context length' in lowered
                    or 'maximum context length' in lowered
                    or 'prompt is too long' in lowered
                    or 'too many tokens' in lowered
                ):
                    logger.debug(
                        'LLM likely hit context/token limits in non-stream request'
                    )
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
        logger.debug(
            'LLM completion finished: model=%s finish_reason=%s usage(prompt=%s completion=%s total=%s)',
            response_obj.model,
            choice.finish_reason,
            response_obj.usage.prompt_tokens,
            response_obj.usage.completion_tokens,
            response_obj.usage.total_tokens,
        )
        if choice.finish_reason == 'length':
            logger.debug(
                'LLM completion truncated by token limit: model=%s max_tokens=%s usage_total=%s',
                response_obj.model,
                max_tokens,
                response_obj.usage.total_tokens,
            )
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
                    raw_body = await response.aread()
                    body_text = raw_body.decode(errors='replace')[:1000]
                    error_code, error_type = _extract_error_metadata(body_text)
                    logger.error(
                        'LLM streaming backend error: status=%s provider_error_code=%s provider_error_type=%s',
                        response.status_code,
                        error_code,
                        error_type,
                    )
                    if body_text:
                        logger.debug(
                            'LLM streaming backend error body: %s',
                            body_text,
                        )
                    lowered = body_text.lower()
                    if (
                        'context length' in lowered
                        or 'maximum context length' in lowered
                        or 'prompt is too long' in lowered
                        or 'too many tokens' in lowered
                    ):
                        logger.debug(
                            'LLM likely hit context/token limits in stream request'
                        )
                    raise LLMCompletionError(
                        kind=LLMCompletionErrorKind.backend_error,
                        message='LLM backend returned an error',
                        backend_status_code=response.status_code,
                    )

                saw_done_marker = False

                async for line in response.aiter_lines():
                    if not line.startswith('data: '):
                        continue

                    data = line[6:].strip()
                    if data == '[DONE]':
                        saw_done_marker = True
                        break

                    try:
                        chunk_dict = json.loads(data)
                        output = parser.parse_chunk(chunk_dict)
                        if output.finish_reason is not None:
                            logger.debug(
                                'LLM stream finished: model=%s finish_reason=%s usage=%s',
                                output.model,
                                output.finish_reason,
                                output.usage.model_dump()
                                if output.usage
                                else None,
                            )
                            if output.finish_reason == 'length':
                                logger.debug(
                                    'LLM stream truncated by token limit: model=%s max_tokens=%s',
                                    output.model,
                                    max_tokens,
                                )
                        yield output
                    except Exception as exc:
                        # Skip malformed chunks in the stream
                        logger.debug(
                            'Skipping malformed chunk in stream: %s',
                            data,
                            exc_info=exc,
                        )
                        continue

                if not saw_done_marker:
                    raise LLMCompletionError(
                        kind=LLMCompletionErrorKind.invalid_response,
                        message='LLM stream did not terminate with [DONE]',
                    )

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
            raise LLMCompletionError(
                kind=LLMCompletionErrorKind.backend_error,
                message=f'LLM transport error: {exc}',
            ) from exc
