"""Tests for ConversationService message retrieval operations."""

import uuid

from fastapi import HTTPException
import pytest

from assistant.models.conversation_sql import Conversation, Message


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
