from datetime import datetime
from enum import StrEnum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import Field, SQLModel


class DurableFactConfidence(StrEnum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


class DurableFactSourceType(StrEnum):
    CONVERSATION = 'conversation'
    TOOL = 'tool'
    USER_EXPLICIT = 'user_explicit'


class ConversationMemorySummary(SQLModel, table=True):
    __tablename__ = 'conversation_memory_summaries'  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint(
            'conversation_id',
            name='conversation_memory_summaries_conversation_id_key',
        ),
        Index(
            'conversation_memory_summaries_user_updated_idx',
            'user_id',
            'updated_at',
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(UUID(as_uuid=True), primary_key=True, nullable=False),
    )
    conversation_id: uuid.UUID = Field(
        foreign_key='conversations.id',
        nullable=False,
    )
    user_id: str = Field(
        sa_column=Column(String(255), nullable=False, index=True),
    )
    summary_text: str = Field(
        sa_column=Column(Text, nullable=False),
    )
    source_message_id: uuid.UUID | None = Field(
        default=None,
        foreign_key='messages.id',
        nullable=True,
    )
    version: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default='1'),
    )
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class DurableFact(SQLModel, table=True):
    __tablename__ = 'durable_facts'  # type: ignore[assignment]
    __table_args__ = (
        Index(
            'durable_facts_user_active_updated_idx',
            'user_id',
            'active',
            'updated_at',
        ),
        Index(
            'durable_facts_user_subject_idx',
            'user_id',
            'subject',
        ),
        Index(
            'durable_facts_user_fact_key_active_idx',
            'user_id',
            'fact_key',
            'active',
        ),
        Index('durable_facts_source_message_idx', 'source_message_id'),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(UUID(as_uuid=True), primary_key=True, nullable=False),
    )
    user_id: str = Field(
        sa_column=Column(String(255), nullable=False, index=True),
    )
    subject: str = Field(
        sa_column=Column(String(255), nullable=False),
    )
    fact_key: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )
    fact_text: str = Field(
        sa_column=Column(Text, nullable=False),
    )
    confidence: DurableFactConfidence = Field(
        sa_column=Column(String(32), nullable=False),
    )
    source_type: DurableFactSourceType = Field(
        sa_column=Column(String(32), nullable=False),
    )
    source_conversation_id: uuid.UUID | None = Field(
        default=None,
        foreign_key='conversations.id',
        nullable=True,
    )
    source_message_id: uuid.UUID | None = Field(
        default=None,
        foreign_key='messages.id',
        nullable=True,
    )
    source_excerpt: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    active: bool = Field(
        default=True,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text('true'),
        ),
    )
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )
