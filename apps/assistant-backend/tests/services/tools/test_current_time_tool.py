"""Test the current time tool."""

import pytest

from assistant.models.tool import TimePayload, ToolExecutionStatus
from assistant.services.tool_service import ToolService
from assistant.services.tools.current_time import CurrentTimeTool
from assistant.services.tools.factory import ToolFactory


@pytest.mark.asyncio
async def test_execute_current_time_tool():
    service = ToolService(factory=ToolFactory(tools=[CurrentTimeTool()]))

    result = await service.execute_tool(
        name='get_current_time',
        arguments={},
    )

    assert result.tool_name == 'get_current_time'
    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.payload is not None
    assert isinstance(result.payload, TimePayload)
    assert 'Current server time:' in result.llm_context
