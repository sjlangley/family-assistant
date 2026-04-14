"""Tests for the shared tool service and first concrete tool."""

import pytest

from assistant.services.tool_service import ToolService
from assistant.services.tools.current_time import CurrentTimeTool
from assistant.services.tools.errors import UnsupportedToolError
from assistant.services.tools.factory import ToolFactory


def test_get_available_tools_returns_current_time_definition():
    service = ToolService(factory=ToolFactory(tools=[CurrentTimeTool()]))

    tools = service.get_available_tools()

    assert len(tools) == 1
    assert tools[0].function.name == 'get_current_time'


@pytest.mark.asyncio
async def test_execute_unknown_tool_raises():
    service = ToolService(factory=ToolFactory(tools=[CurrentTimeTool()]))

    with pytest.raises(UnsupportedToolError):
        await service.execute_tool(
            name='does_not_exist',
            arguments={},
        )
