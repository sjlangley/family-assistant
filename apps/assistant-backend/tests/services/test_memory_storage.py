"""Tests for MemoryStorage."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch
import uuid

import pytest

from assistant.services.memory_storage import MemoryStorage


@pytest.fixture
def mock_collection():
    """Create a mock ChromaDB collection."""
    return MagicMock()


@pytest.fixture
def memory_storage(mock_collection):
    """Create a MemoryStorage instance with mocked internals."""
    # Create a real MemoryStorage instance but mock the chromadb client
    # to prevent actual HTTP connections
    mock_client = Mock()
    mock_client.get_or_create_collection.return_value = mock_collection

    with patch(
        'assistant.services.memory_storage.chromadb.HttpClient'
    ) as mock_http_client:
        mock_http_client.return_value = mock_client
        storage = MemoryStorage(
            chroma_host='localhost',
            chroma_port=8000,
            collection_name='test_collection',
        )

    return storage


@pytest.fixture
def test_conversation_id():
    """Generate a test conversation ID."""
    return str(uuid.uuid4())


@pytest.fixture
def test_user_id():
    """Generate a test user ID."""
    return str(uuid.uuid4())


def test_init_creates_client_and_collection():
    """It initializes ChromaDB client and gets or creates collection."""
    with patch(
        'assistant.services.memory_storage.chromadb.HttpClient'
    ) as mock_http_client:
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_http_client.return_value = mock_client
        mock_client.get_or_create_collection.return_value = mock_collection

        storage = MemoryStorage(
            chroma_host='test-host',
            chroma_port=9000,
            collection_name='my_collection',
        )

        # Verify client was created with correct parameters
        mock_http_client.assert_called_once_with(host='test-host', port=9000)

        # Verify collection was retrieved/created
        mock_client.get_or_create_collection.assert_called_once_with(
            name='my_collection'
        )

        assert storage.client == mock_client
        assert storage.collection == mock_collection


def test_add_memory_success(
    memory_storage,
    mock_collection,
    test_conversation_id,
    test_user_id,
):
    """It adds a memory entry with correct parameters."""
    content = 'This is a test message'
    role = 'user'

    with (
        patch('assistant.services.memory_storage.uuid.uuid4') as mock_uuid,
        patch('assistant.services.memory_storage.utc_now') as mock_utc_now,
    ):
        mock_id = uuid.UUID('12345678-1234-5678-1234-567812345678')
        mock_uuid.return_value = mock_id

        mock_timestamp = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
        mock_utc_now.return_value = mock_timestamp

        memory_storage.add_memory(
            conversation_id=test_conversation_id,
            user_id=test_user_id,
            content=content,
            role=role,
        )

        # Verify collection.add was called with correct parameters
        mock_collection.add.assert_called_once_with(
            ids=[str(mock_id)],
            documents=[content],
            metadatas=[
                {
                    'conversation_id': test_conversation_id,
                    'user_id': test_user_id,
                    'role': role,
                    'timestamp': mock_timestamp.isoformat(),
                }
            ],
        )


def test_add_memory_with_default_role(
    memory_storage,
    mock_collection,
    test_conversation_id,
    test_user_id,
):
    """It uses 'user' as the default role when not specified."""
    content = 'Test message without role'

    with (
        patch('assistant.services.memory_storage.uuid.uuid4') as mock_uuid,
        patch('assistant.services.memory_storage.utc_now') as mock_utc_now,
    ):
        mock_id = uuid.UUID('12345678-1234-5678-1234-567812345678')
        mock_uuid.return_value = mock_id

        mock_timestamp = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
        mock_utc_now.return_value = mock_timestamp

        memory_storage.add_memory(
            conversation_id=test_conversation_id,
            user_id=test_user_id,
            content=content,
        )

        # Verify role defaults to 'user'
        call_args = mock_collection.add.call_args
        assert call_args[1]['metadatas'][0]['role'] == 'user'


def test_add_memory_with_assistant_role(
    memory_storage,
    mock_collection,
    test_conversation_id,
    test_user_id,
):
    """It correctly sets the assistant role."""
    content = 'This is an assistant response'
    role = 'assistant'

    with (
        patch('assistant.services.memory_storage.uuid.uuid4') as mock_uuid,
        patch('assistant.services.memory_storage.utc_now') as mock_utc_now,
    ):
        mock_id = uuid.UUID('87654321-4321-8765-4321-876543218765')
        mock_uuid.return_value = mock_id

        mock_timestamp = datetime(2026, 3, 17, 13, 30, 0, tzinfo=timezone.utc)
        mock_utc_now.return_value = mock_timestamp

        memory_storage.add_memory(
            conversation_id=test_conversation_id,
            user_id=test_user_id,
            content=content,
            role=role,
        )

        # Verify role is set to 'assistant'
        call_args = mock_collection.add.call_args
        assert call_args[1]['metadatas'][0]['role'] == 'assistant'


def test_add_memory_generates_unique_id(
    memory_storage,
    mock_collection,
    test_conversation_id,
    test_user_id,
):
    """It generates a unique UUID for each memory entry."""
    with (
        patch('assistant.services.memory_storage.uuid.uuid4') as mock_uuid,
        patch('assistant.services.memory_storage.utc_now') as mock_utc_now,
    ):
        # Setup mocks
        mock_id_1 = uuid.UUID('11111111-1111-1111-1111-111111111111')
        mock_id_2 = uuid.UUID('22222222-2222-2222-2222-222222222222')
        mock_uuid.side_effect = [mock_id_1, mock_id_2]

        mock_timestamp = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
        mock_utc_now.return_value = mock_timestamp

        # Add first memory
        memory_storage.add_memory(
            conversation_id=test_conversation_id,
            user_id=test_user_id,
            content='First message',
        )

        # Add second memory
        memory_storage.add_memory(
            conversation_id=test_conversation_id,
            user_id=test_user_id,
            content='Second message',
        )

        # Verify different IDs were used
        first_call_id = mock_collection.add.call_args_list[0][1]['ids'][0]
        second_call_id = mock_collection.add.call_args_list[1][1]['ids'][0]

        assert first_call_id == str(mock_id_1)
        assert second_call_id == str(mock_id_2)
        assert first_call_id != second_call_id


def test_query_memory_success(
    memory_storage,
    mock_collection,
    test_user_id,
):
    """It queries memory with correct parameters and returns results."""
    query = 'What did we discuss about Python?'
    expected_documents = ['doc1', 'doc2', 'doc3']
    mock_results = {
        'ids': [['id1', 'id2', 'id3']],
        'documents': [expected_documents],
        'metadatas': [
            [
                {
                    'user_id': test_user_id,
                    'role': 'user',
                    'timestamp': '2026-03-17T10:00:00+00:00',
                },
                {
                    'user_id': test_user_id,
                    'role': 'assistant',
                    'timestamp': '2026-03-17T10:01:00+00:00',
                },
                {
                    'user_id': test_user_id,
                    'role': 'user',
                    'timestamp': '2026-03-17T10:02:00+00:00',
                },
            ]
        ],
        'distances': [[0.1, 0.2, 0.3]],
    }

    mock_collection.query.return_value = mock_results

    results = memory_storage.query_memory(
        user_id=test_user_id,
        query=query,
    )

    # Verify collection.query was called with correct parameters
    mock_collection.query.assert_called_once_with(
        query_texts=[query],
        n_results=5,
        where={'user_id': test_user_id},
        include=['documents'],
    )

    # Verify results are returned correctly
    assert results == expected_documents


def test_query_memory_filters_by_user_id(
    memory_storage,
    mock_collection,
    test_user_id,
):
    """It filters query results by user_id."""
    query = 'Test query'

    memory_storage.query_memory(
        user_id=test_user_id,
        query=query,
    )

    # Verify the where clause includes user_id filter
    call_args = mock_collection.query.call_args
    assert call_args[1]['where'] == {'user_id': test_user_id}


def test_query_memory_returns_5_results(
    memory_storage,
    mock_collection,
    test_user_id,
):
    """It requests up to 5 results from ChromaDB."""
    query = 'Test query'

    memory_storage.query_memory(
        user_id=test_user_id,
        query=query,
    )

    # Verify n_results is set to 5
    call_args = mock_collection.query.call_args
    assert call_args[1]['n_results'] == 5


def test_query_memory_empty_results(
    memory_storage,
    mock_collection,
    test_user_id,
):
    """It handles empty query results correctly."""
    query = 'Non-existent topic'
    mock_empty_results = {
        'ids': [[]],
        'documents': [[]],
        'metadatas': [[]],
        'distances': [[]],
    }

    mock_collection.query.return_value = mock_empty_results

    results = memory_storage.query_memory(
        user_id=test_user_id,
        query=query,
    )

    assert results == []


def test_query_memory_with_different_user_ids(
    memory_storage,
    mock_collection,
):
    """It uses different user_id filters for different queries."""
    user_id_1 = str(uuid.uuid4())
    user_id_2 = str(uuid.uuid4())
    query = 'Same query'

    mock_collection.query.return_value = {
        'ids': [[]],
        'documents': [[]],
        'metadatas': [[]],
        'distances': [[]],
    }

    # Query with first user
    memory_storage.query_memory(user_id=user_id_1, query=query)

    # Query with second user
    memory_storage.query_memory(user_id=user_id_2, query=query)

    # Verify both calls used their respective user_ids
    assert mock_collection.query.call_count == 2

    first_call_where = mock_collection.query.call_args_list[0][1]['where']
    second_call_where = mock_collection.query.call_args_list[1][1]['where']

    assert first_call_where == {'user_id': user_id_1}
    assert second_call_where == {'user_id': user_id_2}


def test_query_memory_with_custom_n_results(
    memory_storage,
    mock_collection,
    test_user_id,
):
    """It allows customizing the number of results returned."""
    query = 'Test query'
    mock_collection.query.return_value = {
        'ids': [[]],
        'documents': [[]],
        'metadatas': [[]],
        'distances': [[]],
    }

    memory_storage.query_memory(
        user_id=test_user_id,
        query=query,
        n_results=10,
    )

    # Verify n_results parameter was passed through
    call_args = mock_collection.query.call_args
    assert call_args[1]['n_results'] == 10
