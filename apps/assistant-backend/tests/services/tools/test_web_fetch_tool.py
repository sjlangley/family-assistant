"""Test the web fetch tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from assistant.models.tool import ToolExecutionStatus
from assistant.services.tool_service import ToolService
from assistant.services.tools.factory import ToolFactory
from assistant.services.tools.web_fetch import WebFetchTool


@pytest.fixture
def mock_http_client():
    """Mock httpx.AsyncClient for web fetch tests."""
    with patch('assistant.services.tools.web_fetch.httpx.AsyncClient') as mock:
        mock_instance = AsyncMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def web_fetch_tool_fixture():
    """Create tool synchronously (fixture)."""
    tool = WebFetchTool()
    return tool


@pytest.mark.asyncio
async def test_web_fetch_tool_basic():
    """Test basic web fetch tool execution."""
    service = ToolService(factory=ToolFactory(tools=[WebFetchTool()]))

    with patch(
        'assistant.services.tools.web_fetch.httpx.AsyncClient'
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value = mock_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = (
            '<html><head><title>Test Page</title></head></html>'
        )
        mock_instance.get.return_value = mock_response

        url = 'http://example.com'
        result = await service.execute_tool(
            name='web_fetch',
            arguments={'url': url},
        )
        assert result.tool_name == 'web_fetch'
        assert result.status == ToolExecutionStatus.SUCCESS


@pytest.mark.asyncio
async def test_web_fetch_client_reuse(web_fetch_tool_fixture, mock_http_client):
    """Verify client is reused across multiple calls."""
    try:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><title>Test</title></html>'
        mock_http_client.get.return_value = mock_response

        # First call
        await web_fetch_tool_fixture._perform_fetch('https://example.com')
        first_client = web_fetch_tool_fixture._http_client

        # Second call - should reuse same client
        await web_fetch_tool_fixture._perform_fetch('https://example.com/page2')
        second_client = web_fetch_tool_fixture._http_client

        # Verify same instance
        assert first_client is second_client
        # Verify both calls were made
        assert mock_http_client.get.call_count == 2
    finally:
        await web_fetch_tool_fixture.close()


@pytest.mark.asyncio
async def test_web_fetch_extracts_title(
    web_fetch_tool_fixture, mock_http_client
):
    """Test that title is extracted correctly."""
    try:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><title>My Page Title</title></html>'
        mock_http_client.get.return_value = mock_response

        result = await web_fetch_tool_fixture._perform_fetch(
            'https://example.com'
        )

        assert result['title'] == 'My Page Title'
    finally:
        await web_fetch_tool_fixture.close()


@pytest.mark.asyncio
async def test_web_fetch_extracts_content(
    web_fetch_tool_fixture, mock_http_client
):
    """Test that content is extracted from main element."""
    try:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <body>
                <main>
                    <p>This is the main content.</p>
                    <p>More content here.</p>
                </main>
            </body>
        </html>
        """
        mock_http_client.get.return_value = mock_response

        result = await web_fetch_tool_fixture._perform_fetch(
            'https://example.com'
        )

        assert 'main content' in result['content'].lower()
    finally:
        await web_fetch_tool_fixture.close()


@pytest.mark.asyncio
async def test_web_fetch_extracts_excerpt(
    web_fetch_tool_fixture, mock_http_client
):
    """Test that excerpt is extracted from first paragraph."""
    try:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <body>
                <p>This is the first paragraph excerpt.</p>
                <p>More content here.</p>
            </body>
        </html>
        """
        mock_http_client.get.return_value = mock_response

        result = await web_fetch_tool_fixture._perform_fetch(
            'https://example.com'
        )

        assert 'first paragraph excerpt' in result['excerpt']
    finally:
        await web_fetch_tool_fixture.close()


@pytest.mark.asyncio
async def test_web_fetch_handles_meta_description(
    web_fetch_tool_fixture, mock_http_client
):
    """Test that meta description is used for excerpt."""
    try:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <head>
                <meta name="description" content="Page from meta description">
            </head>
        </html>
        """
        mock_http_client.get.return_value = mock_response

        result = await web_fetch_tool_fixture._perform_fetch(
            'https://example.com'
        )

        assert result['excerpt'] == 'Page from meta description'
    finally:
        await web_fetch_tool_fixture.close()


@pytest.mark.asyncio
async def test_web_fetch_http_error(web_fetch_tool_fixture, mock_http_client):
    """Test handling of HTTP errors."""
    try:
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            'Not found',
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )

        with pytest.raises(ValueError, match='HTTP 404'):
            await web_fetch_tool_fixture._perform_fetch(
                'https://example.com/notfound'
            )
    finally:
        await web_fetch_tool_fixture.close()


@pytest.mark.asyncio
async def test_web_fetch_request_error(
    web_fetch_tool_fixture, mock_http_client
):
    """Test handling of request errors."""
    try:
        mock_http_client.get.side_effect = httpx.RequestError(
            'Connection failed'
        )

        with pytest.raises(ValueError, match='Failed to fetch'):
            await web_fetch_tool_fixture._perform_fetch('https://example.com')
    finally:
        await web_fetch_tool_fixture.close()


@pytest.mark.asyncio
async def test_web_fetch_close_client(web_fetch_tool_fixture):
    """Test that close properly closes the client."""
    # Initialize the client
    await web_fetch_tool_fixture._get_client()
    assert web_fetch_tool_fixture._http_client is not None

    # Close the tool
    await web_fetch_tool_fixture.close()

    # Client should be None
    assert web_fetch_tool_fixture._http_client is None
