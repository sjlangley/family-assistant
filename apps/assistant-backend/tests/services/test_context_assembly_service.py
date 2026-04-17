"""Tests for ContextAssemblyService."""

from unittest.mock import Mock
import uuid

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
    MAX_FACT_CANDIDATES,
    MAX_FACT_TEXT_LENGTH,
    MAX_RECENT_MESSAGES_NO_SUMMARY,
    MAX_RECENT_MESSAGES_WITH_SUMMARY,
    MAX_SUMMARY_TEXT_LENGTH,
    ContextAssemblyService,
)
from assistant.services.memory_storage import DurableFactSearchResult

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


# New tests for relevance-based fact selection
async def test_fact_selection_prefers_relevant_over_recent(
    db_session: AsyncSession,
):
    """Facts whose subjects appear in recent turns are preferred over recent facts."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create conversation
    conversation = Conversation(user_id=user_id, title='Genealogy')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Create enough facts to exceed MAX_DURABLE_FACTS so selection matters
    # Create old but relevant facts (George mentioned in recent turn)
    old_relevant_fact = DurableFact(
        user_id=user_id,
        subject='George Langley',
        fact_text='Born in 1884',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(old_relevant_fact)
    await db_session.commit()

    # Create many recent but non-relevant facts to exceed the budget
    for i in range(MAX_DURABLE_FACTS + 1):
        fact = DurableFact(
            user_id=user_id,
            subject=f'Unrelated Person {i}',
            fact_text=f'Unrelated fact {i}',
            confidence=DurableFactConfidence.HIGH,
            source_type=DurableFactSourceType.CONVERSATION,
            active=True,
        )
        db_session.add(fact)
    await db_session.commit()
    await db_session.refresh(old_relevant_fact)

    # Add recent turn that mentions "George"
    msg = Message(
        conversation_id=conversation.id,
        role='user',
        content='Tell me about George',
        sequence_number=1,
    )
    db_session.add(msg)
    await db_session.commit()

    # Assemble context
    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='What else?',
    )

    # Should prefer the relevant fact even though others are more recent
    assert old_relevant_fact.id in result.fact_ids
    assert result.selection_method == 'relevance'


async def test_fact_selection_fallback_to_recency(db_session: AsyncSession):
    """When no facts are relevant to recent turns, fall back to recency."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create conversation
    conversation = Conversation(user_id=user_id, title='Chat')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Create facts with subjects not mentioned in recent turns
    fact1 = DurableFact(
        user_id=user_id,
        subject='Alice',
        fact_text='First fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact1)
    await db_session.commit()

    fact2 = DurableFact(
        user_id=user_id,
        subject='Bob',
        fact_text='Second fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact2)
    await db_session.commit()
    await db_session.refresh(fact1)
    await db_session.refresh(fact2)

    # Add recent turn that doesn't mention any subjects
    msg = Message(
        conversation_id=conversation.id,
        role='user',
        content='Tell me something interesting',
        sequence_number=1,
    )
    db_session.add(msg)
    await db_session.commit()

    # Assemble context
    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='What is that?',
    )

    # Should fall back to recency (fact2 is more recent)
    assert fact2.id in result.fact_ids
    assert result.selection_method == 'recency'


async def test_fact_selection_uses_postgres_canonical_rows(
    db_session: AsyncSession,
):
    """Selected facts come from canonical Postgres rows, not another source."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create conversation
    conversation = Conversation(user_id=user_id, title='Chat')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Create facts
    fact = DurableFact(
        user_id=user_id,
        subject='John',
        fact_text='A known fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact)
    await db_session.commit()
    await db_session.refresh(fact)

    # Add recent turn mentioning the subject
    msg = Message(
        conversation_id=conversation.id,
        role='user',
        content='What about John?',
        sequence_number=1,
    )
    db_session.add(msg)
    await db_session.commit()

    # Assemble context
    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='Tell me',
    )

    # Verify fact_ids correspond to actual Postgres rows
    assert len(result.fact_ids) == 1
    assert result.fact_ids[0] == fact.id

    # Verify the fact content appears in the prompt
    facts_msg = [
        m for m in result.messages if 'Known facts' in m.get('content', '')
    ]
    assert len(facts_msg) == 1
    assert 'John' in facts_msg[0]['content']
    assert 'A known fact' in facts_msg[0]['content']


async def test_fact_selection_prefers_multiple_relevant_facts(
    db_session: AsyncSession,
):
    """When multiple facts are relevant, use recency as tiebreaker."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create conversation
    conversation = Conversation(user_id=user_id, title='Chat')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Create three relevant facts (subjects all in recent turns)
    # Older relevant facts
    fact1 = DurableFact(
        user_id=user_id,
        subject='George',
        fact_text='First fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact1)
    await db_session.commit()

    fact2 = DurableFact(
        user_id=user_id,
        subject='Mary',
        fact_text='Second fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact2)
    await db_session.commit()

    # Newest relevant fact
    # Add sleep between commits to ensure distinct updated_at timestamps
    # SQLite uses second-resolution timestamps, so rapid inserts can have
    # identical updated_at and cause nondeterministic ordering
    import asyncio

    await asyncio.sleep(0.1)

    fact3 = DurableFact(
        user_id=user_id,
        subject='John',
        fact_text='Third fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact3)
    await db_session.commit()
    await db_session.refresh(fact1)
    await db_session.refresh(fact2)
    await db_session.refresh(fact3)

    # Add recent turns mentioning all three subjects
    msg = Message(
        conversation_id=conversation.id,
        role='user',
        content='About George, Mary, and John...',
        sequence_number=1,
    )
    db_session.add(msg)
    await db_session.commit()

    # Assemble context
    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='Tell me',
    )

    # All three should be included (all relevant)
    assert len(result.fact_ids) == 3
    # They should be sorted by recency (newest first)
    assert result.fact_ids[0] == fact3.id
    assert result.fact_ids[1] == fact2.id
    assert result.fact_ids[2] == fact1.id
    assert result.selection_method == 'relevance'


async def test_fact_selection_case_insensitive_matching(
    db_session: AsyncSession,
):
    """Subject matching is case-insensitive."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create conversation
    conversation = Conversation(user_id=user_id, title='Chat')
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    # Create fact with mixed case subject
    fact = DurableFact(
        user_id=user_id,
        subject='George Langley',
        fact_text='A fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact)
    await db_session.commit()
    await db_session.refresh(fact)

    # Add recent turn with different case
    msg = Message(
        conversation_id=conversation.id,
        role='user',
        content='What about george langley?',  # lowercase
        sequence_number=1,
    )
    db_session.add(msg)
    await db_session.commit()

    # Assemble context
    result = await service.assemble_context(
        db_session,
        user_id=user_id,
        conversation_id=conversation.id,
        new_user_message='Tell me',
    )

    # Should match despite case difference
    assert fact.id in result.fact_ids
    assert result.selection_method == 'relevance'


async def test_new_conversation_fact_selection_uses_chroma_distance_order(
    db_session: AsyncSession,
):
    """New conversations preserve semantic ranking by ascending distance."""
    user_id = 'user-123'
    closer_fact = DurableFact(
        user_id=user_id,
        subject='Name',
        fact_text='The user name is Barry.',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    farther_fact = DurableFact(
        user_id=user_id,
        subject='Location',
        fact_text='The user lives in Sydney.',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add_all([closer_fact, farther_fact])
    await db_session.commit()
    await db_session.refresh(closer_fact)
    await db_session.refresh(farther_fact)

    memory_storage = Mock()
    memory_storage.query_durable_fact_candidates.return_value = [
        DurableFactSearchResult(
            fact_id=farther_fact.id,
            document='Farther Chroma doc',
            distance=0.8,
        ),
        DurableFactSearchResult(
            fact_id=closer_fact.id,
            document='Closer Chroma doc',
            distance=0.1,
        ),
    ]
    service = ContextAssemblyService(memory_storage=memory_storage)

    result = await service.assemble_context_new_conversation(
        db_session,
        user_id=user_id,
        user_message='what is my name?',
    )

    memory_storage.query_durable_fact_candidates.assert_called_once_with(
        user_id=user_id,
        query='what is my name?',
        n_results=MAX_FACT_CANDIDATES,
    )
    assert result.selection_method == 'chroma'
    assert result.candidate_fact_ids == [closer_fact.id, farther_fact.id]
    assert result.fact_ids == [closer_fact.id, farther_fact.id]


async def test_new_conversation_prefers_older_relevant_fact_over_newer_irrelevant(
    db_session: AsyncSession,
):
    """A semantically relevant older fact beats newer irrelevant facts."""
    user_id = 'user-123'
    older_relevant_fact = DurableFact(
        user_id=user_id,
        subject='Name',
        fact_text='The user name is Barry.',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(older_relevant_fact)
    await db_session.commit()
    await db_session.refresh(older_relevant_fact)

    newer_irrelevant_facts: list[DurableFact] = []
    for i in range(MAX_DURABLE_FACTS):
        fact = DurableFact(
            user_id=user_id,
            subject=f'Unrelated {i}',
            fact_text=f'Irrelevant fact {i}',
            confidence=DurableFactConfidence.HIGH,
            source_type=DurableFactSourceType.CONVERSATION,
            active=True,
        )
        db_session.add(fact)
        newer_irrelevant_facts.append(fact)
    await db_session.commit()
    for fact in newer_irrelevant_facts:
        await db_session.refresh(fact)

    memory_storage = Mock()
    memory_storage.query_durable_fact_candidates.return_value = [
        DurableFactSearchResult(
            fact_id=older_relevant_fact.id,
            document='The user name is Barry.',
            distance=0.01,
        )
    ] + [
        DurableFactSearchResult(
            fact_id=fact.id,
            document=fact.fact_text,
            distance=0.1 + (index * 0.1),
        )
        for index, fact in enumerate(newer_irrelevant_facts)
    ]
    service = ContextAssemblyService(memory_storage=memory_storage)

    result = await service.assemble_context_new_conversation(
        db_session,
        user_id=user_id,
        user_message='what is my name?',
    )

    assert older_relevant_fact.id in result.fact_ids
    assert len(result.fact_ids) == MAX_DURABLE_FACTS


async def test_new_conversation_prefers_older_relevant_fact_over_contradiction(
    db_session: AsyncSession,
):
    """A semantically relevant older fact can displace newer contradictions."""
    user_id = 'user-123'
    correct_fact = DurableFact(
        user_id=user_id,
        subject='Name',
        fact_text='The user name is Barry.',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(correct_fact)
    await db_session.commit()
    await db_session.refresh(correct_fact)

    contradictory_fact = DurableFact(
        user_id=user_id,
        subject='Name',
        fact_text="The assistant does not know the user's name.",
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(contradictory_fact)

    filler_facts: list[DurableFact] = []
    for i in range(MAX_DURABLE_FACTS - 1):
        fact = DurableFact(
            user_id=user_id,
            subject=f'Profile {i}',
            fact_text=f'Other profile fact {i}',
            confidence=DurableFactConfidence.HIGH,
            source_type=DurableFactSourceType.CONVERSATION,
            active=True,
        )
        db_session.add(fact)
        filler_facts.append(fact)
    await db_session.commit()
    await db_session.refresh(contradictory_fact)
    for fact in filler_facts:
        await db_session.refresh(fact)

    memory_storage = Mock()
    memory_storage.query_durable_fact_candidates.return_value = [
        DurableFactSearchResult(
            fact_id=contradictory_fact.id,
            document=contradictory_fact.fact_text,
            distance=0.9,
        ),
        DurableFactSearchResult(
            fact_id=correct_fact.id,
            document=correct_fact.fact_text,
            distance=0.01,
        ),
    ] + [
        DurableFactSearchResult(
            fact_id=fact.id,
            document=fact.fact_text,
            distance=0.1 + (index * 0.1),
        )
        for index, fact in enumerate(filler_facts)
    ]
    service = ContextAssemblyService(memory_storage=memory_storage)

    result = await service.assemble_context_new_conversation(
        db_session,
        user_id=user_id,
        user_message='what is my name?',
    )

    assert correct_fact.id in result.fact_ids
    assert contradictory_fact.id not in result.fact_ids


async def test_new_conversation_chroma_hits_reload_canonical_postgres_rows(
    db_session: AsyncSession,
):
    """Chroma hits are reloaded from Postgres before prompt injection."""
    user_id = 'user-123'
    active_fact = DurableFact(
        user_id=user_id,
        subject='Name',
        fact_text='Canonical fact from Postgres',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    inactive_fact = DurableFact(
        user_id=user_id,
        subject='Old Name',
        fact_text='Inactive fact from Postgres',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=False,
    )
    other_user_fact = DurableFact(
        user_id='user-456',
        subject='Name',
        fact_text='Other user fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add_all([active_fact, inactive_fact, other_user_fact])
    await db_session.commit()
    await db_session.refresh(active_fact)
    await db_session.refresh(inactive_fact)
    await db_session.refresh(other_user_fact)

    missing_fact_id = uuid.uuid4()
    memory_storage = Mock()
    memory_storage.query_durable_fact_candidates.return_value = [
        DurableFactSearchResult(
            fact_id=active_fact.id,
            document='Stale Chroma text',
            distance=0.01,
        ),
        DurableFactSearchResult(
            fact_id=inactive_fact.id,
            document='Inactive Chroma text',
            distance=0.02,
        ),
        DurableFactSearchResult(
            fact_id=other_user_fact.id,
            document='Other user Chroma text',
            distance=0.03,
        ),
        DurableFactSearchResult(
            fact_id=missing_fact_id,
            document='Missing Chroma text',
            distance=0.04,
        ),
    ]
    service = ContextAssemblyService(memory_storage=memory_storage)

    result = await service.assemble_context_new_conversation(
        db_session,
        user_id=user_id,
        user_message='what is my name?',
    )

    assert result.selection_method == 'chroma'
    assert result.candidate_fact_ids == [
        active_fact.id,
        inactive_fact.id,
        other_user_fact.id,
        missing_fact_id,
    ]
    assert result.fact_ids == [active_fact.id]
    assert 'Canonical fact from Postgres' in result.messages[0]['content']
    assert 'Stale Chroma text' not in result.messages[0]['content']


async def test_new_conversation_chroma_empty_falls_back_to_recency(
    db_session: AsyncSession,
):
    """If Chroma has no hits, new-conversation facts fall back to recency."""
    user_id = 'user-123'
    fact1 = DurableFact(
        user_id=user_id,
        subject='Subject A',
        fact_text='First',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    fact2 = DurableFact(
        user_id=user_id,
        subject='Subject B',
        fact_text='Second',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add_all([fact1, fact2])
    await db_session.commit()
    await db_session.refresh(fact2)

    memory_storage = Mock()
    memory_storage.query_durable_fact_candidates.return_value = []
    service = ContextAssemblyService(memory_storage=memory_storage)

    result = await service.assemble_context_new_conversation(
        db_session,
        user_id=user_id,
        user_message='hello',
    )

    assert result.selection_method == 'recency'
    assert result.fact_ids[0] == fact2.id
    assert result.candidate_fact_ids == []


async def test_new_conversation_chroma_failure_falls_back_to_recency(
    db_session: AsyncSession,
):
    """If Chroma retrieval fails, new-conversation facts fall back safely."""
    user_id = 'user-123'
    fact1 = DurableFact(
        user_id=user_id,
        subject='Subject A',
        fact_text='First',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    fact2 = DurableFact(
        user_id=user_id,
        subject='Subject B',
        fact_text='Second',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add_all([fact1, fact2])
    await db_session.commit()
    await db_session.refresh(fact2)

    memory_storage = Mock()
    memory_storage.query_durable_fact_candidates.side_effect = RuntimeError(
        'Chroma unavailable'
    )
    service = ContextAssemblyService(memory_storage=memory_storage)

    result = await service.assemble_context_new_conversation(
        db_session,
        user_id=user_id,
        user_message='hello',
    )

    assert result.selection_method == 'recency'
    assert result.fact_ids[0] == fact2.id
    assert result.candidate_fact_ids == []


async def test_fact_selection_new_conversation_uses_recency(
    db_session: AsyncSession,
):
    """New conversations without Chroma fall back to recency selection."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create facts
    fact1 = DurableFact(
        user_id=user_id,
        subject='Subject A',
        fact_text='First',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact1)
    await db_session.commit()

    fact2 = DurableFact(
        user_id=user_id,
        subject='Subject B',
        fact_text='Second',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
        active=True,
    )
    db_session.add(fact2)
    await db_session.commit()

    # Assemble context for new conversation (no recent turns)
    result = await service.assemble_context_new_conversation(
        db_session,
        user_id=user_id,
        user_message='Hello, can you help?',
    )

    # Should use recency method
    assert result.selection_method == 'recency'
    # Should include the most recent fact first
    assert fact2.id in result.fact_ids


async def test_fact_selection_respects_max_candidates_limit(
    db_session: AsyncSession,
):
    """Fact selection loads some pool size and then ranks, not the full DB."""
    service = ContextAssemblyService()
    user_id = 'user-123'

    # Create many facts (more than MAX_FACT_CANDIDATES)
    for i in range(MAX_FACT_CANDIDATES + 5):
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

    # Assemble context for new conversation
    result = await service.assemble_context_new_conversation(
        db_session,
        user_id=user_id,
        user_message='Hello',
    )

    # Should only include MAX_DURABLE_FACTS, loaded from MAX_FACT_CANDIDATES pool
    assert len(result.fact_ids) <= MAX_DURABLE_FACTS
