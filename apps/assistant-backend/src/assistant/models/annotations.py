from enum import StrEnum

from pydantic import BaseModel, Field


class ToolAnnotationStatus(StrEnum):
    COMPLETED = 'completed'
    FAILED = 'failed'


class FailureAnnotationStage(StrEnum):
    LLM = 'llm'
    TOOL = 'tool'
    ANNOTATION = 'annotation'
    UNKNOWN = 'unknown'


class SourceAnnotation(BaseModel):
    title: str
    url: str
    snippet: str
    rationale: str


class ToolAnnotation(BaseModel):
    name: str
    status: ToolAnnotationStatus


class MemoryHitAnnotation(BaseModel):
    label: str
    summary: str


class MemorySavedAnnotation(BaseModel):
    label: str
    summary: str


class FailureAnnotation(BaseModel):
    stage: FailureAnnotationStage
    retryable: bool = False
    detail: str | None = None


class AssistantAnnotations(BaseModel):
    sources: list[SourceAnnotation] = Field(default_factory=list)
    tools: list[ToolAnnotation] = Field(default_factory=list)
    memory_hits: list[MemoryHitAnnotation] = Field(default_factory=list)
    memory_saved: list[MemorySavedAnnotation] = Field(default_factory=list)
    failure: FailureAnnotation | None = None
