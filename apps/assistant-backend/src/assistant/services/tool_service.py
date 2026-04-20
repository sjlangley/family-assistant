"""Service layer for exposing and executing allowed tools."""

import logging
import time

from assistant.models.llm import ChatCompletionTool
from assistant.models.tool import ToolExecutionResult
from assistant.services.tools.factory import ToolFactory

logger = logging.getLogger(__name__)


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
        started = time.perf_counter()
        logger.debug(
            'tool execute requested: name=%s arg_keys=%s',
            name,
            sorted(arguments.keys()),
        )
        tool = self.factory.get(name)
        try:
            result = await tool.execute(arguments)
            logger.debug(
                'tool execute succeeded: name=%s status=%s duration_ms=%s',
                name,
                result.status.value,
                int((time.perf_counter() - started) * 1000),
            )
            return result
        except Exception:
            logger.debug(
                'tool execute failed: name=%s duration_ms=%s',
                name,
                int((time.perf_counter() - started) * 1000),
                exc_info=True,
            )
            raise
