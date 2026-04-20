"""Tests for ConversationService listing operations."""

from datetime import datetime, timedelta, timezone
import uuid

import pytest

from assistant.models.conversation_sql import Conversation, Message


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
