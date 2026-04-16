"""Tests for MemoryStorage."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

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


# Postgres-backed upsert tests


@pytest_asyncio.fixture
async def async_db_session():
    """Create an async SQLite session for Postgres upsert tests."""
    import os
    import tempfile

    # Create a temporary directory for the test database
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test.db')
    db_url = f'sqlite+aiosqlite:///{db_path}'

    engine = create_async_engine(
        db_url,
        echo=False,
        connect_args={'check_same_thread': False, 'timeout': 30},
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        await session.begin()
        yield session
        try:
            await session.rollback()
        except Exception:
            pass

    await engine.dispose()
    # Cleanup
    try:
        os.remove(db_path)
        os.rmdir(temp_dir)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_upsert_conversation_summary_creates_new(
    memory_storage, async_db_session
):
    """Create a new summary with version=1 when none exists."""

    conv_id = uuid.uuid4()
    user_id = 'user@example.com'
    summary_text = 'This is a test summary'
    source_msg_id = uuid.uuid4()

    result = await memory_storage.upsert_conversation_summary(
        session=async_db_session,
        conversation_id=conv_id,
        user_id=user_id,
        summary_text=summary_text,
        source_message_id=source_msg_id,
    )
    await async_db_session.commit()

    assert result.conversation_id == conv_id
    assert result.user_id == user_id
    assert result.summary_text == summary_text
    assert result.source_message_id == source_msg_id
    assert result.version == 1
    assert result.created_at is not None
    assert result.updated_at is not None

    # Verify it can be queried back
    await async_db_session.refresh(result)
    assert result.version == 1


@pytest.mark.asyncio
async def test_upsert_conversation_summary_retry_safe_on_identical(
    memory_storage, async_db_session
):
    """Identical content can be retried safely (no error, deterministic)."""

    conv_id = uuid.uuid4()
    user_id = 'user@example.com'
    summary_text = 'This is a test summary'
    source_msg_id = uuid.uuid4()

    # First upsert
    first = await memory_storage.upsert_conversation_summary(
        session=async_db_session,
        conversation_id=conv_id,
        user_id=user_id,
        summary_text=summary_text,
        source_message_id=source_msg_id,
    )
    await async_db_session.commit()
    first_id = first.id

    # Second upsert with identical content - should not error
    # With atomic upserts, version will increment even on identical content
    # This is acceptable as long as it's deterministic and doesn't error
    second = await memory_storage.upsert_conversation_summary(
        session=async_db_session,
        conversation_id=conv_id,
        user_id=user_id,
        summary_text=summary_text,
        source_message_id=source_msg_id,
    )

    await async_db_session.commit()
    # Same row ID (not a duplicate)
    assert second.id == first_id
    # Content unchanged
    assert second.summary_text == summary_text
    assert second.source_message_id == source_msg_id


@pytest.mark.asyncio
async def test_upsert_conversation_summary_updates_and_increments_version(
    memory_storage, async_db_session
):
    """Changed summary updates in place and increments version."""
    conv_id = uuid.uuid4()
    user_id = 'user@example.com'
    source_msg_id = uuid.uuid4()

    # First upsert
    first = await memory_storage.upsert_conversation_summary(
        session=async_db_session,
        conversation_id=conv_id,
        user_id=user_id,
        summary_text='Original summary',
        source_message_id=source_msg_id,
    )
    await async_db_session.commit()
    first_id = first.id
    first_version = first.version

    # Second upsert with different summary
    second = await memory_storage.upsert_conversation_summary(
        session=async_db_session,
        conversation_id=conv_id,
        user_id=user_id,
        summary_text='Updated summary',
        source_message_id=source_msg_id,
    )

    await async_db_session.commit()
    assert second.id == first_id
    assert second.version == first_version + 1
    assert second.summary_text == 'Updated summary'


@pytest.mark.asyncio
async def test_upsert_durable_fact_creates_new(
    memory_storage, async_db_session
):
    """Create a new durable fact when none exists."""
    from assistant.models.memory_sql import (
        DurableFactConfidence,
        DurableFactSourceType,
    )

    user_id = 'user@example.com'
    subject = 'John Doe'
    fact_text = 'John works at Acme Corp'

    result = await memory_storage.upsert_durable_fact(
        session=async_db_session,
        user_id=user_id,
        subject=subject,
        fact_text=fact_text,
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        fact_key='employment_status',
    )
    await async_db_session.commit()

    assert result.user_id == user_id
    assert result.subject == subject
    assert result.fact_text == fact_text
    assert result.fact_key == 'employment_status'
    assert result.confidence == DurableFactConfidence.HIGH
    assert result.source_type == DurableFactSourceType.CONVERSATION
    assert result.active is True


@pytest.mark.asyncio
async def test_upsert_durable_fact_per_user_isolation(
    memory_storage, async_db_session
):
    """Facts are isolated per user."""
    from assistant.models.memory_sql import (
        DurableFactConfidence,
        DurableFactSourceType,
    )

    subject = 'Alice'
    fact_text = 'Likes programming'
    fact_key = 'hobby'

    # User 1 creates fact
    user1_fact = await memory_storage.upsert_durable_fact(
        session=async_db_session,
        user_id='user1@example.com',
        subject=subject,
        fact_text=fact_text,
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        fact_key=fact_key,
    )
    await async_db_session.commit()

    # User 2 creates different fact with same fact_key
    user2_fact = await memory_storage.upsert_durable_fact(
        session=async_db_session,
        user_id='user2@example.com',
        subject=subject,
        fact_text='Does not like programming',  # Different
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        fact_key=fact_key,
    )

    # Facts should be different
    assert user1_fact.id != user2_fact.id
    assert user1_fact.fact_text != user2_fact.fact_text
    assert user1_fact.user_id != user2_fact.user_id


@pytest.mark.asyncio
async def test_upsert_durable_fact_only_dedupes_active(
    memory_storage, async_db_session
):
    """Deduplication only matches active facts."""
    from assistant.models.memory_sql import (
        DurableFactConfidence,
        DurableFactSourceType,
    )

    user_id = 'user@example.com'
    fact_key = 'favorite_color'

    # Create first fact
    first = await memory_storage.upsert_durable_fact(
        session=async_db_session,
        user_id=user_id,
        subject='Color preference',
        fact_text='Blue',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.USER_EXPLICIT,
        fact_key=fact_key,
    )
    await async_db_session.commit()

    # Mark it as inactive
    first.active = False
    await async_db_session.flush()
    await async_db_session.commit()

    # Upsert attempt with same fact_key should create new (since old is inactive)
    second = await memory_storage.upsert_durable_fact(
        session=async_db_session,
        user_id=user_id,
        subject='Color preference',
        fact_text='Red',  # Different
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.USER_EXPLICIT,
        fact_key=fact_key,
    )

    assert second.id != first.id
    assert second.active is True
    assert second.fact_text == 'Red'
