"""Tests for ContextAssemblyService."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from assistant.models.conversation_sql import Conversation, Message
from assistant.models.memory_sql import (
    ConversationMemorySummary,
    DurableFact,
    DurableFactConfidence,
    DurableFactSourceType,
)
from assistant.services.context_assembly import (
    MAX_DURABLE_FACTS,
    MAX_FACT_TEXT_LENGTH,
    MAX_RECENT_MESSAGES_NO_SUMMARY,
    MAX_RECENT_MESSAGES_WITH_SUMMARY,
    MAX_SUMMARY_TEXT_LENGTH,
    ContextAssemblyService,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db_session():
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


async def test_assemble_context_new_conversation_no_facts(
    db_session: AsyncSession,
):
    """It assembles context for new conversation with no facts."""
    service = ContextAssemblyService()
    user_id = 'user-123'
    user_message = 'Hello, assistant!'

    result = await service.assemble_context_new_conversation(
        db_session,
        user_id=user_id,
        user_message=user_message,
    )

    assert result.used_summary is False
    assert result.summary_id is None
    assert result.fact_ids == []
    assert len(result.messages) == 1
    assert result.messages[0] == {'role': 'user', 'content': user_message}


async def test_assemble_context_new_conversation_with_facts(
    db_session: AsyncSession,
):
    """It includes durable facts in new conversation context."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create some active facts
    fact1 = DurableFact(
        user_id=user_id,
        subject='George Langley',
        fact_text='Born in 1884',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    fact2 = DurableFact(
        user_id=user_id,
        subject='Mary Langley',
        fact_text='Married in 1910',
        confidence=DurableFactConfidence.MEDIUM,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact1)
    db_session.add(fact2)
    await db_session.commit()
    await db_session.refresh(fact1)
    await db_session.refresh(fact2)

    result = await service.assemble_context_new_conversation(
        db_session,
        user_id=user_id,
        user_message='Tell me about George',
    )

    assert result.used_summary is False
    assert result.summary_id is None
    assert len(result.fact_ids) == 2
    assert fact1.id in result.fact_ids
    assert fact2.id in result.fact_ids
    assert len(result.messages) == 2  # facts system message + user message

    # Check facts message
    facts_msg = result.messages[0]
    assert facts_msg['role'] == 'system'
    assert 'Known facts about the user' in facts_msg['content']
    assert 'George Langley' in facts_msg['content']
    assert 'Born in 1884' in facts_msg['content']
    assert 'Mary Langley' in facts_msg['content']

    # Check user message
    assert result.messages[1] == {
        'role': 'user',
        'content': 'Tell me about George',
    }


async def test_assemble_context_no_summary_uses_recent_turns(
    db_session: AsyncSession,
):
    """It uses recent turns when no summary exists."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create conversation and messages
    conversation = Conversation(user_id=user_id, title='Test Chat')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Add messages (should only use last MAX_RECENT_MESSAGES_NO_SUMMARY)
    for i in range(1, 11):
        msg = Message(
            conversation_id=conversation.id,
            role='user' if i % 2 == 1 else 'assistant',
            content=f'Message {i}',
            sequence_number=i,
        )
        db_session.add(msg)
    await db_session.commit()

    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='New message',
    )

    assert result.used_summary is False
    assert result.summary_id is None
    assert len(result.fact_ids) == 0

    # Should have last 8 messages + new user message
    assert len(result.messages) == MAX_RECENT_MESSAGES_NO_SUMMARY + 1

    # Check that it's the last 8 messages (messages 3-10)
    for i, msg in enumerate(result.messages[:-1]):
        expected_content = f'Message {i + 3}'
        assert msg['content'] == expected_content

    # Last message is the new user message
    assert result.messages[-1] == {'role': 'user', 'content': 'New message'}


async def test_assemble_context_with_summary_limits_recent_turns(
    db_session: AsyncSession,
):
    """It limits recent turns when summary exists."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create conversation
    conversation = Conversation(user_id=user_id, title='Test Chat')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Create summary
    summary = ConversationMemorySummary(
        conversation_id=conversation.id,
        user_id=user_id,
        summary_text='Previous discussion about genealogy research.',
    )
    db_session.add(summary)
    await db_session.commit()
    await db_session.refresh(summary)

    # Add messages (should only use MAX_RECENT_MESSAGES_WITH_SUMMARY)
    for i in range(1, 11):
        msg = Message(
            conversation_id=conversation.id,
            role='user' if i % 2 == 1 else 'assistant',
            content=f'Message {i}',
            sequence_number=i,
        )
        db_session.add(msg)
    await db_session.commit()

    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='New message',
    )

    assert result.used_summary is True
    assert result.summary_id == summary.id

    # Should have: summary + last 4 messages + new user message = 6 total
    assert len(result.messages) == 1 + MAX_RECENT_MESSAGES_WITH_SUMMARY + 1

    # First message is summary
    assert result.messages[0]['role'] == 'system'
    assert 'Conversation summary' in result.messages[0]['content']
    assert 'genealogy research' in result.messages[0]['content']

    # Next 4 are recent turns (messages 7-10)
    for i, msg in enumerate(result.messages[1:5]):
        expected_content = f'Message {i + 7}'
        assert msg['content'] == expected_content

    # Last is new user message
    assert result.messages[-1] == {'role': 'user', 'content': 'New message'}


async def test_assemble_context_with_summary_and_facts(
    db_session: AsyncSession,
):
    """It includes both summary and facts when available."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create conversation
    conversation = Conversation(user_id=user_id, title='Test Chat')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Create summary
    summary = ConversationMemorySummary(
        conversation_id=conversation.id,
        user_id=user_id,
        summary_text='Discussed family history.',
    )
    db_session.add(summary)

    # Create fact
    fact = DurableFact(
        user_id=user_id,
        subject='John Smith',
        fact_text='Lives in London',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact)

    # Add recent message
    msg = Message(
        conversation_id=conversation.id,
        role='user',
        content='Previous question',
        sequence_number=1,
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(summary)
    await db_session.refresh(fact)

    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='New question',
    )

    assert result.used_summary is True
    assert result.summary_id == summary.id
    assert len(result.fact_ids) == 1
    assert fact.id in result.fact_ids

    # Should have: summary + facts + 1 recent turn + new message = 4 total
    assert len(result.messages) == 4

    # Check order: summary, facts, recent turn, new message
    assert 'Conversation summary' in result.messages[0]['content']
    assert 'Known facts' in result.messages[1]['content']
    assert result.messages[2] == {
        'role': 'user',
        'content': 'Previous question',
    }
    assert result.messages[3] == {'role': 'user', 'content': 'New question'}


async def test_facts_filtered_by_user_and_active(db_session: AsyncSession):
    """It only includes facts for the current user that are active."""
    service = ContextAssemblyService()
    user_id = 'user-123'
    other_user_id = 'user-456'

    # Create conversation
    conversation = Conversation(user_id=user_id, title='Test')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Create facts for current user (active)
    fact1 = DurableFact(
        user_id=user_id,
        subject='Item 1',
        fact_text='User fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    # Create fact for current user (inactive - should be excluded)
    fact2 = DurableFact(
        user_id=user_id,
        subject='Item 2',
        fact_text='Inactive fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=False,
    )
    # Create fact for other user (should be excluded)
    fact3 = DurableFact(
        user_id=other_user_id,
        subject='Item 3',
        fact_text='Other user fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add_all([fact1, fact2, fact3])
    await db_session.commit()
    await db_session.refresh(fact1)

    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='Test',
    )

    # Only fact1 should be included
    assert len(result.fact_ids) == 1
    assert result.fact_ids[0] == fact1.id


async def test_facts_limited_to_max(db_session: AsyncSession):
    """It limits facts to MAX_DURABLE_FACTS."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create conversation
    conversation = Conversation(user_id=user_id, title='Test')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Create more facts than the max
    for i in range(MAX_DURABLE_FACTS + 3):
        fact = DurableFact(
            user_id=user_id,
            subject=f'Subject {i}',
            fact_text=f'Fact {i}',
            confidence=DurableFactConfidence.HIGH,
            source_type=DurableFactSourceType.CONVERSATION,
            active=True,
        )
        db_session.add(fact)
    await db_session.commit()

    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='Test',
    )

    # Should only include MAX_DURABLE_FACTS
    assert len(result.fact_ids) == MAX_DURABLE_FACTS


async def test_summary_text_truncated(db_session: AsyncSession):
    """It truncates summary text to MAX_SUMMARY_TEXT_LENGTH."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create conversation
    conversation = Conversation(user_id=user_id, title='Test')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Create summary with very long text
    long_text = 'A' * (MAX_SUMMARY_TEXT_LENGTH + 500)
    summary = ConversationMemorySummary(
        conversation_id=conversation.id,
        user_id=user_id,
        summary_text=long_text,
    )
    db_session.add(summary)
    await db_session.commit()

    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='Test',
    )

    assert result.used_summary is True

    # Find the summary message
    summary_msg = result.messages[0]
    assert summary_msg['role'] == 'system'

    # Extract just the summary text (after the prefix)
    content = summary_msg['content']
    summary_text = content.replace('[Conversation summary]: ', '')

    # Should be truncated with ellipsis
    assert len(summary_text) <= MAX_SUMMARY_TEXT_LENGTH
    assert summary_text.endswith('...')


async def test_fact_text_truncated(db_session: AsyncSession):
    """It truncates individual fact text to MAX_FACT_TEXT_LENGTH."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create fact with very long text
    long_text = 'B' * (MAX_FACT_TEXT_LENGTH + 100)
    fact = DurableFact(
        user_id=user_id,
        subject='Long Fact',
        fact_text=long_text,
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact)
    await db_session.commit()
    await db_session.refresh(fact)

    result = await service.assemble_context_new_conversation(
        db_session,
        user_id=user_id,
        user_message='Test',
    )

    # Find the facts message
    facts_msg = result.messages[0]
    assert facts_msg['role'] == 'system'

    # The fact text in the message should be truncated
    content = facts_msg['content']
    assert '...' in content
    # The full long text should not be in the message
    assert long_text not in content


async def test_empty_conversation_no_summary(db_session: AsyncSession):
    """It handles empty conversation with no summary gracefully."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create empty conversation
    conversation = Conversation(user_id=user_id, title='Empty')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='First real message',
    )

    assert result.used_summary is False
    assert result.summary_id is None
    assert len(result.fact_ids) == 0

    # Should only have the new user message
    assert len(result.messages) == 1
    assert result.messages[0] == {
        'role': 'user',
        'content': 'First real message',
    }


async def test_assemble_context_without_new_message_no_duplication(
    db_session: AsyncSession,
):
    """It doesn't duplicate messages when new_user_message=None.

    Regression test: when the new user message is already in the DB
    (existing conversation flow), passing None prevents duplication.
    """
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create conversation with existing messages
    conversation = Conversation(user_id=user_id, title='Test')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Add messages including the "new" one that's already persisted
    msg1 = Message(
        conversation_id=conversation.id,
        role='user',
        content='First message',
        sequence_number=1,
    )
    msg2 = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='First response',
        sequence_number=2,
    )
    msg3 = Message(
        conversation_id=conversation.id,
        role='user',
        content='Latest message',
        sequence_number=3,
    )
    db_session.add_all([msg1, msg2, msg3])
    await db_session.commit()

    # Call with new_user_message=None (existing conversation case)
    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message=None,
    )

    # Should have exactly 3 messages from DB, no duplication
    assert len(result.messages) == 3
    assert result.messages[0]['content'] == 'First message'
    assert result.messages[1]['content'] == 'First response'
    assert result.messages[2]['content'] == 'Latest message'

    # Verify "Latest message" appears exactly once
    latest_count = sum(
        1 for msg in result.messages if msg['content'] == 'Latest message'
    )
    assert latest_count == 1
