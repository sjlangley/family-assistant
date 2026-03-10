from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern='^(system|user|assistant)$')
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int | None = 512


class ChatResponse(BaseModel):
    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
