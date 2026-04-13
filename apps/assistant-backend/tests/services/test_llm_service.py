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
    service = LLMService(base_url='http://test', timeout_seconds=5)
    service.client = client

    try:
        result = await service.complete_messages(
            messages=messages,
            model='test-model',
            temperature=0.7,
            max_tokens=128,
        )
    finally:
        await client.aclose()

    assert result.content == 'Hello! How can I help you?'
    assert result.model == 'test-model'
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 15
    assert result.total_tokens == 25


async def test_complete_messages_timeout():
    """It raises LLMCompletionError with timeout kind."""
    service = LLMService(base_url='http://test', timeout_seconds=5)
    service.client = httpx.AsyncClient(base_url='http://test')
    service.client.post = AsyncMock(
        side_effect=httpx.TimeoutException('Timeout')
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
        await service.client.aclose()


async def test_complete_messages_unreachable():
    """It raises LLMCompletionError with unreachable kind."""
    service = LLMService(base_url='http://test', timeout_seconds=5)
    service.client = httpx.AsyncClient(base_url='http://test')
    service.client.post = AsyncMock(
        side_effect=httpx.ConnectError('Connection failed')
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
        await service.client.aclose()


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

    service = LLMService(base_url='http://test', timeout_seconds=5)
    service.client = httpx.AsyncClient(base_url='http://test')
    service.client.post = AsyncMock(side_effect=error)

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
        await service.client.aclose()


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
    service = LLMService(base_url='http://test', timeout_seconds=5)
    service.client = client

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
        await client.aclose()


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
    service = LLMService(base_url='http://test', timeout_seconds=5)
    service.client = client

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
        await client.aclose()


# Legacy tests for create_chat_completion (backward compatibility)


async def test_create_chat_completion_success():
    """It returns the parsed JSON response on success."""
    request_body = {
        'model': 'test-model',
        'messages': [{'role': 'user', 'content': 'Hello'}],
        'temperature': 0.7,
        'max_tokens': 128,
        'stream': False,
    }
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
        assert payload == request_body
        return httpx.Response(200, json=mock_response, request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url='http://test')
    service = LLMService(base_url='http://test', timeout_seconds=5)
    service.client = client

    try:
        response = await service.create_chat_completion(request_body)
    finally:
        await client.aclose()

    assert response == mock_response


async def test_create_chat_completion_timeout():
    """It raises TimeoutError when httpx times out."""
    service = LLMService(base_url='http://test', timeout_seconds=5)
    service.client = httpx.AsyncClient(base_url='http://test')
    service.client.post = AsyncMock(
        side_effect=httpx.TimeoutException('Timeout')
    )

    try:
        with pytest.raises(TimeoutError, match='LLM request timed out'):
            await service.create_chat_completion({'messages': []})
    finally:
        await service.client.aclose()


async def test_create_chat_completion_request_error():
    """It raises ConnectionError when httpx fails to connect."""
    service = LLMService(base_url='http://test', timeout_seconds=5)
    service.client = httpx.AsyncClient(base_url='http://test')
    service.client.post = AsyncMock(
        side_effect=httpx.ConnectError('Connection failed')
    )

    try:
        with pytest.raises(
            ConnectionError, match='Failed to reach LLM backend'
        ):
            await service.create_chat_completion({'messages': []})
    finally:
        await service.client.aclose()


async def test_create_chat_completion_http_status_error():
    """It re-raises HTTPStatusError for non-2xx responses."""
    response = httpx.Response(
        500,
        request=httpx.Request('POST', 'http://test'),
    )
    error = httpx.HTTPStatusError(
        'LLM error',
        request=response.request,
        response=response,
    )

    service = LLMService(base_url='http://test', timeout_seconds=5)
    service.client = httpx.AsyncClient(base_url='http://test')
    service.client.post = AsyncMock(side_effect=error)

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await service.create_chat_completion({'messages': []})
    finally:
        await service.client.aclose()
