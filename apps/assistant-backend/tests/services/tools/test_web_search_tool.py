"""Test the current time tool."""

from unittest.mock import MagicMock, patch

import pytest

from assistant.models.tool import ToolExecutionStatus, WebSearchPayload
from assistant.services.tool_service import ToolService
from assistant.services.tools.factory import ToolFactory
from assistant.services.tools.web_search import WebSearchTool


@pytest.fixture
def mock_ddgs():
    with patch('assistant.services.tools.web_search.DDGS') as mock:
        mock_instance = MagicMock()
        mock.return_value.__enter__ = MagicMock(return_value=mock_instance)
        mock.return_value.__exit__ = MagicMock(return_value=None)
        yield mock_instance


@pytest.mark.asyncio
async def test_execute_web_search_tool(mock_ddgs):

    mock_ddgs.text.return_value = [
        {'title': 'First', 'href': 'url1', 'body': 'snippet1'},
        {'title': 'Second', 'href': 'url2', 'body': 'snippet2'},
    ]

    service = ToolService(factory=ToolFactory(tools=[WebSearchTool()]))

    number_of_results = 2
    result = await service.execute_tool(
        name='web_search',
        arguments={'query': 'test', 'num_results': number_of_results},
    )

    mock_ddgs.text.assert_called_once_with(
        'test', max_results=number_of_results
    )

    assert result.tool_name == 'web_search'
    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.payload is not None
    assert isinstance(result.payload, WebSearchPayload)
    assert result.payload.kind == 'web_search'
    assert len(result.payload.results) == number_of_results
    assert result.payload.results[0].title == 'First'
    assert result.payload.results[0].url == 'url1'
    assert result.payload.results[0].snippet == 'snippet1'
    assert result.llm_context == (
        'Web search results for: test\n'
        '\n'
        '1. First\n'
        'URL: url1\n'
        'Snippet: snippet1\n'
        '\n'
        '2. Second\n'
        'URL: url2\n'
        'Snippet: snippet2'
    )


@pytest.mark.asyncio
async def test_execute_web_search_tool_no_results(mock_ddgs):

    mock_ddgs.text.return_value = []

    service = ToolService(factory=ToolFactory(tools=[WebSearchTool()]))

    number_of_results = 2
    result = await service.execute_tool(
        name='web_search',
        arguments={'query': 'test', 'num_results': number_of_results},
    )

    assert result.tool_name == 'web_search'
    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.payload is not None
    assert isinstance(result.payload, WebSearchPayload)
    assert result.payload.kind == 'web_search'
    assert len(result.payload.results) == 0
    assert result.llm_context == 'Web search results for: test'
