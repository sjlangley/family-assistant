"""Tests for chat endpoint."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from assistant.constants import SYSTEM_PROMPT

pytestmark = pytest.mark.asyncio


async def test_create_chat_completion_success(
    authenticated_async_test_client,
):
    """Test successful chat completion."""
    mock_llm_response = {
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

    mock_service = AsyncMock()
    mock_service.create_chat_completion = AsyncMock(
        return_value=mock_llm_response
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
    mock_service.create_chat_completion.assert_called_once()
    request_body = mock_service.create_chat_completion.call_args[0][0]
    assert request_body['messages'][0]['role'] == 'system'
    assert request_body['messages'][0]['content'] == SYSTEM_PROMPT
    assert request_body['messages'][1]['role'] == 'user'
    assert request_body['messages'][1]['content'] == 'Hello'


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
    mock_service.create_chat_completion = AsyncMock(
        side_effect=TimeoutError('LLM request timed out')
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
    mock_service.create_chat_completion = AsyncMock(
        side_effect=ConnectionError('Failed to reach LLM backend')
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
    response = httpx.Response(
        500,
        request=httpx.Request('POST', 'http://test'),
    )
    error = httpx.HTTPStatusError(
        'LLM error',
        request=response.request,
        response=response,
    )

    mock_service = AsyncMock()
    mock_service.create_chat_completion = AsyncMock(side_effect=error)

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
    mock_llm_response = {
        'id': 'chatcmpl-malformed',
        'object': 'chat.completion',
        'created': 1677652288,
        'model': 'test-model',
        'choices': [],  # Empty choices - malformed
        'usage': {
            'prompt_tokens': 10,
            'completion_tokens': 0,
            'total_tokens': 10,
        },
    }

    mock_service = AsyncMock()
    mock_service.create_chat_completion = AsyncMock(
        return_value=mock_llm_response
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
    mock_llm_response = {
        'id': 'chatcmpl-nocontent',
        'object': 'chat.completion',
        'created': 1677652288,
        'model': 'test-model',
        'choices': [
            {
                'index': 0,
                'message': {
                    'role': 'assistant',
                    # Missing 'content' field
                },
                'logprobs': None,
                'finish_reason': 'stop',
            }
        ],
        'usage': {
            'prompt_tokens': 10,
            'completion_tokens': 0,
            'total_tokens': 10,
        },
    }

    mock_service = AsyncMock()
    mock_service.create_chat_completion = AsyncMock(
        return_value=mock_llm_response
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
    mock_llm_response = {
        'id': 'chatcmpl-temp',
        'object': 'chat.completion',
        'created': 1677652288,
        'model': 'test-model',
        'choices': [
            {
                'index': 0,
                'message': {
                    'role': 'assistant',
                    'content': 'Response',
                },
                'logprobs': None,
                'finish_reason': 'stop',
            }
        ],
        'usage': {
            'prompt_tokens': 5,
            'completion_tokens': 3,
            'total_tokens': 8,
        },
    }

    mock_service = AsyncMock()
    mock_service.create_chat_completion = AsyncMock(
        return_value=mock_llm_response
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
    request_body = mock_service.create_chat_completion.call_args[0][0]
    assert request_body['temperature'] == 0.2
    assert request_body['max_tokens'] == 256


async def test_create_chat_completion_missing_usage_info(
    authenticated_async_test_client,
):
    """Test chat completion when LLM doesn't return usage info."""
    mock_llm_response = {
        'id': 'chatcmpl-nousage',
        'object': 'chat.completion',
        'created': 1677652288,
        'model': 'test-model',
        'choices': [
            {
                'index': 0,
                'message': {
                    'role': 'assistant',
                    'content': 'Response without usage',
                },
                'logprobs': None,
                'finish_reason': 'stop',
            }
        ],
        'usage': {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
        },
    }

    mock_service = AsyncMock()
    mock_service.create_chat_completion = AsyncMock(
        return_value=mock_llm_response
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
