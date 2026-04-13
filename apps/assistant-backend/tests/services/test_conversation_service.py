"""Tests for ConversationService."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import uuid

from fastapi import HTTPException
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from assistant.models.conversation import (
    ConversationWithMessagesResponse,
    CreateConversationWithMessageRequest,
    CreateMessageRequest,
)
from assistant.models.conversation_sql import Conversation, Message
from assistant.models.llm import (
    LLMCompletionError,
    LLMCompletionErrorKind,
    LLMCompletionResult,
)
from assistant.services.context_assembly import (
    ContextAssemblyResult,
    ContextAssemblyService,
)
from assistant.services.conversation_service import ConversationService
from assistant.services.llm_service import LLMService
from assistant.services.memory_storage import MemoryStorage

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_async_engine(
        'sqlite+aiosqlite:///:memory:',
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service."""
    return AsyncMock(spec=LLMService)


@pytest.fixture
def mock_memory_storage():
    """Create a mock MemoryStorage."""
    return AsyncMock(spec=MemoryStorage)


@pytest.fixture
def mock_context_assembly():
    """Create a mock ContextAssemblyService."""
    return AsyncMock(spec=ContextAssemblyService)


@pytest.fixture
def conversation_service(
    mock_llm_service, mock_memory_storage, mock_context_assembly
):
    """Create a ConversationService with mocked dependencies."""
    return ConversationService(
        llm_service=mock_llm_service,
        memory_storage=mock_memory_storage,
        context_assembly=mock_context_assembly,
    )


@pytest.fixture
def test_user_id():
    """Generate a test user ID."""
    return str(uuid.uuid4())


@pytest.fixture
def valid_request():
    """Create a valid conversation request."""
    return CreateConversationWithMessageRequest(
        content='Hello, how are you?',
        temperature=0.7,
        max_tokens=512,
    )


@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response."""
    return LLMCompletionResult(
        content='I am doing well, thank you!',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=15,
        total_tokens=25,
        tool_calls=None,
        finish_reason='stop',
    )


@pytest.fixture
def mock_context_result():
    """Create a mock context assembly result for new conversation."""
    return ContextAssemblyResult(
        messages=[{'role': 'user', 'content': 'Hello, how are you?'}],
        used_summary=False,
        summary_id=None,
        fact_ids=[],
        chroma_used=False,
    )


async def test_create_conversation_with_message_success(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
    valid_request,
    mock_llm_response,
    mock_context_result,
):
    """It creates a conversation with user and assistant messages."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.return_value = mock_llm_response

    result = await conversation_service.create_conversation_with_message(
        session=async_session,
        user_id=test_user_id,
        payload=valid_request,
    )

    # Verify the response structure
    assert isinstance(result, ConversationWithMessagesResponse)
    assert result.conversation.title == 'Hello, how are you?'
    assert result.user_message.content == 'Hello, how are you?'
    assert result.user_message.role == 'user'
    assert result.user_message.sequence_number == 1
    assert result.assistant_message.content == 'I am doing well, thank you!'
    assert result.assistant_message.role == 'assistant'
    assert result.assistant_message.sequence_number == 2

    # Verify context assembly was called
    mock_context_assembly.assemble_context_new_conversation.assert_called_once()

    # Verify LLM service was called correctly
    mock_llm_service.complete_messages.assert_called_once()
    call_kwargs = mock_llm_service.complete_messages.call_args.kwargs
    assert call_kwargs['model'] is not None
    assert call_kwargs['temperature'] == 0.7
    assert call_kwargs['max_tokens'] == 512
    # Messages should have system message + context assembly messages
    assert len(call_kwargs['messages']) == 2  # system + user
    assert call_kwargs['messages'][0]['role'] == 'system'
    assert call_kwargs['messages'][1] == mock_context_result.messages[0]

    # Verify data was saved to database
    # Re-query to ensure persistence

    stmt = select(Conversation).where(Conversation.id == result.conversation.id)
    db_result = await async_session.execute(stmt)
    db_conversation = db_result.scalar_one()
    assert db_conversation.user_id == test_user_id
    assert db_conversation.title == 'Hello, how are you?'

    stmt = (
        select(Message)
        .where(Message.conversation_id == db_conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    db_result = await async_session.execute(stmt)
    db_messages = list(db_result.scalars().all())
    assert len(db_messages) == 2
    assert db_messages[0].role == 'user'
    assert db_messages[1].role == 'assistant'


async def test_create_conversation_with_message_empty_content(
    conversation_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when content is empty."""
    request = CreateConversationWithMessageRequest(
        content='   ',  # Only whitespace
        temperature=0.7,
        max_tokens=512,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=request,
        )

    assert exc_info.value.status_code == 400
    assert 'empty' in exc_info.value.detail.lower()


async def test_create_conversation_with_message_llm_timeout(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM times out."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.timeout,
        message='LLM request timed out',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 504
    assert 'timed out' in exc_info.value.detail.lower()

    stmt = select(Conversation)
    result = await async_session.execute(stmt)
    conversations = list(result.scalars().all())
    # We save the conversation anyway.
    assert len(conversations) == 1


async def test_create_conversation_with_message_llm_connection_error(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM connection fails."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.unreachable,
        message='Failed to reach LLM backend',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 502
    assert 'failed to reach' in exc_info.value.detail.lower()


async def test_create_conversation_with_message_llm_http_error(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM returns HTTP error."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.backend_error,
        message='LLM backend returned an error',
        backend_status_code=500,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 502
    assert 'error' in str(exc_info.value.detail).lower()


async def test_create_conversation_with_message_invalid_llm_response(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM response is invalid."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    # Return an invalid response structure
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.invalid_response,
        message='LLM response has unexpected response shape',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 502
    assert 'unexpected response' in exc_info.value.detail.lower()


async def test_create_conversation_with_message_empty_choices(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM returns no choices."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.invalid_response,
        message='LLM backend did not return any choices',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 502
    assert 'did not return any choices' in exc_info.value.detail.lower()


async def test_create_conversation_with_message_long_content_title(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_llm_response,
    mock_context_assembly,
    mock_context_result,
):
    """It truncates long messages for conversation title."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    long_content = 'A' * 100  # More than 60 characters
    request = CreateConversationWithMessageRequest(
        content=long_content,
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.return_value = mock_llm_response

    result = await conversation_service.create_conversation_with_message(
        session=async_session,
        user_id=test_user_id,
        payload=request,
    )

    # Title should be truncated to 60 characters
    assert len(result.conversation.title) == 60
    assert result.conversation.title == 'A' * 60


async def test_create_conversation_with_message_empty_assistant_content(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It handles empty assistant content gracefully."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.return_value = LLMCompletionResult(
        content='',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=0,
        total_tokens=10,
        tool_calls=None,
        finish_reason='stop',
    )

    result = await conversation_service.create_conversation_with_message(
        session=async_session,
        user_id=test_user_id,
        payload=valid_request,
    )

    # Should handle None content by converting to empty string
    assert result.assistant_message.content == ''


# Tests for list_conversations


async def test_list_conversations_empty(
    conversation_service,
    async_session,
    test_user_id,
):
    """It returns an empty list when user has no conversations."""
    result = await conversation_service.list_conversations(
        session=async_session,
        user_id=test_user_id,
    )

    assert result.items == []


async def test_list_conversations_single(
    conversation_service,
    async_session,
    test_user_id,
):
    """It returns a single conversation for the user."""
    # Create a conversation
    conversation = Conversation(
        user_id=test_user_id,
        title='Test Conversation',
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    result = await conversation_service.list_conversations(
        session=async_session,
        user_id=test_user_id,
    )

    assert len(result.items) == 1
    assert result.items[0].id == conversation.id
    assert result.items[0].title == 'Test Conversation'
    assert result.items[0].created_at == conversation.created_at
    assert result.items[0].updated_at == conversation.updated_at


async def test_list_conversations_multiple_ordered(
    conversation_service,
    async_session,
    test_user_id,
):
    """It returns multiple conversations ordered by updated_at descending."""

    base_time = datetime.now(timezone.utc)

    conversation1 = Conversation(
        user_id=test_user_id,
        title='Oldest Conversation',
        created_at=base_time,
        updated_at=base_time,
    )
    async_session.add(conversation1)
    await async_session.commit()

    conversation2 = Conversation(
        user_id=test_user_id,
        title='Middle Conversation',
        created_at=base_time + timedelta(seconds=1),
        updated_at=base_time + timedelta(seconds=1),
    )
    async_session.add(conversation2)
    await async_session.commit()

    conversation3 = Conversation(
        user_id=test_user_id,
        title='Newest Conversation',
        created_at=base_time + timedelta(seconds=2),
        updated_at=base_time + timedelta(seconds=2),
    )
    async_session.add(conversation3)
    await async_session.commit()

    result = await conversation_service.list_conversations(
        session=async_session,
        user_id=test_user_id,
    )

    assert len(result.items) == 3
    # Should be ordered by updated_at desc (newest first)
    assert result.items[0].title == 'Newest Conversation'
    assert result.items[1].title == 'Middle Conversation'
    assert result.items[2].title == 'Oldest Conversation'


async def test_list_conversations_user_isolation(
    conversation_service,
    async_session,
    test_user_id,
):
    """It only returns conversations for the specified user."""
    other_user_id = str(uuid.uuid4())

    # Create conversations for two different users
    user1_conversation = Conversation(
        user_id=test_user_id,
        title='User 1 Conversation',
    )
    async_session.add(user1_conversation)

    user2_conversation = Conversation(
        user_id=other_user_id,
        title='User 2 Conversation',
    )
    async_session.add(user2_conversation)

    await async_session.commit()

    # Query for user 1
    result = await conversation_service.list_conversations(
        session=async_session,
        user_id=test_user_id,
    )

    assert len(result.items) == 1
    assert result.items[0].title == 'User 1 Conversation'
    assert result.items[0].id == user1_conversation.id

    # Query for user 2
    result2 = await conversation_service.list_conversations(
        session=async_session,
        user_id=other_user_id,
    )

    assert len(result2.items) == 1
    assert result2.items[0].title == 'User 2 Conversation'
    assert result2.items[0].id == user2_conversation.id


async def test_list_conversations_with_messages(
    conversation_service,
    async_session,
    test_user_id,
):
    """It returns conversations even when they have messages."""
    # Create a conversation with messages
    conversation = Conversation(
        user_id=test_user_id,
        title='Conversation with Messages',
    )
    async_session.add(conversation)
    await async_session.flush()

    message1 = Message(
        conversation_id=conversation.id,
        role='user',
        content='Hello',
        sequence_number=1,
    )
    async_session.add(message1)

    message2 = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='Hi there!',
        sequence_number=2,
    )
    async_session.add(message2)

    await async_session.commit()
    await async_session.refresh(conversation)

    result = await conversation_service.list_conversations(
        session=async_session,
        user_id=test_user_id,
    )

    assert len(result.items) == 1
    assert result.items[0].id == conversation.id
    assert result.items[0].title == 'Conversation with Messages'


# Tests for get_conversation_messages


async def test_get_conversation_messages_success(
    conversation_service,
    async_session,
    test_user_id,
):
    """It returns conversation and its messages."""
    # Create a conversation with messages
    conversation = Conversation(
        user_id=test_user_id,
        title='Test Conversation',
    )
    async_session.add(conversation)
    await async_session.flush()

    message1 = Message(
        conversation_id=conversation.id,
        role='user',
        content='Hello, assistant!',
        sequence_number=1,
    )
    async_session.add(message1)

    message2 = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='Hello! How can I help you?',
        sequence_number=2,
    )
    async_session.add(message2)

    message3 = Message(
        conversation_id=conversation.id,
        role='user',
        content='Tell me about Python',
        sequence_number=3,
    )
    async_session.add(message3)

    await async_session.commit()
    await async_session.refresh(conversation)

    result = await conversation_service.get_conversation_messages(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
    )

    # Verify conversation summary
    assert result.conversation.id == conversation.id
    assert result.conversation.title == 'Test Conversation'

    # Verify messages
    assert len(result.items) == 3
    assert result.items[0].content == 'Hello, assistant!'
    assert result.items[0].role == 'user'
    assert result.items[0].sequence_number == 1
    assert result.items[1].content == 'Hello! How can I help you?'
    assert result.items[1].role == 'assistant'
    assert result.items[1].sequence_number == 2
    assert result.items[2].content == 'Tell me about Python'
    assert result.items[2].role == 'user'
    assert result.items[2].sequence_number == 3


async def test_get_conversation_messages_empty(
    conversation_service,
    async_session,
    test_user_id,
):
    """It returns conversation with empty message list."""
    # Create a conversation without messages
    conversation = Conversation(
        user_id=test_user_id,
        title='Empty Conversation',
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    result = await conversation_service.get_conversation_messages(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
    )

    assert result.conversation.id == conversation.id
    assert result.conversation.title == 'Empty Conversation'
    assert result.items == []


async def test_get_conversation_messages_not_found(
    conversation_service,
    async_session,
    test_user_id,
):
    """It raises HTTPException when conversation doesn't exist."""
    non_existent_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.get_conversation_messages(
            session=async_session,
            user_id=test_user_id,
            conversation_id=non_existent_id,
        )

    assert exc_info.value.status_code == 404
    assert 'not found' in exc_info.value.detail.lower()


async def test_get_conversation_messages_wrong_user(
    conversation_service,
    async_session,
    test_user_id,
):
    """It raises HTTPException when user doesn't own the conversation."""
    other_user_id = str(uuid.uuid4())

    # Create a conversation for a different user
    conversation = Conversation(
        user_id=other_user_id,
        title='Other User Conversation',
    )
    async_session.add(conversation)
    await async_session.commit()

    # Try to access with wrong user
    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.get_conversation_messages(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
        )

    assert exc_info.value.status_code == 404
    assert 'not found' in exc_info.value.detail.lower()


async def test_get_conversation_messages_ordered_by_sequence(
    conversation_service,
    async_session,
    test_user_id,
):
    """It returns messages ordered by sequence_number ascending."""
    conversation = Conversation(
        user_id=test_user_id,
        title='Order Test',
    )
    async_session.add(conversation)
    await async_session.flush()

    # Add messages in random order
    message3 = Message(
        conversation_id=conversation.id,
        role='user',
        content='Third message',
        sequence_number=3,
    )
    async_session.add(message3)

    message1 = Message(
        conversation_id=conversation.id,
        role='user',
        content='First message',
        sequence_number=1,
    )
    async_session.add(message1)

    message2 = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='Second message',
        sequence_number=2,
    )
    async_session.add(message2)

    await async_session.commit()

    result = await conversation_service.get_conversation_messages(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
    )

    # Verify messages are ordered by sequence_number
    assert len(result.items) == 3
    assert result.items[0].sequence_number == 1
    assert result.items[0].content == 'First message'
    assert result.items[1].sequence_number == 2
    assert result.items[1].content == 'Second message'
    assert result.items[2].sequence_number == 3
    assert result.items[2].content == 'Third message'


async def test_get_conversation_messages_with_error_field(
    conversation_service,
    async_session,
    test_user_id,
):
    """It includes error field in messages when present."""
    conversation = Conversation(
        user_id=test_user_id,
        title='Error Test',
    )
    async_session.add(conversation)
    await async_session.flush()

    message_with_error = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='',
        sequence_number=1,
        error='LLM backend timeout',
    )
    async_session.add(message_with_error)

    await async_session.commit()

    result = await conversation_service.get_conversation_messages(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
    )

    assert len(result.items) == 1
    assert result.items[0].error == 'LLM backend timeout'
    assert result.items[0].content == ''


# Tests for add_message_to_conversation


async def test_add_message_to_conversation_success(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_llm_response,
    mock_context_assembly,
    mock_context_result,
):
    """It adds a message to an existing conversation."""
    mock_context_assembly.assemble_context.return_value = mock_context_result
    # Create a conversation with initial messages
    conversation = Conversation(
        user_id=test_user_id,
        title='Existing Conversation',
    )
    async_session.add(conversation)
    await async_session.flush()

    message1 = Message(
        conversation_id=conversation.id,
        role='user',
        content='Hello',
        sequence_number=1,
    )
    async_session.add(message1)

    message2 = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='Hi there!',
        sequence_number=2,
    )
    async_session.add(message2)

    await async_session.commit()
    await async_session.refresh(conversation)

    original_updated_at = conversation.updated_at

    # Add a new message
    payload = CreateMessageRequest(
        content='How are you?',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.return_value = mock_llm_response

    result = await conversation_service.add_message_to_conversation(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    )

    # Verify the response
    assert result.user_message.content == 'How are you?'
    assert result.user_message.sequence_number == 3
    assert result.user_message.role == 'user'
    assert result.assistant_message.content == 'I am doing well, thank you!'
    assert result.assistant_message.sequence_number == 4
    assert result.assistant_message.role == 'assistant'

    # Verify LLM was called with all messages
    mock_llm_service.complete_messages.assert_called_once()
    call_kwargs = mock_llm_service.complete_messages.call_args.kwargs
    # Should have system message + context assembly messages
    assert len(call_kwargs['messages']) == 2  # system + user
    assert call_kwargs['messages'][0]['role'] == 'system'
    assert call_kwargs['messages'][1] == mock_context_result.messages[0]

    # Verify messages were saved to database
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    db_result = await async_session.execute(stmt)
    all_messages = list(db_result.scalars().all())
    assert len(all_messages) == 4
    assert all_messages[2].content == 'How are you?'
    assert all_messages[3].content == 'I am doing well, thank you!'

    # Verify updated_at was updated
    await async_session.refresh(conversation)
    assert conversation.updated_at >= original_updated_at


async def test_add_message_to_conversation_empty_content(
    conversation_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when content is empty."""

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='   ',  # Only whitespace
        temperature=0.7,
        max_tokens=512,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 400
    assert 'empty' in exc_info.value.detail.lower()


async def test_add_message_to_conversation_not_found(
    conversation_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when conversation doesn't exist."""

    non_existent_id = uuid.uuid4()
    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=non_existent_id,
            payload=payload,
        )

    assert exc_info.value.status_code == 404
    assert 'not found' in exc_info.value.detail.lower()


async def test_add_message_to_conversation_wrong_user(
    conversation_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when user doesn't own the conversation."""

    other_user_id = str(uuid.uuid4())

    conversation = Conversation(
        user_id=other_user_id,
        title='Other User Conversation',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 404
    assert 'not found' in exc_info.value.detail.lower()


async def test_add_message_to_conversation_with_no_existing_messages(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_llm_response,
    mock_context_assembly,
    mock_context_result,
):
    """It handles adding a message to a conversation with no messages."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Empty Conversation',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='First message',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.return_value = mock_llm_response

    result = await conversation_service.add_message_to_conversation(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    )

    # Should start sequence numbers at 1
    assert result.user_message.sequence_number == 1
    assert result.assistant_message.sequence_number == 2


async def test_add_message_to_conversation_llm_timeout(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM times out."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.timeout,
        message='LLM request timed out',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 504
    assert 'timed out' in exc_info.value.detail.lower()


async def test_add_message_to_conversation_llm_connection_error(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM connection fails."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.unreachable,
        message='Failed to reach LLM backend',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 502
    assert 'failed to reach' in exc_info.value.detail.lower()


async def test_add_message_to_conversation_llm_http_error(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM returns HTTP error."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.backend_error,
        message='LLM backend returned an error',
        backend_status_code=500,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 502
    assert 'error' in str(exc_info.value.detail).lower()


async def test_add_message_to_conversation_invalid_llm_response(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM response is invalid."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.invalid_response,
        message='LLM response has unexpected response shape',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 502
    assert 'unexpected response' in exc_info.value.detail.lower()


async def test_add_message_to_conversation_empty_llm_choices(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM returns no choices."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.invalid_response,
        message='LLM backend did not return any choices',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 502
    assert 'did not return any choices' in exc_info.value.detail.lower()
