"""Service layer for exposing and executing allowed tools."""

from assistant.models.llm import ChatCompletionTool
from assistant.models.tool import ToolExecutionResult
from assistant.services.tools.factory import ToolFactory


class ToolService:
    """Thin orchestration layer over the explicit tool factory."""

    def __init__(self, factory: ToolFactory) -> None:
        self.factory = factory

    def get_available_tools(self) -> list[ChatCompletionTool]:
        """Return the tool definitions exposed to the model for this process."""

        return self.factory.definitions()

    async def execute_tool(
        self, *, name: str, arguments: dict
    ) -> ToolExecutionResult:
        """Execute one named tool with already-parsed arguments."""

        tool = self.factory.get(name)
        return await tool.execute(arguments)
