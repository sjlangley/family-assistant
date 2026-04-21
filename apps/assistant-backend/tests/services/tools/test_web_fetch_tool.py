"""Test the web fetch tool."""

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from assistant.models.tool import ToolExecutionStatus
from assistant.services.tool_service import ToolService
from assistant.services.tools.factory import ToolFactory
from assistant.services.tools.web_fetch import UnsafeUrlError, WebFetchTool


@pytest.fixture
def mock_http_client():
    """Mock httpx.AsyncClient for web fetch tests."""
    with patch('assistant.services.tools.web_fetch.httpx.AsyncClient') as mock:
        with patch.object(
            WebFetchTool,
            '_resolve_host_ips',
            new=AsyncMock(return_value={'93.184.216.34'}),
        ):
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
        mock_response.is_redirect = False
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.text = (
            '<html><head><title>Test Page</title></head></html>'
        )
        mock_response.raise_for_status = MagicMock()
        mock_instance.get.return_value = mock_response

        # Mock the URL validation method
        with patch.object(
            WebFetchTool, '_assert_public_url', new_callable=AsyncMock
        ):
            url = 'http://example.com'
            result = await service.execute_tool(
                name='web_fetch',
                arguments={'url': url},
            )
            assert result.tool_name == 'web_fetch'
            assert result.status == ToolExecutionStatus.SUCCESS
            assert result.llm_context == (
                'Fetched page\n'
                'URL: http://example.com\n'
                'Title: Test Page\n'
                '\n'
                'Excerpt:\n'
                'No excerpt available.\n'
                '\n'
                'Content:\n'
                'No readable content extracted.'
            )


@pytest.mark.asyncio
async def test_web_fetch_tool_with_content():
    """Test basic web fetch tool execution."""
    service = ToolService(factory=ToolFactory(tools=[WebFetchTool()]))

    with patch(
        'assistant.services.tools.web_fetch.httpx.AsyncClient'
    ) as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value = mock_instance

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.is_redirect = False
        mock_response.text = (
            '<html>'
            '<head><title>Test Page</title>'
            '<meta name="description" content="This is a test page excerpt">'
            '</head>'
            '<body><h1>Main Heading</h1>'
            '<main><p>This is the main content.</p></main></body>'
            '</html>'
        )
        mock_response.raise_for_status = MagicMock()  # Sync method, not async
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_instance.get.return_value = mock_response

        # Mock the URL validation method
        with patch.object(
            WebFetchTool, '_assert_public_url', new_callable=AsyncMock
        ):
            url = 'http://example.com'
            result = await service.execute_tool(
                name='web_fetch',
                arguments={'url': url},
            )
            assert result.tool_name == 'web_fetch'
            assert result.status == ToolExecutionStatus.SUCCESS
            assert 'Fetched page' in result.llm_context
            assert 'Test Page' in result.llm_context
            assert 'This is a test page excerpt' in result.llm_context
            assert 'This is the main content.' in result.llm_context


@pytest.mark.asyncio
async def test_web_fetch_client_reuse(web_fetch_tool_fixture, mock_http_client):
    """Verify client is reused across multiple calls."""
    try:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_redirect = False
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.text = '<html><title>Test</title></html>'
        mock_response.raise_for_status = MagicMock()
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
        mock_response.is_redirect = False
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.text = '<html><title>My Page Title</title></html>'
        mock_response.raise_for_status = MagicMock()
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
        mock_response.is_redirect = False
        mock_response.headers = {'Content-Type': 'text/html'}
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
        mock_response.raise_for_status = MagicMock()
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
        mock_response.is_redirect = False
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.text = """
        <html>
            <body>
                <p>This is the first paragraph excerpt.</p>
                <p>More content here.</p>
            </body>
        </html>
        """
        mock_response.raise_for_status = MagicMock()
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
        mock_response.is_redirect = False
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.text = """
        <html>
            <head>
                <meta name="description" content="Page from meta description">
            </head>
        </html>
        """
        mock_response.raise_for_status = MagicMock()
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


@pytest.mark.asyncio
async def test_web_fetch_rejects_private_ip():
    """It blocks direct requests to private IP ranges."""
    with pytest.raises(UnsafeUrlError, match='non-public IP address'):
        await WebFetchTool._assert_public_url('http://127.0.0.1:8000')


@pytest.mark.asyncio
async def test_web_fetch_rejects_localhost():
    """It blocks localhost URLs before any request is sent."""
    with pytest.raises(UnsafeUrlError, match='Localhost'):
        await WebFetchTool._assert_public_url('http://localhost:8000')


@pytest.mark.asyncio
async def test_web_fetch_rejects_non_http_scheme():
    """It only allows http and https fetches."""
    with pytest.raises(UnsafeUrlError, match='Only http and https'):
        await WebFetchTool._assert_public_url('file:///etc/passwd')


@pytest.mark.asyncio
async def test_web_fetch_rejects_redirect_to_private_host(
    web_fetch_tool_fixture, mock_http_client
):
    """It validates every redirect hop before following it."""
    try:
        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.is_redirect = True
        redirect_response.headers = {'location': 'http://127.0.0.1/internal'}

        mock_http_client.get.return_value = redirect_response

        with pytest.raises(
            ValueError, match='Host resolves to a non-public IP address'
        ):
            await web_fetch_tool_fixture._perform_fetch('https://example.com')
    finally:
        await web_fetch_tool_fixture.close()


@pytest.mark.asyncio
async def test_web_fetch_rejects_hostname_resolving_to_private_ip():
    """It blocks DNS names that resolve to private addresses."""
    with patch(
        'assistant.services.tools.web_fetch.socket.getaddrinfo',
        return_value=[
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                '',
                ('10.0.0.8', 0),
            )
        ],
    ):
        with pytest.raises(UnsafeUrlError, match='non-public IP address'):
            await WebFetchTool._assert_public_url('https://internal.example')
