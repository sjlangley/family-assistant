"""Tests for chat endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

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

    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_llm_response

        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

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
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert '/v1/chat/completions' in call_args[0][0]
    assert call_args[1]['json']['messages'][1]['content'] == 'Hello'


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
    with patch('httpx.AsyncClient') as mock_client:
        mock_post = AsyncMock(side_effect=httpx.TimeoutException('Timeout'))
        mock_client.return_value.__aenter__.return_value.post = mock_post

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
    with patch('httpx.AsyncClient') as mock_client:
        mock_post = AsyncMock(
            side_effect=httpx.ConnectError('Connection failed')
        )
        mock_client.return_value.__aenter__.return_value.post = mock_post

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
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'

        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

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

    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_llm_response

        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

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

    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_llm_response

        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

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

    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_llm_response

        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

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
    call_args = mock_post.call_args
    request_body = call_args[1]['json']
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

    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_llm_response

        mock_post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.post = mock_post

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
