"""Web Search tool for retrieving relevant information from the web."""

from datetime import UTC, datetime

from bs4 import BeautifulSoup
import httpx

from assistant.models.llm import ChatCompletionTool
from assistant.models.tool import (
    ToolCallRecord,
    ToolExecutionResult,
    ToolExecutionStatus,
    WebFetchPayload,
)
from assistant.services.tools.base import BaseTool


class WebFetchTool(BaseTool):
    """Perform a web fetch and return structured results."""

    name = 'web_fetch'

    def __init__(self) -> None:
        """Initialize the tool."""
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client (lazy initialization)."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def definition(self) -> ChatCompletionTool:
        """Expose the tool definition to the model."""

        return ChatCompletionTool(
            type='function',
            function={
                'name': self.name,
                'description': 'Perform a web fetch and return relevant results.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'url': {
                            'type': 'string',
                            'description': 'The URL to fetch.',
                        },
                    },
                    'required': ['url'],
                    'additionalProperties': False,
                },
            },
        )

    async def execute(self, arguments: dict) -> ToolExecutionResult:
        """Execute the web fetch and return structured results."""

        started_at = datetime.now(UTC)

        # Placeholder implementation - replace with actual web fetch logic
        url = arguments['url']

        result = await self._perform_fetch(url)

        payload = WebFetchPayload(
            kind=self.name,
            url=url,
            title=result.get('title', ''),
            content=result.get('content', ''),
            excerpt=result.get('excerpt', ''),
        )

        finished_at = datetime.now(UTC)

        return ToolExecutionResult(
            tool_name=self.name,
            status=ToolExecutionStatus.SUCCESS,
            tool_call=ToolCallRecord(
                name=self.name,
                arguments=arguments,
                started_at=started_at,
                finished_at=finished_at,
                status=ToolExecutionStatus.SUCCESS,
            ),
            llm_context=f'Web fetch for "{url}" completed successfully.',
            annotation_inputs={
                'tool_name': self.name,
                'label': f'Web fetch for "{url}"',
            },
            payload=payload,
        )

    async def _perform_fetch(self, url: str) -> dict:
        """Perform the web fetch using a cached async HTTP client."""
        try:
            client = await self._get_client()
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

            # Parse HTML content
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract title
            title = ''
            if soup.title:
                title = soup.title.string
            elif soup.find('h1'):
                title = soup.find('h1').get_text(strip=True)

            # Extract main content
            content = ''
            main_content = (
                soup.find('main')
                or soup.find('article')
                or soup.find(['div', 'section'])
            )
            if main_content:
                content = main_content.get_text(separator=' ', strip=True)[
                    :2000
                ]

            # Extract excerpt
            excerpt = ''
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                excerpt = meta_desc['content']
            else:
                first_p = soup.find('p')
                if first_p:
                    excerpt = first_p.get_text(strip=True)[:200]

            return {
                'title': title,
                'content': content,
                'excerpt': excerpt,
            }

        except httpx.HTTPStatusError as e:
            raise ValueError(
                f'Failed to fetch {url}: HTTP {e.response.status_code}'
            ) from e
        except httpx.RequestError as e:
            raise ValueError(f'Failed to fetch {url}: {str(e)}') from e
        except Exception as e:
            raise ValueError(f'Error parsing {url}: {str(e)}') from e
