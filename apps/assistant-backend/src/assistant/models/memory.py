from datetime import datetime
import uuid

from pydantic import BaseModel

from assistant.models.memory_sql import (
    DurableFactConfidence,
    DurableFactSourceType,
)


class ConversationMemorySummaryRead(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    user_id: str
    summary_text: str
    source_message_id: uuid.UUID | None = None
    version: int
    created_at: datetime
    updated_at: datetime


class DurableFactRead(BaseModel):
    id: uuid.UUID
    user_id: str
    subject: str
    fact_key: str | None = None
    fact_text: str
    confidence: DurableFactConfidence
    source_type: DurableFactSourceType
    source_conversation_id: uuid.UUID | None = None
    source_message_id: uuid.UUID | None = None
    source_excerpt: str | None = None
    active: bool
    created_at: datetime
    updated_at: datetime


class UpsertConversationMemorySummaryRequest(BaseModel):
    conversation_id: uuid.UUID
    user_id: str
    summary_text: str
    source_message_id: uuid.UUID | None = None


class CreateDurableFactRequest(BaseModel):
    user_id: str
    subject: str
    fact_key: str | None = None
    fact_text: str
    confidence: DurableFactConfidence
    source_type: DurableFactSourceType
    source_conversation_id: uuid.UUID | None = None
    source_message_id: uuid.UUID | None = None
    source_excerpt: str | None = None


class DurableFactCandidate(BaseModel):
    subject: str
    fact_key: str | None = None
    fact_text: str
    confidence: DurableFactConfidence
    source_type: DurableFactSourceType
    source_excerpt: str | None = None
