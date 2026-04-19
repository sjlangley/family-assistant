"""Tests for chat endpoint."""

from unittest.mock import AsyncMock, patch

import pytest

from assistant.constants import SYSTEM_PROMPT
from assistant.models.llm import (
    LLMCompletionError,
    LLMCompletionErrorKind,
    LLMCompletionResult,
)

pytestmark = pytest.mark.asyncio


async def test_create_chat_completion_success(
    authenticated_async_test_client,
):
    """Test successful chat completion."""
    mock_completion_result = LLMCompletionResult(
        content='Hello! How can I help you?',
        model='test-model',
        prompt_tokens=10,
        completion_tokens=15,
        total_tokens=25,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_service = AsyncMock()
    mock_service.complete_messages = AsyncMock(
        return_value=mock_completion_result
    )

    with patch(
        'assistant.routers.chat.get_llm_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/chat/completions',
            json={
                'messages': [
                    {'role': 'user', 'content': 'Hello'},
                ],
                'temperature': 0.7,
                'max_tokens': 512,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data['content'] == 'Hello! How can I help you?'
    assert data['model'] == 'test-model'
    assert data['prompt_tokens'] == 10
    assert data['completion_tokens'] == 15
    assert data['total_tokens'] == 25

    # Verify the LLM was called with correct parameters
    mock_service.complete_messages.assert_called_once()
    call_kwargs = mock_service.complete_messages.call_args.kwargs

    # Verify system prompt injection
    messages = call_kwargs['messages']
    assert messages[0]['role'] == 'system'
    assert messages[0]['content'] == SYSTEM_PROMPT
    assert messages[1]['role'] == 'user'
    assert messages[1]['content'] == 'Hello'


async def test_create_chat_completion_requires_auth(async_test_client):
    """Test that chat completion requires authentication."""
    response = await async_test_client.post(
        '/api/v1/chat/completions',
        json={
            'messages': [
                {'role': 'user', 'content': 'Hello'},
            ],
        },
    )

    assert response.status_code == 401


async def test_create_chat_completion_empty_messages(
    authenticated_async_test_client,
):
    """Test that empty messages list returns 400."""
    response = await authenticated_async_test_client.post(
        '/api/v1/chat/completions',
        json={
            'messages': [],
        },
    )

    assert response.status_code == 400
    data = response.json()
    assert 'At least one message is required' in data['detail']


async def test_create_chat_completion_invalid_role(
    authenticated_async_test_client,
):
    """Test that invalid message role returns 422."""
    response = await authenticated_async_test_client.post(
        '/api/v1/chat/completions',
        json={
            'messages': [
                {'role': 'invalid', 'content': 'Hello'},
            ],
        },
    )

    assert response.status_code == 422


async def test_create_chat_completion_llm_timeout(
    authenticated_async_test_client,
):
    """Test LLM timeout handling."""
    mock_service = AsyncMock()
    mock_service.complete_messages = AsyncMock(
        side_effect=LLMCompletionError(
            kind=LLMCompletionErrorKind.timeout,
            message='LLM request timed out',
        )
    )

    with patch(
        'assistant.routers.chat.get_llm_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/chat/completions',
            json={
                'messages': [
                    {'role': 'user', 'content': 'Hello'},
                ],
            },
        )

    assert response.status_code == 504
    data = response.json()
    assert 'LLM request timed out' in data['detail']


async def test_create_chat_completion_llm_unreachable(
    authenticated_async_test_client,
):
    """Test LLM backend unreachable handling."""
    mock_service = AsyncMock()
    mock_service.complete_messages = AsyncMock(
        side_effect=LLMCompletionError(
            kind=LLMCompletionErrorKind.unreachable,
            message='Failed to reach LLM backend',
        )
    )

    with patch(
        'assistant.routers.chat.get_llm_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/chat/completions',
            json={
                'messages': [
                    {'role': 'user', 'content': 'Hello'},
                ],
            },
        )

    assert response.status_code == 502
    data = response.json()
    assert 'Failed to reach LLM backend' in data['detail']


async def test_create_chat_completion_llm_error_response(
    authenticated_async_test_client,
):
    """Test LLM backend error response handling."""
    mock_service = AsyncMock()
    mock_service.complete_messages = AsyncMock(
        side_effect=LLMCompletionError(
            kind=LLMCompletionErrorKind.backend_error,
            message='LLM backend returned an error',
            backend_status_code=500,
        )
    )

    with patch(
        'assistant.routers.chat.get_llm_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/chat/completions',
            json={
                'messages': [
                    {'role': 'user', 'content': 'Hello'},
                ],
            },
        )

    assert response.status_code == 502
    data = response.json()
    assert data['detail']['message'] == 'LLM backend returned an error'
    assert data['detail']['status_code'] == 500


async def test_create_chat_completion_malformed_llm_response(
    authenticated_async_test_client,
):
    """Test malformed LLM response handling."""
    mock_service = AsyncMock()
    mock_service.complete_messages = AsyncMock(
        side_effect=LLMCompletionError(
            kind=LLMCompletionErrorKind.invalid_response,
            message='LLM backend did not return any choices',
        )
    )

    with patch(
        'assistant.routers.chat.get_llm_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/chat/completions',
            json={
                'messages': [
                    {'role': 'user', 'content': 'Hello'},
                ],
            },
        )

    assert response.status_code == 502
    data = response.json()
    assert 'did not return any choices' in data['detail']


async def test_create_chat_completion_missing_content(
    authenticated_async_test_client,
):
    """Test LLM response with missing content field."""
    mock_service = AsyncMock()
    mock_service.complete_messages = AsyncMock(
        side_effect=LLMCompletionError(
            kind=LLMCompletionErrorKind.invalid_response,
            message='LLM response has unexpected response shape',
        )
    )

    with patch(
        'assistant.routers.chat.get_llm_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/chat/completions',
            json={
                'messages': [
                    {'role': 'user', 'content': 'Hello'},
                ],
            },
        )

    assert response.status_code == 502
    data = response.json()
    assert 'unexpected response shape' in data['detail']


async def test_create_chat_completion_custom_temperature(
    authenticated_async_test_client,
):
    """Test chat completion with custom temperature."""
    mock_completion_result = LLMCompletionResult(
        content='Response',
        model='test-model',
        prompt_tokens=5,
        completion_tokens=3,
        total_tokens=8,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_service = AsyncMock()
    mock_service.complete_messages = AsyncMock(
        return_value=mock_completion_result
    )

    with patch(
        'assistant.routers.chat.get_llm_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/chat/completions',
            json={
                'messages': [
                    {'role': 'user', 'content': 'Test'},
                ],
                'temperature': 0.2,
                'max_tokens': 256,
            },
        )

    assert response.status_code == 200

    # Verify temperature and max_tokens were passed to LLM
    call_kwargs = mock_service.complete_messages.call_args.kwargs
    assert call_kwargs['temperature'] == 0.2
    assert call_kwargs['max_tokens'] == 256


async def test_create_chat_completion_missing_usage_info(
    authenticated_async_test_client,
):
    """Test chat completion when LLM doesn't return usage info."""
    mock_completion_result = LLMCompletionResult(
        content='Response without usage',
        model='test-model',
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_service = AsyncMock()
    mock_service.complete_messages = AsyncMock(
        return_value=mock_completion_result
    )

    with patch(
        'assistant.routers.chat.get_llm_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/chat/completions',
            json={
                'messages': [
                    {'role': 'user', 'content': 'Hello'},
                ],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data['content'] == 'Response without usage'
    assert data['prompt_tokens'] == 0
    assert data['completion_tokens'] == 0
    assert data['total_tokens'] == 0


async def test_debug_stream_success(authenticated_async_test_client):
    """Test debug stream endpoint returns event-stream."""
    response = await authenticated_async_test_client.get('/api/v1/chat/debug-stream')
    
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    assert response.headers['cache-control'] == 'no-cache'
    assert response.headers['x-accel-buffering'] == 'no'
    
    # We don't necessarily need to consume the whole stream in this basic test,
    # but let's verify it starts with a thought event.
    first_chunk = await response.aread()
    assert b'event: thought' in first_chunk
