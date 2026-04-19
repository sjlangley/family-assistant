"""Tests for LLMService."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from assistant.models.llm import LLMCompletionError, LLMCompletionErrorKind
from assistant.services.llm_service import LLMService

pytestmark = pytest.mark.asyncio


# Tests for complete_messages (shared LLM completion seam)


async def test_complete_messages_success():
    """It returns LLMCompletionResult with parsed content and usage."""
    messages = [
        {'role': 'system', 'content': 'You are helpful'},
        {'role': 'user', 'content': 'Hello'},
    ]
    mock_response = {
        'id': 'chatcmpl-123',
        'object': 'chat.completion',
        'created': 1677652288,
        'model': 'test-model',
        'choices': [
            {
                'index': 0,
                'message': {
                    'role': 'assistant',
                    'content': 'Hello! How can I help you?',
                },
                'logprobs': None,
                'finish_reason': 'stop',
            }
        ],
        'usage': {
            'prompt_tokens': 10,
            'completion_tokens': 15,
            'total_tokens': 25,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == '/v1/chat/completions'
        payload = json.loads(request.content)
        assert payload['messages'] == messages
        assert payload['model'] == 'test-model'
        assert payload['temperature'] == 0.7
        assert payload['max_tokens'] == 128
        assert payload['stream'] is False
        return httpx.Response(200, json=mock_response, request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url='http://test')
    service = LLMService(
        base_url='http://test', timeout_seconds=5, client=client
    )

    try:
        result = await service.complete_messages(
            messages=messages,
            model='test-model',
            temperature=0.7,
            max_tokens=128,
        )
    finally:
        await service.aclose()

    assert result.content == 'Hello! How can I help you?'
    assert result.model == 'test-model'
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 15
    assert result.total_tokens == 25
    assert result.tool_calls is None
    assert result.finish_reason == 'stop'


async def test_complete_messages_with_tool_calls():
    """It preserves tool_calls metadata in the result."""
    messages = [{'role': 'user', 'content': 'What is the weather?'}]
    mock_response = {
        'id': 'chatcmpl-456',
        'object': 'chat.completion',
        'created': 1677652288,
        'model': 'test-model',
        'choices': [
            {
                'index': 0,
                'message': {
                    'role': 'assistant',
                    'content': None,
                    'tool_calls': [
                        {
                            'id': 'call_abc123',
                            'type': 'function',
                            'function': {
                                'name': 'get_weather',
                                'arguments': '{"location": "Seattle"}',
                            },
                        }
                    ],
                },
                'logprobs': None,
                'finish_reason': 'tool_calls',
            }
        ],
        'usage': {
            'prompt_tokens': 20,
            'completion_tokens': 10,
            'total_tokens': 30,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_response, request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url='http://test')
    service = LLMService(
        base_url='http://test', timeout_seconds=5, client=client
    )

    try:
        result = await service.complete_messages(
            messages=messages,
            model='test-model',
            temperature=0.7,
            max_tokens=128,
        )
    finally:
        await service.aclose()

    assert result.content == ''
    assert result.model == 'test-model'
    assert result.prompt_tokens == 20
    assert result.completion_tokens == 10
    assert result.total_tokens == 30
    assert result.finish_reason == 'tool_calls'
    assert result.tool_calls is not None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == 'call_abc123'
    assert result.tool_calls[0].type == 'function'
    assert result.tool_calls[0].function.name == 'get_weather'
    assert result.tool_calls[0].function.arguments == '{"location": "Seattle"}'


async def test_complete_messages_timeout():
    """It raises LLMCompletionError with timeout kind."""
    client = httpx.AsyncClient(base_url='http://test')
    client.post = AsyncMock(side_effect=httpx.TimeoutException('Timeout'))
    service = LLMService(
        base_url='http://test', timeout_seconds=5, client=client
    )

    try:
        with pytest.raises(LLMCompletionError) as exc_info:
            await service.complete_messages(
                messages=[],
                model='test',
                temperature=0.7,
                max_tokens=100,
            )

        assert exc_info.value.kind == LLMCompletionErrorKind.timeout
        assert exc_info.value.message == 'LLM request timed out'
        assert exc_info.value.backend_status_code is None
    finally:
        await service.aclose()


async def test_complete_messages_unreachable():
    """It raises LLMCompletionError with unreachable kind."""
    client = httpx.AsyncClient(base_url='http://test')
    client.post = AsyncMock(side_effect=httpx.ConnectError('Connection failed'))
    service = LLMService(
        base_url='http://test', timeout_seconds=5, client=client
    )

    try:
        with pytest.raises(LLMCompletionError) as exc_info:
            await service.complete_messages(
                messages=[],
                model='test',
                temperature=0.7,
                max_tokens=100,
            )

        assert exc_info.value.kind == LLMCompletionErrorKind.unreachable
        assert exc_info.value.message == 'Failed to reach LLM backend'
        assert exc_info.value.backend_status_code is None
    finally:
        await service.aclose()


async def test_complete_messages_backend_error():
    """It raises LLMCompletionError with backend_error kind and status code."""
    response = httpx.Response(
        500,
        request=httpx.Request('POST', 'http://test'),
    )
    error = httpx.HTTPStatusError(
        'LLM error',
        request=response.request,
        response=response,
    )

    client = httpx.AsyncClient(base_url='http://test')
    client.post = AsyncMock(side_effect=error)
    service = LLMService(
        base_url='http://test', timeout_seconds=5, client=client
    )

    try:
        with pytest.raises(LLMCompletionError) as exc_info:
            await service.complete_messages(
                messages=[],
                model='test',
                temperature=0.7,
                max_tokens=100,
            )

        assert exc_info.value.kind == LLMCompletionErrorKind.backend_error
        assert exc_info.value.message == 'LLM backend returned an error'
        assert exc_info.value.backend_status_code == 500
    finally:
        await service.aclose()


async def test_complete_messages_invalid_response_shape():
    """It raises LLMCompletionError with invalid_response kind."""
    mock_response = {
        'invalid': 'response',
        'missing': 'required fields',
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_response, request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url='http://test')
    service = LLMService(
        base_url='http://test', timeout_seconds=5, client=client
    )

    try:
        with pytest.raises(LLMCompletionError) as exc_info:
            await service.complete_messages(
                messages=[],
                model='test',
                temperature=0.7,
                max_tokens=100,
            )

        assert exc_info.value.kind == LLMCompletionErrorKind.invalid_response
        assert 'unexpected response shape' in exc_info.value.message.lower()
    finally:
        await service.aclose()


async def test_complete_messages_empty_choices():
    """It raises LLMCompletionError with invalid_response kind."""
    mock_response = {
        'id': 'chatcmpl-123',
        'object': 'chat.completion',
        'created': 1677652288,
        'model': 'test-model',
        'choices': [],  # Empty choices
        'usage': {
            'prompt_tokens': 10,
            'completion_tokens': 0,
            'total_tokens': 10,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_response, request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url='http://test')
    service = LLMService(
        base_url='http://test', timeout_seconds=5, client=client
    )

    try:
        with pytest.raises(LLMCompletionError) as exc_info:
            await service.complete_messages(
                messages=[],
                model='test',
                temperature=0.7,
                max_tokens=100,
            )

        assert exc_info.value.kind == LLMCompletionErrorKind.invalid_response
        assert 'did not return any choices' in exc_info.value.message
    finally:
        await service.aclose()


async def test_complete_messages_invalid_json():
    """It raises LLMCompletionError when response is not valid JSON."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'not valid json',
            headers={'content-type': 'application/json'},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url='http://test')
    service = LLMService(
        base_url='http://test', timeout_seconds=5, client=client
    )

    try:
        with pytest.raises(LLMCompletionError) as exc_info:
            await service.complete_messages(
                messages=[],
                model='test',
                temperature=0.7,
                max_tokens=100,
            )

        assert exc_info.value.kind == LLMCompletionErrorKind.invalid_response
        assert 'unexpected response shape' in exc_info.value.message.lower()
    finally:
        await service.aclose()


# Tests for stream_messages (streaming LLM completion seam)


async def test_stream_messages_success():
    """It yields StreamParserOutput objects for each chunk."""
    messages = [{'role': 'user', 'content': 'Hello'}]

    # Mock SSE stream data
    chunks = [
        {
            'id': '1',
            'object': 'chat.completion.chunk',
            'created': 1,
            'model': 'test',
            'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}],
        },
        {
            'id': '2',
            'object': 'chat.completion.chunk',
            'created': 2,
            'model': 'test',
            'choices': [{'index': 0, 'delta': {'content': 'Hi'}, 'finish_reason': None}],
        },
        {
            'id': '3',
            'object': 'chat.completion.chunk',
            'created': 3,
            'model': 'test',
            'choices': [{'index': 0, 'delta': {'content': ' there'}, 'finish_reason': 'stop'}],
        },
    ]

    sse_content = ''.join([f'data: {json.dumps(c)}\n\n' for c in chunks])
    sse_content += 'data: [DONE]\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == '/v1/chat/completions'
        payload = json.loads(request.content)
        assert payload['stream'] is True
        return httpx.Response(
            200,
            content=sse_content.encode('utf-8'),
            headers={'content-type': 'text/event-stream'},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url='http://test')
    service = LLMService(base_url='http://test', timeout_seconds=5, client=client)

    outputs = []
    try:
        async for output in service.stream_messages(
            messages=messages,
            model='test-model',
            temperature=0.7,
            max_tokens=128,
        ):
            outputs.append(output)
    finally:
        await service.aclose()

    assert len(outputs) == 3
    assert outputs[0].model == 'test'
    assert outputs[1].token == 'Hi'
    assert outputs[2].token == ' there'
    assert outputs[2].finish_reason == 'stop'


async def test_stream_messages_timeout():
    """It raises LLMCompletionError on stream timeout."""
    from unittest.mock import MagicMock
    client = httpx.AsyncClient(base_url='http://test')
    # Mock stream to return an async context manager that raises on __aenter__
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=httpx.TimeoutException('Timeout'))
    client.stream = MagicMock(return_value=mock_ctx)
    
    service = LLMService(base_url='http://test', timeout_seconds=5, client=client)

    try:
        with pytest.raises(LLMCompletionError) as exc_info:
            async for _ in service.stream_messages(
                messages=[],
                model='test',
                temperature=0.7,
                max_tokens=100,
            ):
                pass

        assert exc_info.value.kind == LLMCompletionErrorKind.timeout
        assert exc_info.value.message == 'LLM request timed out'
    finally:
        await service.aclose()


async def test_stream_messages_unreachable():
    """It raises LLMCompletionError when backend is unreachable."""
    from unittest.mock import MagicMock
    client = httpx.AsyncClient(base_url='http://test')
    # Mock stream to return an async context manager that raises on __aenter__
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=httpx.ConnectError('Connection failed'))
    client.stream = MagicMock(return_value=mock_ctx)
    
    service = LLMService(base_url='http://test', timeout_seconds=5, client=client)

    try:
        with pytest.raises(LLMCompletionError) as exc_info:
            async for _ in service.stream_messages(
                messages=[],
                model='test',
                temperature=0.7,
                max_tokens=100,
            ):
                pass

        assert exc_info.value.kind == LLMCompletionErrorKind.unreachable
        assert exc_info.value.message == 'Failed to reach LLM backend'
    finally:
        await service.aclose()


async def test_stream_messages_backend_error():
    """It raises LLMCompletionError on non-200 response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b'Internal Server Error', request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url='http://test')
    service = LLMService(base_url='http://test', timeout_seconds=5, client=client)

    try:
        with pytest.raises(LLMCompletionError) as exc_info:
            async for _ in service.stream_messages(
                messages=[],
                model='test',
                temperature=0.7,
                max_tokens=100,
            ):
                pass

        assert exc_info.value.kind == LLMCompletionErrorKind.backend_error
        assert exc_info.value.backend_status_code == 500
    finally:
        await service.aclose()
