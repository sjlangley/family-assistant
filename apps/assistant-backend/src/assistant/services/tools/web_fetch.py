"""Web Fetch tool for retrieving relevant information from the web."""

import asyncio
from datetime import UTC, datetime
import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlsplit

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

logger = logging.getLogger(__name__)

DEFAULT_FETCH_TIMEOUT_SECONDS = 10.0
MAXIMUM_REDIRECTS = 5
ALLOWED_FETCH_SCHEMES = {'http', 'https'}


class UnsafeUrlError(ValueError):
    """Raised when a fetch URL is not safe to request from the backend."""


class WebFetchTool(BaseTool):
    """Perform a web fetch and return structured results."""

    name = 'web_fetch'

    def __init__(self) -> None:
        """Initialize the tool."""
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client (lazy initialization)."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=DEFAULT_FETCH_TIMEOUT_SECONDS,
                trust_env=False,
            )
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

        url = arguments['url']

        logger.debug('Starting web fetch for url: %s', url)

        result = await self._perform_fetch(url)

        payload = WebFetchPayload(
            kind=self.name,
            url=url,
            title=result.get('title', ''),
            content=result.get('content', ''),
            excerpt=result.get('excerpt', ''),
        )

        finished_at = datetime.now(UTC)

        logger.debug(
            'Web fetch completed for url=%s title=%r content_length=%d '
            'excerpt_length=%d',
            payload.url,
            payload.title,
            len(payload.content),
            len(payload.excerpt),
        )

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
            llm_context=self._build_llm_context(
                url=url,
                title=result.get('title'),
                excerpt=result.get('excerpt'),
                content=result.get('content', ''),
            ),
            annotation_inputs={
                'tool_name': self.name,
                'label': f'Web fetch for "{url}"',
            },
            payload=payload,
        )

    async def _perform_fetch(self, url: str) -> dict:
        """Perform the web fetch using a cached async HTTP client."""
        try:
            await self._assert_public_url(url)
            client = await self._get_client()
            current_url = url
            response: httpx.Response | None = None

            for _ in range(MAXIMUM_REDIRECTS + 1):
                response = await client.get(current_url, follow_redirects=False)

                if response.is_redirect:
                    location = response.headers.get('location')
                    if not location:
                        raise ValueError(
                            'Redirect response missing Location header'
                        )

                    current_url = urljoin(current_url, location)
                    await self._assert_public_url(current_url)
                    continue

                response.raise_for_status()
                break
            else:
                raise ValueError(f'Failed to fetch {url}: too many redirects')

            if response is None:
                raise RuntimeError(
                    'Fetch completed without receiving an HTTP response'
                )

            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type:
                raise ValueError('The URL did not return an HTML document')

            # Parse HTML content
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract title
            title = ''
            if soup.title:
                title = soup.title.string
            elif soup.find('h1'):
                # pyrefly: ignore [missing-attribute]
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

    @staticmethod
    async def _resolve_host_ips(hostname: str) -> set[str]:
        """Resolve a hostname to IP addresses without blocking the event loop."""
        address_info = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )
        # pyrefly: ignore [bad-return]
        return {info[4][0] for info in address_info}

    @classmethod
    async def _assert_public_url(cls, url: str) -> None:
        """Reject URLs that target local or otherwise non-public hosts."""
        parsed = urlsplit(url)

        if parsed.scheme not in ALLOWED_FETCH_SCHEMES:
            raise UnsafeUrlError('Only http and https URLs are allowed')

        if not parsed.hostname:
            raise UnsafeUrlError('URL must include a hostname')

        if parsed.username or parsed.password:
            raise UnsafeUrlError(
                'URLs with embedded credentials are not allowed'
            )

        hostname = parsed.hostname.rstrip('.').lower()
        if hostname == 'localhost':
            raise UnsafeUrlError('Localhost is not allowed')

        try:
            candidate_ips = {str(ipaddress.ip_address(hostname))}
        except ValueError:
            candidate_ips = await cls._resolve_host_ips(hostname)

        for raw_ip in candidate_ips:
            candidate_ip = ipaddress.ip_address(raw_ip)
            if (
                candidate_ip.is_private
                or candidate_ip.is_loopback
                or candidate_ip.is_link_local
                or candidate_ip.is_multicast
                or candidate_ip.is_reserved
                or candidate_ip.is_unspecified
            ):
                raise UnsafeUrlError(
                    f'Host resolves to a non-public IP address: {raw_ip}'
                )

    def _build_llm_context(
        self,
        *,
        url: str,
        title: str | None,
        excerpt: str | None,
        content: str,
    ) -> str:
        return '\n'.join(
            [
                'Fetched page',
                f'URL: {url}',
                f'Title: {title or "Untitled"}',
                '',
                'Excerpt:',
                excerpt or 'No excerpt available.',
                '',
                'Content:',
                content or 'No readable content extracted.',
            ]
        ).strip()
