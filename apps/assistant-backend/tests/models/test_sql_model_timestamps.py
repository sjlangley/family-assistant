"""Tests pinning DB-assigned timestamps on the SQL models.

``created_at`` / ``updated_at`` are populated by the database
(``server_default=func.now()``), so callers construct rows without them. These
tests guard that contract: the fields default to ``None`` on construction and
are never inserted as explicit NULLs.
"""

from datetime import datetime, timezone
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


@pytest_asyncio.fixture
async def async_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_maker() as session:
        yield session

    await engine.dispose()


def test_timestamps_default_to_none_when_not_provided():
    """It lets callers omit timestamps; the database assigns them."""
    conversation = Conversation(user_id='user-1', title='Title')
    message = Message(
        conversation_id=conversation.id,
        role='user',
        content='hello',
        sequence_number=1,
    )
    summary = ConversationMemorySummary(
        conversation_id=conversation.id,
        user_id='user-1',
        summary_text='summary',
    )
    fact = DurableFact(
        user_id='user-1',
        subject='subject',
        fact_text='fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.USER_EXPLICIT,
    )

    assert conversation.created_at is None
    assert conversation.updated_at is None
    assert message.created_at is None
    assert summary.created_at is None
    assert summary.updated_at is None
    assert fact.created_at is None
    assert fact.updated_at is None


@pytest.mark.asyncio
async def test_database_assigns_timestamps_on_insert(async_session):
    """It persists server-assigned timestamps rather than explicit NULLs."""
    conversation = Conversation(user_id='user-1', title='Title')
    async_session.add(conversation)
    await async_session.commit()

    message = Message(
        conversation_id=conversation.id,
        role='user',
        content='hello',
        sequence_number=1,
    )
    summary = ConversationMemorySummary(
        conversation_id=conversation.id,
        user_id='user-1',
        summary_text='summary',
    )
    fact = DurableFact(
        user_id='user-1',
        subject='subject',
        fact_text='fact',
        confidence=DurableFactConfidence.HIGH,
        source_type=DurableFactSourceType.USER_EXPLICIT,
    )
    async_session.add_all([message, summary, fact])
    await async_session.commit()

    for row in (conversation, message, summary, fact):
        await async_session.refresh(row)
        assert isinstance(row.created_at, datetime)
    for row in (conversation, summary, fact):
        assert isinstance(row.updated_at, datetime)


@pytest.mark.asyncio
async def test_explicit_timestamps_are_preserved(async_session):
    """It still honours timestamps passed explicitly by the caller."""
    created = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    conversation = Conversation(
        id=uuid.uuid4(),
        user_id='user-1',
        title='Title',
        created_at=created,
        updated_at=created,
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    assert conversation.created_at.replace(tzinfo=timezone.utc) == created
    assert conversation.updated_at.replace(tzinfo=timezone.utc) == created
