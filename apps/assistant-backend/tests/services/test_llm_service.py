"""Tests for LLMService."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from assistant.services.llm_service import LLMService

pytestmark = pytest.mark.asyncio


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
