"""Base classes and exceptions for tools."""

from abc import ABC, abstractmethod

from assistant.models.llm import ChatCompletionTool
from assistant.models.tool import ToolExecutionResult


class BaseTool(ABC):
    """Abstract contract implemented by every concrete tool."""

    name: str

    @abstractmethod
    def definition(self) -> ChatCompletionTool:
        """Return the OpenAI-compatible tool definition exposed to the model."""
        ...

    @abstractmethod
    async def execute(self, arguments: dict) -> ToolExecutionResult:
        """Execute the tool and return a normalized result envelope."""
        ...

    def is_enabled(self) -> bool:
        """Allow tools to be disabled without removing them from wiring."""

        return True
