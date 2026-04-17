"""Tests for conversations router endpoints."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
import pytest

pytestmark = pytest.mark.asyncio


def build_assistant_annotations() -> dict:
    return {
        'sources': [
            {
                'title': 'Example Source',
                'url': 'https://example.com',
                'snippet': 'Example supporting snippet',
                'rationale': 'Shows why the source matters',
            }
        ],
        'tools': [{'name': 'web_fetch', 'status': 'completed'}],
        'memory_hits': [
            {
                'label': 'Saved family detail',
                'summary': 'Matched a previously saved fact',
            }
        ],
        'memory_saved': [],
        'failure': None,
    }


async def test_list_conversations_success(authenticated_async_test_client):
    """Test successfully listing conversations for a user."""
    conv_id_1 = str(uuid4())
    conv_id_2 = str(uuid4())

    mock_response = {
        'items': [
            {
                'id': conv_id_1,
                'title': 'First Conversation',
                'created_at': '2024-01-01T00:00:00Z',
                'updated_at': '2024-01-01T00:00:00Z',
            },
            {
                'id': conv_id_2,
                'title': 'Second Conversation',
                'created_at': '2024-01-01T00:00:00Z',
                'updated_at': '2024-01-01T00:00:00Z',
            },
        ]
    }

    mock_service = AsyncMock()
    mock_service.list_conversations = AsyncMock(return_value=mock_response)

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.get(
            '/api/v1/conversations'
        )

    assert response.status_code == 200
    data = response.json()
    assert 'items' in data
    assert len(data['items']) == 2
    assert data['items'][0]['title'] == 'First Conversation'
    assert data['items'][1]['title'] == 'Second Conversation'


async def test_list_conversations_empty(authenticated_async_test_client):
    """Test listing conversations when user has none."""
    mock_service = AsyncMock()
    mock_service.list_conversations = AsyncMock(return_value={'items': []})

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.get(
            '/api/v1/conversations'
        )

    assert response.status_code == 200
    data = response.json()
    assert data['items'] == []


async def test_list_conversations_requires_auth(async_test_client):
    """Test that list_conversations requires authentication."""
    response = await async_test_client.get('/api/v1/conversations')
    assert response.status_code == 401


async def test_get_conversation_messages_success(
    authenticated_async_test_client,
):
    """Test successfully getting messages for a conversation."""
    conv_id = str(uuid4())
    msg_id_1 = str(uuid4())
    msg_id_2 = str(uuid4())

    mock_response = {
        'conversation': {
            'id': conv_id,
            'title': 'Test Conversation',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
        },
        'items': [
            {
                'id': msg_id_1,
                'role': 'user',
                'content': 'Hello',
                'sequence_number': 1,
                'created_at': '2024-01-01T00:00:00Z',
                'error': None,
                'annotations': None,
            },
            {
                'id': msg_id_2,
                'role': 'assistant',
                'content': 'Hi there!',
                'sequence_number': 2,
                'created_at': '2024-01-01T00:00:00Z',
                'error': None,
                'annotations': build_assistant_annotations(),
            },
        ],
    }

    mock_service = AsyncMock()
    mock_service.get_conversation_messages = AsyncMock(
        return_value=mock_response
    )

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.get(
            f'/api/v1/conversations/{conv_id}/messages'
        )

    assert response.status_code == 200
    data = response.json()
    assert 'items' in data
    assert len(data['items']) == 2
    assert data['items'][0]['content'] == 'Hello'
    assert data['items'][0]['role'] == 'user'
    assert data['items'][0]['annotations'] is None
    assert data['items'][1]['content'] == 'Hi there!'
    assert data['items'][1]['role'] == 'assistant'
    assert data['items'][1]['annotations'] is not None
    assert data['items'][1]['annotations']['sources'][0]['title'] == (
        'Example Source'
    )


async def test_get_conversation_messages_not_found(
    authenticated_async_test_client,
):
    """Test getting messages for non-existent conversation."""
    conv_id = str(uuid4())
    mock_service = AsyncMock()
    mock_service.get_conversation_messages = AsyncMock(
        side_effect=HTTPException(
            status_code=404, detail='Conversation not found'
        )
    )

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.get(
            f'/api/v1/conversations/{conv_id}/messages'
        )

    assert response.status_code == 404
    assert 'not found' in response.json()['detail'].lower()


async def test_get_conversation_messages_invalid_uuid(
    authenticated_async_test_client,
):
    """Test getting messages with invalid conversation_id format."""
    response = await authenticated_async_test_client.get(
        '/api/v1/conversations/invalid-uuid/messages'
    )
    assert response.status_code == 422  # Validation error


async def test_get_conversation_messages_requires_auth(async_test_client):
    """Test that get_conversation_messages requires authentication."""
    conv_id = str(uuid4())
    response = await async_test_client.get(
        f'/api/v1/conversations/{conv_id}/messages'
    )
    assert response.status_code == 401


async def test_create_conversation_with_message_success(
    authenticated_async_test_client,
):
    """Test successfully creating a conversation with initial message."""
    conv_id = str(uuid4())
    msg_id_1 = str(uuid4())
    msg_id_2 = str(uuid4())

    mock_response = {
        'conversation': {
            'id': conv_id,
            'title': 'Generated Title',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
        },
        'user_message': {
            'id': msg_id_1,
            'role': 'user',
            'content': 'What is Python?',
            'sequence_number': 1,
            'created_at': '2024-01-01T00:00:00Z',
            'error': None,
            'annotations': None,
        },
        'assistant_message': {
            'id': msg_id_2,
            'role': 'assistant',
            'sequence_number': 2,
            'content': 'Python is a programming language.',
            'created_at': '2024-01-01T00:00:00Z',
            'error': None,
            'annotations': build_assistant_annotations(),
        },
    }

    mock_service = AsyncMock()
    mock_service.create_conversation_with_message = AsyncMock(
        return_value=mock_response
    )

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/conversations/with-message',
            json={
                'content': 'What is Python?',
                'temperature': 0.7,
                'max_tokens': 512,
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert 'conversation' in data
    assert 'user_message' in data
    assert 'assistant_message' in data
    assert data['conversation']['title'] == 'Generated Title'
    assert data['user_message']['content'] == 'What is Python?'
    assert data['user_message']['annotations'] is None
    assert (
        data['assistant_message']['content']
        == 'Python is a programming language.'
    )
    assert data['assistant_message']['annotations'] is not None
    assert data['assistant_message']['annotations']['tools'] == [
        {'name': 'web_fetch', 'status': 'completed'}
    ]


async def test_create_conversation_with_message_default_params(
    authenticated_async_test_client,
):
    """Test creating conversation with default temperature and max_tokens."""
    conv_id = str(uuid4())
    msg_id = str(uuid4())

    mock_response = {
        'conversation': {
            'id': conv_id,
            'title': 'Test Title',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
        },
        'user_message': {
            'id': msg_id,
            'role': 'user',
            'content': 'Hello',
            'sequence_number': 1,
            'created_at': '2024-01-01T00:00:00Z',
            'error': None,
            'annotations': None,
        },
        'assistant_message': {
            'id': msg_id,
            'role': 'assistant',
            'content': 'Hello',
            'sequence_number': 2,
            'created_at': '2024-01-01T00:00:00Z',
            'error': None,
            'annotations': None,
        },
    }

    mock_service = AsyncMock()
    mock_service.create_conversation_with_message = AsyncMock(
        return_value=mock_response
    )

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/conversations/with-message',
            json={'content': 'Hello'},
        )

    assert response.status_code == 201


async def test_create_conversation_with_message_empty_message(
    authenticated_async_test_client,
):
    """Test that empty message is rejected."""
    # Mock the memory storage to prevent ChromaDB connection attempts
    mock_memory_storage = AsyncMock()

    with patch(
        'assistant.services.get_memory_storage',
        return_value=mock_memory_storage,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/conversations/with-message',
            json={'content': ''},
        )

    assert response.status_code == 400


async def test_create_conversation_with_message_missing_message(
    authenticated_async_test_client,
):
    """Test that missing content field is rejected."""
    response = await authenticated_async_test_client.post(
        '/api/v1/conversations/with-message',
        json={'temperature': 0.5},
    )
    assert response.status_code == 422  # Validation error


async def test_create_conversation_with_message_invalid_temperature(
    authenticated_async_test_client,
):
    """Test that invalid temperature is rejected."""
    response = await authenticated_async_test_client.post(
        '/api/v1/conversations/with-message',
        json={'content': 'Hello', 'temperature': 2.5},  # Too high
    )
    assert response.status_code == 422  # Validation error


async def test_create_conversation_with_message_invalid_max_tokens(
    authenticated_async_test_client,
):
    """Test that invalid max_tokens is rejected."""
    response = await authenticated_async_test_client.post(
        '/api/v1/conversations/with-message',
        json={'content': 'Hello', 'max_tokens': 0},  # Too low
    )
    assert response.status_code == 422  # Validation error


async def test_create_conversation_with_message_requires_auth(
    async_test_client,
):
    """Test that create_conversation_with_message requires authentication."""
    response = await async_test_client.post(
        '/api/v1/conversations/with-message',
        json={'content': 'Hello'},
    )
    assert response.status_code == 401


async def test_create_conversation_with_message_llm_failure(
    authenticated_async_test_client,
):
    """Test handling of LLM service failure."""
    mock_service = AsyncMock()
    mock_service.create_conversation_with_message = AsyncMock(
        side_effect=HTTPException(
            status_code=503, detail='LLM service unavailable'
        )
    )

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/conversations/with-message',
            json={'content': 'Hello'},
        )

    assert response.status_code == 503
    assert 'unavailable' in response.json()['detail'].lower()


# ==================== add_message_to_conversation tests ====================


async def test_add_message_to_conversation_success(
    authenticated_async_test_client,
):
    """Test successfully adding a message to an existing conversation."""
    conv_id = str(uuid4())
    user_msg_id = str(uuid4())
    assistant_msg_id = str(uuid4())

    mock_response = {
        'conversation': {
            'id': conv_id,
            'title': 'Existing Conversation',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:01Z',
        },
        'user_message': {
            'id': user_msg_id,
            'role': 'user',
            'content': 'Follow-up question',
            'sequence_number': 3,
            'created_at': '2024-01-01T00:00:01Z',
            'error': None,
            'annotations': None,
        },
        'assistant_message': {
            'id': assistant_msg_id,
            'role': 'assistant',
            'content': 'Follow-up response',
            'sequence_number': 4,
            'created_at': '2024-01-01T00:00:01Z',
            'error': None,
            'annotations': build_assistant_annotations(),
        },
    }

    mock_service = AsyncMock()
    mock_service.add_message_to_conversation = AsyncMock(
        return_value=mock_response
    )

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            f'/api/v1/conversations/{conv_id}/messages',
            json={
                'content': 'Follow-up question',
                'temperature': 0.8,
                'max_tokens': 1024,
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert 'conversation' in data
    assert 'user_message' in data
    assert 'assistant_message' in data
    assert data['conversation']['id'] == conv_id
    assert data['user_message']['content'] == 'Follow-up question'
    assert data['user_message']['annotations'] is None
    assert data['assistant_message']['content'] == 'Follow-up response'
    assert data['assistant_message']['annotations'] is not None
    assert (
        data['assistant_message']['annotations']['memory_hits'][0]['label']
        == 'Saved family detail'
    )


async def test_add_message_to_conversation_default_params(
    authenticated_async_test_client,
):
    """Test adding a message with default temperature and max_tokens."""
    conv_id = str(uuid4())

    mock_response = {
        'conversation': {
            'id': conv_id,
            'title': 'Test Conversation',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:01Z',
        },
        'user_message': {
            'id': str(uuid4()),
            'role': 'user',
            'content': 'Hello',
            'sequence_number': 1,
            'created_at': '2024-01-01T00:00:01Z',
            'error': None,
            'annotations': None,
        },
        'assistant_message': {
            'id': str(uuid4()),
            'role': 'assistant',
            'content': 'Hi',
            'sequence_number': 2,
            'created_at': '2024-01-01T00:00:01Z',
            'error': None,
            'annotations': None,
        },
    }

    mock_service = AsyncMock()
    mock_service.add_message_to_conversation = AsyncMock(
        return_value=mock_response
    )

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            f'/api/v1/conversations/{conv_id}/messages',
            json={'content': 'Hello'},
        )

    assert response.status_code == 201


async def test_add_message_to_conversation_not_found(
    authenticated_async_test_client,
):
    """Test adding a message to a non-existent conversation."""
    conv_id = str(uuid4())
    mock_service = AsyncMock()
    mock_service.add_message_to_conversation = AsyncMock(
        side_effect=HTTPException(
            status_code=404, detail='Conversation not found'
        )
    )

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            f'/api/v1/conversations/{conv_id}/messages',
            json={'content': 'Hello'},
        )

    assert response.status_code == 404
    assert 'not found' in response.json()['detail'].lower()


async def test_add_message_to_conversation_invalid_uuid(
    authenticated_async_test_client,
):
    """Test adding a message with invalid conversation_id format."""
    response = await authenticated_async_test_client.post(
        '/api/v1/conversations/invalid-uuid/messages',
        json={'content': 'Hello'},
    )
    assert response.status_code == 422  # Validation error


async def test_add_message_to_conversation_empty_content(
    authenticated_async_test_client,
):
    """Test that empty content is rejected."""
    conv_id = str(uuid4())

    # Mock the memory storage to prevent ChromaDB connection attempts
    mock_memory_storage = AsyncMock()

    with patch(
        'assistant.services.get_memory_storage',
        return_value=mock_memory_storage,
    ):
        response = await authenticated_async_test_client.post(
            f'/api/v1/conversations/{conv_id}/messages',
            json={'content': ''},
        )

    assert response.status_code == 400


async def test_add_message_to_conversation_missing_content(
    authenticated_async_test_client,
):
    """Test that missing content field is rejected."""
    conv_id = str(uuid4())
    response = await authenticated_async_test_client.post(
        f'/api/v1/conversations/{conv_id}/messages',
        json={'temperature': 0.5},
    )
    assert response.status_code == 422


async def test_add_message_to_conversation_invalid_temperature(
    authenticated_async_test_client,
):
    """Test that invalid temperature is rejected."""
    conv_id = str(uuid4())
    response = await authenticated_async_test_client.post(
        f'/api/v1/conversations/{conv_id}/messages',
        json={'content': 'Hello', 'temperature': 2.5},  # Too high
    )
    assert response.status_code == 422  # Validation error


async def test_add_message_to_conversation_invalid_max_tokens(
    authenticated_async_test_client,
):
    """Test that invalid max_tokens is rejected."""
    conv_id = str(uuid4())
    response = await authenticated_async_test_client.post(
        f'/api/v1/conversations/{conv_id}/messages',
        json={'content': 'Hello', 'max_tokens': 0},  # Too low
    )
    assert response.status_code == 422  # Validation error


async def test_add_message_to_conversation_requires_auth(async_test_client):
    """Test that add_message_to_conversation requires authentication."""
    conv_id = str(uuid4())
    response = await async_test_client.post(
        f'/api/v1/conversations/{conv_id}/messages',
        json={'content': 'Hello'},
    )
    assert response.status_code == 401


async def test_add_message_to_conversation_llm_failure(
    authenticated_async_test_client,
):
    """Test handling of LLM service failure when adding a message."""
    conv_id = str(uuid4())
    mock_service = AsyncMock()
    mock_service.add_message_to_conversation = AsyncMock(
        side_effect=HTTPException(
            status_code=503, detail='LLM service unavailable'
        )
    )

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            f'/api/v1/conversations/{conv_id}/messages',
            json={'content': 'Hello'},
        )

    assert response.status_code == 503
    assert 'unavailable' in response.json()['detail'].lower()


# ============================================================================
# Background Tasks Routing Tests
# ============================================================================


async def test_create_conversation_with_message_passes_background_tasks(
    authenticated_async_test_client,
):
    """Test that create_conversation_with_message passes BackgroundTasks to service."""
    mock_response = {
        'conversation': {
            'id': str(uuid4()),
            'title': 'New Conversation',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
        },
        'user_message': {
            'id': str(uuid4()),
            'role': 'user',
            'content': 'Hello',
            'sequence_number': 1,
            'created_at': '2024-01-01T00:00:00Z',
            'error': None,
            'annotations': None,
        },
        'assistant_message': {
            'id': str(uuid4()),
            'role': 'assistant',
            'content': 'Hi!',
            'sequence_number': 2,
            'created_at': '2024-01-01T00:00:00Z',
            'error': None,
            'annotations': None,
        },
    }

    mock_service = AsyncMock()
    mock_service.create_conversation_with_message = AsyncMock(
        return_value=mock_response
    )

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            '/api/v1/conversations/with-message',
            json={'content': 'Hello', 'temperature': 0.7, 'max_tokens': 100},
        )

    assert response.status_code == 201

    # Verify service was called with background_tasks parameter
    assert mock_service.create_conversation_with_message.called
    call_kwargs = mock_service.create_conversation_with_message.call_args[1]
    assert 'background_tasks' in call_kwargs
    assert call_kwargs['background_tasks'] is not None


async def test_add_message_to_conversation_passes_background_tasks(
    authenticated_async_test_client,
):
    """Test that add_message_to_conversation passes BackgroundTasks to service."""
    conv_id = str(uuid4())

    mock_response = {
        'conversation': {
            'id': conv_id,
            'title': 'Test Conversation',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
        },
        'user_message': {
            'id': str(uuid4()),
            'role': 'user',
            'content': 'Follow-up',
            'sequence_number': 3,
            'created_at': '2024-01-01T00:00:00Z',
            'error': None,
            'annotations': None,
        },
        'assistant_message': {
            'id': str(uuid4()),
            'role': 'assistant',
            'content': 'Response',
            'sequence_number': 4,
            'created_at': '2024-01-01T00:00:00Z',
            'error': None,
            'annotations': None,
        },
    }

    mock_service = AsyncMock()
    mock_service.add_message_to_conversation = AsyncMock(
        return_value=mock_response
    )

    with patch(
        'assistant.routers.conversations.get_conversation_service',
        return_value=mock_service,
    ):
        response = await authenticated_async_test_client.post(
            f'/api/v1/conversations/{conv_id}/messages',
            json={
                'content': 'Follow-up',
                'temperature': 0.7,
                'max_tokens': 100,
            },
        )

    assert response.status_code == 201

    # Verify service was called with background_tasks parameter
    assert mock_service.add_message_to_conversation.called
    call_kwargs = mock_service.add_message_to_conversation.call_args[1]
    assert 'background_tasks' in call_kwargs
    assert call_kwargs['background_tasks'] is not None
