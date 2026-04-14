"""Explicit allowlist and lookup helpers for supported tools."""

from assistant.services.tools.base import BaseTool
from assistant.services.tools.errors import UnsupportedToolError


class ToolFactory:
    """Own the enabled tool set for the current backend process."""

    def __init__(self, tools: list[BaseTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def definitions(self) -> list[dict]:
        """Return model-facing definitions for all enabled tools."""

        return [
            tool.definition()
            for tool in self._tools.values()
            if tool.is_enabled()
        ]

    def get(self, name: str) -> BaseTool:
        """Resolve one tool by name or raise a typed lookup error."""

        try:
            return self._tools[name]
        except KeyError as exc:
            raise UnsupportedToolError(name) from exc
