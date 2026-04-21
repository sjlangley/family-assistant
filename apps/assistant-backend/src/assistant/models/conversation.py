from datetime import datetime
from typing import Literal
import uuid

from pydantic import BaseModel, Field

from assistant.models.annotations import AssistantAnnotations


class ConversationSummary(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    id: uuid.UUID
    role: Literal['user', 'assistant']
    content: str
    sequence_number: int
    created_at: datetime
    error: str | None = None
    annotations: AssistantAnnotations | None = None


class CreateConversationWithMessageRequest(BaseModel):
    content: str
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=4096)
    stream: bool = False


class CreateMessageRequest(BaseModel):
    content: str
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=4096)
    stream: bool = False


class ConversationWithMessagesResponse(BaseModel):
    conversation: ConversationSummary
    user_message: MessageRead
    assistant_message: MessageRead


class ListConversationsResponse(BaseModel):
    items: list[ConversationSummary]


class GetConversationMessagesResponse(BaseModel):
    conversation: ConversationSummary
    items: list[MessageRead]
