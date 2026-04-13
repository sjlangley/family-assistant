from datetime import datetime
from typing import Literal
import uuid

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import Field, Relationship, SQLModel

from assistant.models.annotations import AssistantAnnotations


class Conversation(SQLModel, table=True):
    __tablename__ = 'conversations'  # type: ignore[assignment]
    __table_args__ = (
        Index('conversations_user_created_idx', 'user_id', 'created_at'),
    )
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(UUID(as_uuid=True), primary_key=True, nullable=False),
    )
    user_id: str = Field(
        sa_column=Column(String(255), nullable=False, index=True),
    )
    title: str = Field(
        sa_column=Column(Text, nullable=False),
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

    messages: list['Message'] = Relationship(
        back_populates='conversation',
        sa_relationship_kwargs={
            'cascade': 'all, delete-orphan',
            'order_by': 'Message.sequence_number',
        },
    )


class Message(SQLModel, table=True):
    __tablename__ = 'messages'  # type: ignore[assignment]
    __table_args__ = (
        CheckConstraint(
            "role in ('user', 'assistant')",
            name='messages_role_check',
        ),
        Index(
            'messages_conversation_sequence_idx',
            'conversation_id',
            'sequence_number',
            unique=True,
        ),
        Index(
            'messages_conversation_created_idx',
            'conversation_id',
            'created_at',
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
    role: Literal['user', 'assistant'] = Field(
        sa_column=Column(String(255), nullable=False),
    )
    content: str = Field(
        sa_column=Column(Text, nullable=False),
    )
    sequence_number: int = Field(nullable=False)
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    error: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    annotations: AssistantAnnotations | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    conversation: Conversation = Relationship(back_populates='messages')
