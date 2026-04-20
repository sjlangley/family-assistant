"""Web Search tool for retrieving relevant information from the web."""

import asyncio
from datetime import UTC, datetime
import logging

from ddgs import DDGS

from assistant.models.llm import ChatCompletionTool
from assistant.models.tool import (
    ToolCallRecord,
    ToolExecutionResult,
    ToolExecutionStatus,
    WebSearchPayload,
    WebSearchResultPayload,
)
from assistant.services.tools.base import BaseTool

logger = logging.getLogger(__name__)

DEFAULT_NUMBER_OF_RESULTS = 5


class WebSearchTool(BaseTool):
    """Perform a web search and return structured results."""

    name = 'web_search'

    def definition(self) -> ChatCompletionTool:
        """Expose the tool definition to the model."""

        return ChatCompletionTool(
            type='function',
            function={
                'name': self.name,
                'description': 'Perform a web search and return relevant results.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'query': {
                            'type': 'string',
                            'description': 'The search query to execute.',
                        },
                        'num_results': {
                            'type': 'integer',
                            'description': 'The number of search results to return.',
                            'default': DEFAULT_NUMBER_OF_RESULTS,
                        },
                    },
                    'required': ['query'],
                    'additionalProperties': False,
                },
            },
        )

    async def execute(self, arguments: dict) -> ToolExecutionResult:
        """Execute the web search and return structured results."""

        started_at = datetime.now(UTC)

        query = arguments['query']
        num_results = arguments.get('num_results', DEFAULT_NUMBER_OF_RESULTS)

        logger.debug(
            'web_search start: query_length=%d num_results=%s',
            len(query),
            num_results,
        )

        results = await asyncio.to_thread(
            self._perform_search, query, num_results
        )

        payload = WebSearchPayload(
            kind=self.name,
            results=results,
        )

        finished_at = datetime.now(UTC)

        logger.debug(
            'web_search done: results=%s duration_ms=%s',
            len(results),
            int((finished_at - started_at).total_seconds() * 1000),
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
            llm_context=self._build_llm_context(query, results),
            annotation_inputs={
                'tool_name': self.name,
                'label': f'Web search for "{query}"',
            },
            payload=payload,
        )

    def _perform_search(
        self, query: str, num_results: int
    ) -> list[WebSearchResultPayload]:
        """Perform the web search using DuckDuckGo Search API."""

        with DDGS() as ddgs:
            search_results = ddgs.text(query, max_results=num_results)

        results = []
        for result in search_results:
            results.append(
                WebSearchResultPayload(
                    title=result.get('title', ''),
                    url=result.get('href', ''),
                    snippet=result.get('body', ''),
                )
            )

        return results

    def _build_llm_context(
        self, query: str, results: list[WebSearchResultPayload]
    ) -> str:
        lines = [f'Web search results for: {query}', '']
        for index, result in enumerate(results, start=1):
            lines.extend(
                [
                    f'{index}. {result.title or "Untitled"}',
                    f'URL: {result.url}',
                    f'Snippet: {result.snippet or "No snippet available."}',
                    '',
                ]
            )
        return '\n'.join(lines).strip()
