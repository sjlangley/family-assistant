"""Explicit allowlist and lookup helpers for supported tools."""

from assistant.models.llm import ChatCompletionTool
from assistant.services.tools.base import BaseTool
from assistant.services.tools.errors import UnsupportedToolError


class DisabledToolError(Exception):
    """Raised when a supported tool is currently disabled."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f'Tool is disabled: {name}')


class ToolFactory:
    """Own the enabled tool set for the current backend process."""

    def __init__(self, tools: list[BaseTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def definitions(self) -> list[ChatCompletionTool]:
        """Return model-facing definitions for all enabled tools."""

        return [
            tool.definition()
            for tool in self._tools.values()
            if tool.is_enabled()
        ]

    def get(self, name: str) -> BaseTool:
        """Resolve one enabled tool by name or raise a typed error."""

        try:
            tool = self._tools[name]
        except KeyError as exc:
            raise UnsupportedToolError(name) from exc

        if not tool.is_enabled():
            raise DisabledToolError(name)

        return tool
