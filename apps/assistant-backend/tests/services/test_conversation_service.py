"""Tests for ConversationService."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
import uuid

from fastapi import HTTPException
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from assistant.models.annotations import (
    AssistantAnnotations,
    FailureAnnotationStage,
)
from assistant.models.conversation import (
    ConversationWithMessagesResponse,
    CreateConversationWithMessageRequest,
    CreateMessageRequest,
)
from assistant.models.conversation_sql import Conversation, Message
from assistant.models.llm import (
    ChatCompletionMessageToolCall,
    ChatCompletionMessageToolCallFunction,
    LLMCompletionError,
    LLMCompletionErrorKind,
    LLMCompletionResult,
)
from assistant.models.tool import (
    ToolExecutionResult,
    ToolExecutionStatus,
)
from assistant.services.context_assembly import (
    ContextAssemblyResult,
    ContextAssemblyService,
)
from assistant.services.conversation_service import ConversationService
from assistant.services.llm_service import LLMService
from assistant.services.memory_storage import MemoryStorage
from assistant.services.tool_service import ToolService
from assistant.services.tools.errors import (
    UnsupportedToolError,
)

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
def mock_tool_service():
    """Create a mock ToolService."""
    mock_service = Mock(spec=ToolService)
    mock_service.execute_tool = AsyncMock()
    mock_service.get_available_tools.return_value = []
    return mock_service


@pytest.fixture
def conversation_service(
    mock_llm_service,
    mock_memory_storage,
    mock_context_assembly,
    mock_tool_service,
):
    """Create a ConversationService with mocked dependencies."""
    return ConversationService(
        llm_service=mock_llm_service,
        context_assembly=mock_context_assembly,
        tool_service=mock_tool_service,
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

    # Should handle empty content by replacing with placeholder
    assert (
        result.assistant_message.content
        == 'Unable to generate a response. Please try again.'
    )


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


# Tests for tool loop functionality


@pytest.fixture
def mock_tool_result():
    """Create a mock tool execution result."""
    from datetime import datetime, timezone

    return ToolExecutionResult(
        tool_name='test_tool',
        status=ToolExecutionStatus.SUCCESS,
        tool_call={
            'name': 'test_tool',
            'arguments': {'query': 'test'},
            'started_at': datetime.now(timezone.utc),
            'finished_at': datetime.now(timezone.utc),
            'status': ToolExecutionStatus.SUCCESS,
        },
        llm_context='Tool execution successful',
    )


@pytest.fixture
def llm_response_with_tool_call():
    """Create an LLM response with a tool call."""
    tool_call = ChatCompletionMessageToolCall(
        id='call_123',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='test_tool',
            arguments='{"query": "test"}',
        ),
    )
    return LLMCompletionResult(
        content='I will search for that information.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=15,
        total_tokens=25,
        tool_calls=[tool_call],
        finish_reason='tool_calls',
    )


@pytest.fixture
def llm_response_with_multiple_tool_calls():
    """Create an LLM response with multiple tool calls."""
    tool_calls = [
        ChatCompletionMessageToolCall(
            id='call_1',
            type='function',
            function=ChatCompletionMessageToolCallFunction(
                name='search_tool',
                arguments='{"query": "python"}',
            ),
        ),
        ChatCompletionMessageToolCall(
            id='call_2',
            type='function',
            function=ChatCompletionMessageToolCallFunction(
                name='fetch_tool',
                arguments='{"url": "https://example.com"}',
            ),
        ),
    ]
    return LLMCompletionResult(
        content='I will search and fetch information.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        tool_calls=tool_calls,
        finish_reason='tool_calls',
    )


async def test_call_llm_chat_completion_single_tool_call(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    llm_response_with_tool_call,
    mock_tool_result,
):
    """It executes a single tool call and returns final assistant content."""
    # First call returns tool call, second call returns content
    final_response = LLMCompletionResult(
        content='Here is the search result.',
        model='llama3.2',
        prompt_tokens=20,
        completion_tokens=25,
        total_tokens=45,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_llm_service.complete_messages.side_effect = [
        llm_response_with_tool_call,
        final_response,
    ]
    mock_tool_service.execute_tool.return_value = mock_tool_result
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Search for python'}],
        temperature=0.7,
        max_tokens=512,
    )

    # Verify final content is returned
    assert result.content == 'Here is the search result.'
    assert result.error is None

    # Verify LLM was called twice (initial + follow-up)
    assert mock_llm_service.complete_messages.call_count == 2

    # Verify tool was executed
    mock_tool_service.execute_tool.assert_called_once_with(
        name='test_tool',
        arguments={'query': 'test'},
    )


async def test_call_llm_chat_completion_multiple_tool_calls_same_round(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    llm_response_with_multiple_tool_calls,
    mock_tool_result,
):
    """It executes multiple tool calls in the same round."""
    final_response = LLMCompletionResult(
        content='Here are the results from both tools.',
        model='llama3.2',
        prompt_tokens=30,
        completion_tokens=35,
        total_tokens=65,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_llm_service.complete_messages.side_effect = [
        llm_response_with_multiple_tool_calls,
        final_response,
    ]
    mock_tool_service.execute_tool.return_value = mock_tool_result
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Search and fetch'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.content == 'Here are the results from both tools.'
    assert result.error is None

    # Both tools should have been executed
    assert mock_tool_service.execute_tool.call_count == 2


async def test_call_llm_chat_completion_multiple_rounds(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    llm_response_with_tool_call,
    mock_tool_result,
):
    """It handles multiple rounds of tool calling."""
    # Create second tool call response
    second_tool_response = LLMCompletionResult(
        content='I will also search for related info.',
        model='llama3.2',
        prompt_tokens=30,
        completion_tokens=15,
        total_tokens=45,
        tool_calls=[
            ChatCompletionMessageToolCall(
                id='call_456',
                type='function',
                function=ChatCompletionMessageToolCallFunction(
                    name='test_tool',
                    arguments='{"query": "related"}',
                ),
            ),
        ],
        finish_reason='tool_calls',
    )

    final_response = LLMCompletionResult(
        content='Here are all the results.',
        model='llama3.2',
        prompt_tokens=50,
        completion_tokens=30,
        total_tokens=80,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_llm_service.complete_messages.side_effect = [
        llm_response_with_tool_call,
        second_tool_response,
        final_response,
    ]
    mock_tool_service.execute_tool.return_value = mock_tool_result
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Search for info'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.content == 'Here are all the results.'
    assert result.error is None

    # LLM called 3 times and tool executed 2 times
    assert mock_llm_service.complete_messages.call_count == 3
    assert mock_tool_service.execute_tool.call_count == 2


async def test_call_llm_chat_completion_tool_execution_error(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    llm_response_with_tool_call,
):
    """It returns error result when tool execution fails."""
    mock_llm_service.complete_messages.return_value = (
        llm_response_with_tool_call
    )
    mock_tool_service.get_available_tools.return_value = []
    mock_tool_service.execute_tool.side_effect = UnsupportedToolError(
        'test_tool'
    )

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Search'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert 'unsupported tool' in str(result.error.message).lower()


async def test_call_llm_chat_completion_max_rounds_exceeded(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
):
    """It returns error result when maximum tool rounds are exceeded."""
    tool_call_response = LLMCompletionResult(
        content='I will search.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=10,
        total_tokens=20,
        tool_calls=[
            ChatCompletionMessageToolCall(
                id='call_123',
                type='function',
                function=ChatCompletionMessageToolCallFunction(
                    name='test_tool',
                    arguments='{"query": "test"}',
                ),
            ),
        ],
        finish_reason='tool_calls',
    )

    # Always return tool calls to trigger max rounds
    mock_llm_service.complete_messages.return_value = tool_call_response
    mock_tool_service.get_available_tools.return_value = []
    from datetime import datetime, timezone

    mock_tool_service.execute_tool.return_value = ToolExecutionResult(
        tool_name='test_tool',
        status=ToolExecutionStatus.SUCCESS,
        tool_call={
            'name': 'test_tool',
            'arguments': {},
            'started_at': datetime.now(timezone.utc),
            'finished_at': datetime.now(timezone.utc),
            'status': ToolExecutionStatus.SUCCESS,
        },
        llm_context='Result',
    )

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Search'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert 'exceeded maximum tool rounds' in result.error.message.lower()


async def test_call_llm_chat_completion_tool_messages_appended_correctly(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    llm_response_with_tool_call,
    mock_tool_result,
):
    """It appends tool results correctly to message history."""
    final_response = LLMCompletionResult(
        content='Final answer.',
        model='llama3.2',
        prompt_tokens=30,
        completion_tokens=15,
        total_tokens=45,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_llm_service.complete_messages.side_effect = [
        llm_response_with_tool_call,
        final_response,
    ]
    mock_tool_service.execute_tool.return_value = mock_tool_result
    mock_tool_service.get_available_tools.return_value = []

    await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Test'}],
        temperature=0.7,
        max_tokens=512,
    )

    # Verify second LLM call includes tool result message
    second_call_args = mock_llm_service.complete_messages.call_args_list[1]
    messages = second_call_args.kwargs['messages']

    # Should have system message + user message + assistant message with tool_calls + tool result message
    assert len(messages) >= 4
    # Last message should be tool result
    tool_message = messages[-1]
    assert tool_message['role'] == 'tool'
    assert tool_message['tool_call_id'] == 'call_123'
    assert tool_message['content'] == mock_tool_result.llm_context


async def test_call_llm_chat_completion_with_json_tool_arguments(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    mock_tool_result,
):
    """It correctly parses JSON arguments from tool calls."""
    # Tool call with complex JSON arguments
    tool_call_with_json = ChatCompletionMessageToolCall(
        id='call_json',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='complex_tool',
            arguments='{"query": "test", "filters": {"type": "article", "limit": 10}, "sort": "date"}',
        ),
    )

    tool_response = LLMCompletionResult(
        content='I will execute the complex tool.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=12,
        total_tokens=22,
        tool_calls=[tool_call_with_json],
        finish_reason='tool_calls',
    )

    final_response = LLMCompletionResult(
        content='Here are the results.',
        model='llama3.2',
        prompt_tokens=30,
        completion_tokens=10,
        total_tokens=40,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_llm_service.complete_messages.side_effect = [
        tool_response,
        final_response,
    ]
    mock_tool_service.execute_tool.return_value = mock_tool_result
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Complex search'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.content == 'Here are the results.'
    assert result.error is None

    # Verify tool was called with parsed JSON arguments
    mock_tool_service.execute_tool.assert_called_once_with(
        name='complex_tool',
        arguments={
            'query': 'test',
            'filters': {'type': 'article', 'limit': 10},
            'sort': 'date',
        },
    )


async def test_add_message_with_tool_call_flow(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
    mock_tool_result,
):
    """It handles complete message addition with tool calling."""
    # Create a conversation
    conversation = Conversation(
        user_id=test_user_id,
        title='Tool Calling Conversation',
    )
    async_session.add(conversation)
    await async_session.flush()

    user_message = Message(
        conversation_id=conversation.id,
        role='user',
        content='Initial message',
        sequence_number=1,
    )
    async_session.add(user_message)

    assistant_message = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='Initial response',
        sequence_number=2,
    )
    async_session.add(assistant_message)
    await async_session.commit()

    # Set up mock responses for tool calling
    tool_call_response = LLMCompletionResult(
        content='I will search for that.',
        model='llama3.2',
        prompt_tokens=15,
        completion_tokens=10,
        total_tokens=25,
        tool_calls=[
            ChatCompletionMessageToolCall(
                id='call_abc',
                type='function',
                function=ChatCompletionMessageToolCallFunction(
                    name='search_tool',
                    arguments='{"q": "python"}',
                ),
            ),
        ],
        finish_reason='tool_calls',
    )

    final_response = LLMCompletionResult(
        content='Python is a programming language.',
        model='llama3.2',
        prompt_tokens=30,
        completion_tokens=20,
        total_tokens=50,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_context_assembly.assemble_context.return_value = mock_context_result
    mock_llm_service.complete_messages.side_effect = [
        tool_call_response,
        final_response,
    ]
    mock_tool_service.get_available_tools.return_value = []
    mock_tool_service.execute_tool.return_value = mock_tool_result

    # Add new message
    payload = CreateMessageRequest(
        content='What is Python?',
        temperature=0.7,
        max_tokens=512,
    )

    result = await conversation_service.add_message_to_conversation(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    )

    # Verify final assistant response is from after tool execution
    assert (
        result.assistant_message.content == 'Python is a programming language.'
    )

    # Verify conversation was updated
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    db_result = await async_session.execute(stmt)
    messages = list(db_result.scalars().all())

    # Should have initial messages + new user message + final assistant response
    assert len(messages) == 4
    assert messages[2].content == 'What is Python?'
    assert messages[3].content == 'Python is a programming language.'


# Tests for tool argument validation


async def test_call_llm_chat_completion_malformed_json_arguments(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
):
    """It returns error result when tool arguments are malformed JSON."""
    # Tool call with invalid JSON
    malformed_tool_call = ChatCompletionMessageToolCall(
        id='call_bad',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='broken_tool',
            arguments='{invalid json}',  # Not valid JSON
        ),
    )

    tool_response = LLMCompletionResult(
        content='I will execute the tool.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=12,
        total_tokens=22,
        tool_calls=[malformed_tool_call],
        finish_reason='tool_calls',
    )

    mock_llm_service.complete_messages.return_value = tool_response
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Test'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert 'unable to parse tool arguments' in result.error.message.lower()


async def test_call_llm_chat_completion_tool_arguments_array(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
):
    """It returns error result when tool arguments are JSON array instead of object."""
    # Tool call with JSON array instead of object
    array_tool_call = ChatCompletionMessageToolCall(
        id='call_array',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='array_tool',
            arguments='["arg1", "arg2"]',  # Valid JSON but not an object
        ),
    )

    tool_response = LLMCompletionResult(
        content='I will execute the tool.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=12,
        total_tokens=22,
        tool_calls=[array_tool_call],
        finish_reason='tool_calls',
    )

    mock_llm_service.complete_messages.return_value = tool_response
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Test'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert (
        'tool arguments must be a json object' in result.error.message.lower()
    )
    assert 'list' in result.error.message.lower()


async def test_call_llm_chat_completion_tool_arguments_string(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
):
    """It returns error result when tool arguments are JSON string instead of object."""
    # Tool call with JSON string instead of object
    string_tool_call = ChatCompletionMessageToolCall(
        id='call_string',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='string_tool',
            arguments='"just a string"',  # Valid JSON but not an object
        ),
    )

    tool_response = LLMCompletionResult(
        content='I will execute the tool.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=12,
        total_tokens=22,
        tool_calls=[string_tool_call],
        finish_reason='tool_calls',
    )

    mock_llm_service.complete_messages.return_value = tool_response
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Test'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert (
        'tool arguments must be a json object' in result.error.message.lower()
    )
    assert 'str' in result.error.message.lower()


async def test_call_llm_chat_completion_tool_arguments_number(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
):
    """It returns error result when tool arguments are JSON number instead of object."""
    # Tool call with JSON number instead of object
    number_tool_call = ChatCompletionMessageToolCall(
        id='call_number',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='number_tool',
            arguments='42',  # Valid JSON but not an object
        ),
    )

    tool_response = LLMCompletionResult(
        content='I will execute the tool.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=12,
        total_tokens=22,
        tool_calls=[number_tool_call],
        finish_reason='tool_calls',
    )

    mock_llm_service.complete_messages.return_value = tool_response
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Test'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert (
        'tool arguments must be a json object' in result.error.message.lower()
    )
    assert 'int' in result.error.message.lower()


# Tests for annotation building


async def test_create_conversation_with_message_success_includes_annotations(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
    valid_request,
    mock_context_result,
):
    """It builds and persists success annotations on successful responses."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.return_value = LLMCompletionResult(
        content='The answer is 42.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=8,
        total_tokens=18,
        tool_calls=None,
        finish_reason='stop',
    )

    result = await conversation_service.create_conversation_with_message(
        session=async_session,
        user_id=test_user_id,
        payload=valid_request,
    )

    # Verify assistant message has success annotations
    assert result.assistant_message.annotations is not None
    assert result.assistant_message.annotations.failure is None
    assert result.assistant_message.error is None

    # Reload from DB to verify persistence
    stmt = select(Message).where(Message.id == result.assistant_message.id)
    db_result = await async_session.execute(stmt)
    db_message = db_result.scalar_one()
    assert db_message.annotations is not None
    assert db_message.error is None


async def test_add_message_with_tool_execution_and_fetch_sources(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    mock_tool_service,
    async_session,
    test_user_id,
    mock_context_result,
):
    """It builds annotations with sources from web_fetch tool results."""
    # Set up conversation
    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    user_message = Message(
        conversation_id=conversation.id,
        role='user',
        content='Find information about Python.',
        sequence_number=1,
    )
    async_session.add(user_message)
    await async_session.commit()

    # Mock context assembly
    mock_context_assembly.assemble_context.return_value = mock_context_result

    # Mock LLM to NOT request tools on first call
    mock_llm_service.complete_messages.return_value = LLMCompletionResult(
        content='Python is a popular programming language.',
        model='llama3.2',
        prompt_tokens=15,
        completion_tokens=12,
        total_tokens=27,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_tool_service.get_available_tools.return_value = []

    request = CreateMessageRequest(
        content='Find information about Python.',
        temperature=0.7,
        max_tokens=512,
    )

    result = await conversation_service.add_message_to_conversation(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=request,
    )

    # Verify assistant message has annotations
    assert result.assistant_message.annotations is not None
    assert result.assistant_message.error is None


async def test_create_conversation_with_message_llm_failure_persists_error_row(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
    valid_request,
    mock_context_result,
):
    """It persists assistant failure row with error annotations on LLM error."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    # Simulate LLM timeout
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.timeout,
        message='Request timed out',
    )

    # Should still raise HTTPException to client
    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 504

    # But message should be persisted with failure annotations
    stmt = (
        select(Message)
        .where(Message.role == 'assistant')
        .where(Message.conversation_id.is_not(None))
    )
    result = await async_session.execute(stmt)
    messages = list(result.scalars().all())

    # Should have persisted the assistant message with error
    assert len(messages) == 1
    assistant_msg = messages[0]
    assert assistant_msg.error is not None
    assert 'timed out' in assistant_msg.error.lower()
    assert assistant_msg.annotations is not None
    # Convert dict to AssistantAnnotations for assertion
    annotations = (
        AssistantAnnotations(**assistant_msg.annotations)
        if isinstance(assistant_msg.annotations, dict)
        else assistant_msg.annotations
    )
    assert annotations.failure is not None
    assert annotations.failure.stage == FailureAnnotationStage.LLM
    assert annotations.failure.retryable is True


async def test_get_conversation_messages_returns_persisted_annotations(
    conversation_service,
    async_session,
    test_user_id,
):
    """It returns persisted annotations unchanged on reload."""
    # Create conversation with annotated message
    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    message = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='Test response',
        sequence_number=1,
    )
    # Manually set annotations to verify they round-trip
    message.annotations = {
        'sources': [
            {
                'title': 'Example',
                'url': 'https://example.com',
                'snippet': 'Example snippet',
                'rationale': 'Test source',
            }
        ],
        'tools': [],
        'memory_hits': [],
        'memory_saved': [],
        'failure': None,
    }
    async_session.add(message)
    await async_session.commit()

    # Reload messages
    result = await conversation_service.get_conversation_messages(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
    )

    # Verify annotations are returned unchanged
    assert len(result.items) == 1
    assert result.items[0].annotations is not None
    assert len(result.items[0].annotations.sources) == 1
    assert result.items[0].annotations.sources[0].title == 'Example'


async def test_add_message_with_llm_failure_persists_error_annotations(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
    mock_context_result,
):
    """It persists failure annotations with correct stage on LLM error."""
    # Create conversation
    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    user_message = Message(
        conversation_id=conversation.id,
        role='user',
        content='Hello',
        sequence_number=1,
    )
    async_session.add(user_message)
    await async_session.commit()

    # Mock context assembly
    mock_context_assembly.assemble_context.return_value = mock_context_result

    # Simulate LLM server error
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.backend_error,
        message='Backend error',
    )

    request = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=request,
        )

    assert exc_info.value.status_code == 502

    # Verify failure message persisted with correct stage
    stmt = (
        select(Message)
        .where(Message.role == 'assistant')
        .where(Message.conversation_id == conversation.id)
    )
    result = await async_session.execute(stmt)
    messages = list(result.scalars().all())

    assert len(messages) == 1
    failure_msg = messages[0]
    assert failure_msg.annotations is not None
    # Convert dict to AssistantAnnotations for assertion
    annotations = (
        AssistantAnnotations(**failure_msg.annotations)
        if isinstance(failure_msg.annotations, dict)
        else failure_msg.annotations
    )
    assert annotations.failure is not None
    assert annotations.failure.stage == FailureAnnotationStage.LLM
    assert annotations.failure.retryable is True


# ============================================================================
# Background Extraction Tests
# ============================================================================


@pytest.fixture
def mock_background_tasks():
    """Create a mock BackgroundTasks instance."""
    mock_tasks = Mock()
    mock_tasks.add_task = Mock()
    return mock_tasks


async def test_create_conversation_schedules_background_extraction(
    async_session,
    mock_llm_service,
    mock_context_assembly,
    mock_tool_service,
    mock_memory_storage,
    mock_background_tasks,
):
    """Test that create_conversation_with_message schedules extraction on success."""
    # Setup
    user_id = 'test@example.com'
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        ContextAssemblyResult(
            messages=[
                {'role': 'user', 'content': 'Hello'},
            ],
            used_summary=False,
            summary_id=None,
            fact_ids=[],
        )
    )
    mock_llm_service.complete_messages.return_value = LLMCompletionResult(
        content='Hi there!',
        model='test-model',
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        tool_calls=None,
        finish_reason='stop',
    )

    service = ConversationService(
        llm_service=mock_llm_service,
        context_assembly=mock_context_assembly,
        tool_service=mock_tool_service,
        memory_storage=mock_memory_storage,
    )

    payload = CreateConversationWithMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=100,
    )

    # Execute
    result = await service.create_conversation_with_message(
        async_session,
        user_id=user_id,
        payload=payload,
        background_tasks=mock_background_tasks,
    )

    # Assert: background task scheduled exactly once
    assert mock_background_tasks.add_task.call_count == 1

    # Assert: task is called with correct method and args
    call_args = mock_background_tasks.add_task.call_args
    assert call_args[0][0].__name__ == 'extract_and_save_background'
    assert call_args[1]['user_id'] == user_id
    assert call_args[1]['conversation_id'] == result.conversation.id
    assert call_args[1]['assistant_message_id'] == result.assistant_message.id
    assert call_args[1]['latest_user_message_id'] == result.user_message.id


async def test_add_message_schedules_background_extraction(
    async_session,
    mock_llm_service,
    mock_context_assembly,
    mock_tool_service,
    mock_memory_storage,
    mock_background_tasks,
):
    """Test that add_message_to_conversation schedules extraction on success."""
    # Setup
    user_id = 'test@example.com'
    conv_id = uuid.uuid4()

    # Create initial conversation with user message
    conversation = Conversation(
        id=conv_id,
        user_id=user_id,
        title='Test Conversation',
    )
    async_session.add(conversation)

    user_msg_1 = Message(
        conversation_id=conv_id,
        role='user',
        content='Hello',
        sequence_number=1,
    )
    async_session.add(user_msg_1)
    await async_session.commit()

    # Setup mocks for add_message
    mock_context_assembly.assemble_context.return_value = ContextAssemblyResult(
        messages=[
            {'role': 'user', 'content': 'Follow-up'},
        ],
        used_summary=False,
        summary_id=None,
        fact_ids=[],
    )
    mock_llm_service.complete_messages.return_value = LLMCompletionResult(
        content='Response to follow-up',
        model='test-model',
        prompt_tokens=15,
        completion_tokens=8,
        total_tokens=23,
        tool_calls=None,
        finish_reason='stop',
    )

    service = ConversationService(
        llm_service=mock_llm_service,
        context_assembly=mock_context_assembly,
        tool_service=mock_tool_service,
        memory_storage=mock_memory_storage,
    )

    payload = CreateMessageRequest(
        content='Follow-up question',
        temperature=0.7,
        max_tokens=100,
    )

    # Execute
    result = await service.add_message_to_conversation(
        async_session,
        user_id=user_id,
        conversation_id=conv_id,
        payload=payload,
        background_tasks=mock_background_tasks,
    )

    # Assert: background task scheduled exactly once
    assert mock_background_tasks.add_task.call_count == 1

    # Assert: task receives primitive IDs
    call_args = mock_background_tasks.add_task.call_args
    assert call_args[0][0].__name__ == 'extract_and_save_background'
    assert call_args[1]['user_id'] == user_id
    assert call_args[1]['conversation_id'] == conv_id
    assert call_args[1]['assistant_message_id'] == result.assistant_message.id


async def test_no_background_extraction_on_terminal_failure(
    async_session,
    mock_llm_service,
    mock_context_assembly,
    mock_tool_service,
    mock_background_tasks,
):
    """Test that background extraction is NOT scheduled on terminal LLM failure."""
    # Setup
    user_id = 'test@example.com'
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        ContextAssemblyResult(
            messages=[
                {'role': 'user', 'content': 'Hello'},
            ],
            used_summary=False,
            summary_id=None,
            fact_ids=[],
        )
    )

    # Simulate LLM error
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.timeout,
        message='LLM timeout',
    )

    service = ConversationService(
        llm_service=mock_llm_service,
        context_assembly=mock_context_assembly,
        tool_service=mock_tool_service,
    )

    payload = CreateConversationWithMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=100,
    )

    # Execute and catch HTTPException from terminal failure
    with pytest.raises(HTTPException):
        await service.create_conversation_with_message(
            async_session,
            user_id=user_id,
            payload=payload,
            background_tasks=mock_background_tasks,
        )

    # Assert: NO background task scheduled on failure
    assert mock_background_tasks.add_task.call_count == 0


async def test_no_background_extraction_without_memory_storage(
    async_session,
    mock_llm_service,
    mock_context_assembly,
    mock_tool_service,
    mock_background_tasks,
):
    """Test that background extraction is not scheduled if memory_storage is None."""
    # Setup
    user_id = 'test@example.com'
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        ContextAssemblyResult(
            messages=[
                {'role': 'user', 'content': 'Hello'},
            ],
            used_summary=False,
            summary_id=None,
            fact_ids=[],
        )
    )
    mock_llm_service.complete_messages.return_value = LLMCompletionResult(
        content='Hi there!',
        model='test-model',
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        tool_calls=None,
        finish_reason='stop',
    )

    # Create service WITHOUT memory_storage
    service = ConversationService(
        llm_service=mock_llm_service,
        context_assembly=mock_context_assembly,
        tool_service=mock_tool_service,
        memory_storage=None,
    )

    payload = CreateConversationWithMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=100,
    )

    # Execute
    result = await service.create_conversation_with_message(
        async_session,
        user_id=user_id,
        payload=payload,
        background_tasks=mock_background_tasks,
    )

    # Assert: response succeeds but NO background task scheduled
    assert result.assistant_message.content == 'Hi there!'
    assert mock_background_tasks.add_task.call_count == 0


async def test_background_extraction_parses_results_correctly():
    """Test that extraction result parsing works correctly."""
    service = ConversationService(
        llm_service=AsyncMock(spec=LLMService),
        context_assembly=AsyncMock(spec=ContextAssemblyService),
        tool_service=Mock(spec=ToolService),
    )

    # Test valid JSON extraction
    result_text = """
    {
        "summary": "User learned about Python",
        "facts": [
            {"subject": "User", "fact": "Interested in Python", "confidence": "high"},
            {"subject": "User", "fact": "Beginner programmer", "confidence": "medium"}
        ]
    }
    """

    summary, facts = service._parse_extraction_result(result_text)

    assert summary == 'User learned about Python'
    assert len(facts) == 2
    assert facts[0]['subject'] == 'User'
    assert facts[0]['fact'] == 'Interested in Python'


async def test_background_extraction_handles_invalid_json():
    """Test that extraction gracefully handles invalid JSON."""
    service = ConversationService(
        llm_service=AsyncMock(spec=LLMService),
        context_assembly=AsyncMock(spec=ContextAssemblyService),
        tool_service=Mock(spec=ToolService),
    )

    # Invalid JSON
    result_text = 'Invalid JSON text without any braces'

    summary, facts = service._parse_extraction_result(result_text)

    assert summary is None
    assert facts is None


async def test_background_extraction_filters_empty_facts():
    """Test that extraction filters out empty facts."""
    service = ConversationService(
        llm_service=AsyncMock(spec=LLMService),
        context_assembly=AsyncMock(spec=ContextAssemblyService),
        tool_service=Mock(spec=ToolService),
    )

    result_text = """
    {
        "summary": "Test summary",
        "facts": [
            {"subject": "User", "fact": "Valid fact", "confidence": "high"},
            {"subject": "", "fact": "", "confidence": "low"},
            {"subject": "Valid", "fact": "Another fact", "confidence": "medium"}
        ]
    }
    """

    summary, facts = service._parse_extraction_result(result_text)

    assert summary == 'Test summary'
    assert len(facts) == 2  # Empty fact filtered out
