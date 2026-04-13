"""Tests for canonical memory models."""

from datetime import datetime, timezone
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from assistant.models.conversation_sql import Conversation
from assistant.models.memory import (
    ConversationMemorySummaryRead,
    CreateDurableFactRequest,
    DurableFactCandidate,
    DurableFactRead,
    UpsertConversationMemorySummaryRequest,
)
from assistant.models.memory_sql import (
    ConversationMemorySummary,
    DurableFact,
    DurableFactConfidence,
    DurableFactSourceType,
)


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


@pytest.mark.asyncio
async def test_conversation_memory_summary_defaults(async_session):
    """It persists a single latest summary with sensible defaults."""
    conversation = Conversation(
        user_id='user-123',
        title='Research George Langley',
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    summary = ConversationMemorySummary(
        conversation_id=conversation.id,
        user_id=conversation.user_id,
        summary_text='The user is researching George Langley census records.',
    )
    async_session.add(summary)
    await async_session.commit()

    stmt = select(ConversationMemorySummary).where(
        ConversationMemorySummary.id == summary.id
    )
    result = await async_session.execute(stmt)
    persisted = result.scalar_one()

    assert persisted.version == 1
    assert persisted.source_message_id is None
    assert persisted.summary_text.startswith('The user is researching')
    assert persisted.created_at is not None
    assert persisted.updated_at is not None


@pytest.mark.asyncio
async def test_conversation_memory_summary_requires_unique_conversation(
    async_session,
):
    """It only allows one canonical summary row per conversation."""
    conversation = Conversation(
        user_id='user-123',
        title='Family tree',
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    first = ConversationMemorySummary(
        conversation_id=conversation.id,
        user_id=conversation.user_id,
        summary_text='Initial summary',
    )
    second = ConversationMemorySummary(
        conversation_id=conversation.id,
        user_id=conversation.user_id,
        summary_text='Duplicate summary',
    )

    async_session.add(first)
    await async_session.commit()

    async_session.add(second)
    with pytest.raises(IntegrityError):
        await async_session.commit()


@pytest.mark.asyncio
async def test_durable_fact_defaults(async_session):
    """It persists a durable fact with default active state."""
    fact = DurableFact(
        user_id='user-123',
        subject='user',
        fact_key='user.home_city',
        fact_text='User lives in Sydney.',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.CONVERSATION,
    )
    async_session.add(fact)
    await async_session.commit()

    stmt = select(DurableFact).where(DurableFact.id == fact.id)
    result = await async_session.execute(stmt)
    persisted = result.scalar_one()

    assert persisted.active is True
    assert persisted.fact_key == 'user.home_city'
    assert persisted.confidence == DurableFactConfidence.HIGH
    assert persisted.source_type == DurableFactSourceType.CONVERSATION
    assert persisted.source_excerpt is None
    assert persisted.created_at is not None
    assert persisted.updated_at is not None


def test_memory_read_models_preserve_fields():
    """It exposes stable typed read models for services and APIs."""
    now = datetime(2026, 4, 13, 8, 30, tzinfo=timezone.utc)
    conversation_id = uuid.uuid4()
    message_id = uuid.uuid4()
    fact_id = uuid.uuid4()

    summary = ConversationMemorySummaryRead(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        user_id='user-123',
        summary_text='Summary text',
        source_message_id=message_id,
        version=2,
        created_at=now,
        updated_at=now,
    )
    fact = DurableFactRead(
        id=fact_id,
        user_id='user-123',
        subject='person.george_langley',
        fact_key='person.george_langley.birth_year',
        fact_text='George Langley was born in 1884.',
        confidence=DurableFactConfidence.MEDIUM,
        source_type=DurableFactSourceType.TOOL,
        source_conversation_id=conversation_id,
        source_message_id=message_id,
        source_excerpt='1911 census lists age 27.',
        active=True,
        created_at=now,
        updated_at=now,
    )

    assert summary.version == 2
    assert summary.source_message_id == message_id
    assert fact.confidence == DurableFactConfidence.MEDIUM
    assert fact.source_type == DurableFactSourceType.TOOL
    assert fact.fact_key == 'person.george_langley.birth_year'


def test_memory_write_models_capture_extraction_outputs():
    """It provides typed request and candidate shapes for extraction flows."""
    summary_request = UpsertConversationMemorySummaryRequest(
        conversation_id=uuid.uuid4(),
        user_id='user-123',
        summary_text='Refreshed summary',
    )
    fact_request = CreateDurableFactRequest(
        user_id='user-123',
        subject='user',
        fact_key='user.preference.primary_sources',
        fact_text='User prefers primary sources over summaries.',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.USER_EXPLICIT,
        source_excerpt='Please use primary records whenever possible.',
    )
    candidate = DurableFactCandidate(
        subject='person.george_langley',
        fact_key='person.george_langley.birth_year',
        fact_text='George Langley was born in 1884.',
        confidence=DurableFactConfidence.MEDIUM,
        source_type=DurableFactSourceType.TOOL,
        source_excerpt='1911 census age suggests 1884 birth year.',
    )

    assert summary_request.summary_text == 'Refreshed summary'
    assert fact_request.source_type == DurableFactSourceType.USER_EXPLICIT
    assert fact_request.fact_key == 'user.preference.primary_sources'
    assert candidate.confidence == DurableFactConfidence.MEDIUM
    assert candidate.source_excerpt is not None
