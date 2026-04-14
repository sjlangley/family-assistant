"""Shared models for tool definitions, execution metadata, and payloads."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class ToolExecutionStatus(StrEnum):
    """Normalized status values returned by all tools."""

    SUCCESS = 'success'
    ERROR = 'error'


class ToolCallRecord(BaseModel):
    """Metadata about one concrete tool execution."""

    name: str
    arguments: dict
    started_at: datetime
    finished_at: datetime
    status: ToolExecutionStatus


class TimePayload(BaseModel):
    """Structured payload for the current-time tool."""

    kind: Literal['get_current_time']
    iso_timestamp: str
    display_text: str


class WebSearchPayload(BaseModel):
    """Structured payload for a single web search result."""

    kind: Literal['web_search']
    title: str
    url: str
    snippet: str | None = None


class WebFetchPayload(BaseModel):
    """Structured payload for fetched page content."""

    kind: Literal['web_fetch']
    url: str
    title: str | None = None
    content: str
    excerpt: str | None = None


class ImageGenerationPayload(BaseModel):
    """Structured payload for generated image artifacts."""

    kind: Literal['image_generate']
    asset_url: str
    prompt: str
    revised_prompt: str | None = None
    mime_type: str = 'image/png'


class ToolError(BaseModel):
    """Normalized error shape returned by tool executions."""

    code: str
    message: str
    retryable: bool = False


ToolPayload = (
    WebSearchPayload | WebFetchPayload | ImageGenerationPayload | TimePayload
)


class ToolExecutionResult(BaseModel):
    """Stable envelope returned by every tool execution."""

    tool_name: str
    status: ToolExecutionStatus
    tool_call: ToolCallRecord
    llm_context: str | None = None
    annotation_inputs: dict | None = None
    payload: ToolPayload | None = None
    error: ToolError | None = None
