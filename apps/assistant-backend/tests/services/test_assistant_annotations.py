"""Tests for AssistantAnnotationService."""

from datetime import datetime, timezone

import pytest

from assistant.models.annotations import (
    FailureAnnotationStage,
    ToolAnnotationStatus,
)
from assistant.models.llm import (
    LLMCompletionError,
    LLMCompletionErrorKind,
)
from assistant.models.tool import (
    ToolCallRecord,
    ToolExecutionResult,
    ToolExecutionStatus,
    WebFetchPayload,
    WebSearchPayload,
    WebSearchResultPayload,
)
from assistant.services.assistant_annotations import (
    AssistantAnnotationService,
)


@pytest.fixture
def annotation_service():
    """Create an AssistantAnnotationService for testing."""
    return AssistantAnnotationService()


class TestSuccessAnnotations:
    """Test success annotation building."""

    def test_build_success_annotations_with_web_fetch_sources(
        self, annotation_service
    ):
        """Extract sources only from web_fetch results, not search snippets."""
        # Web search - should NOT produce sources
        web_search_result = ToolExecutionResult(
            tool_name='web_search',
            status=ToolExecutionStatus.SUCCESS,
            tool_call=ToolCallRecord(
                name='web_search',
                arguments={'query': 'test'},
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                status=ToolExecutionStatus.SUCCESS,
            ),
            payload=WebSearchPayload(
                kind='web_search',
                results=[
                    WebSearchResultPayload(
                        title='Result 1',
                        url='https://example.com/1',
                        snippet='Search snippet 1',
                    )
                ],
            ),
        )

        # Web fetch - should produce sources
        web_fetch_result = ToolExecutionResult(
            tool_name='web_fetch',
            status=ToolExecutionStatus.SUCCESS,
            tool_call=ToolCallRecord(
                name='web_fetch',
                arguments={'url': 'https://example.com/page'},
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                status=ToolExecutionStatus.SUCCESS,
            ),
            payload=WebFetchPayload(
                kind='web_fetch',
                url='https://example.com/page',
                title='Example Page',
                content='This is the full page content with lots of information.',
                excerpt='This is the full page content with lots of information.',
            ),
        )

        annotations = annotation_service.build_success_annotations(
            executed_tools=[web_search_result, web_fetch_result]
        )

        # Should have 1 source from fetch, 0 from search
        assert len(annotations.sources) == 1
        assert annotations.sources[0].title == 'Example Page'
        assert annotations.sources[0].url == 'https://example.com/page'
        assert (
            annotations.sources[0].snippet
            == 'This is the full page content with lots of information.'
        )

    def test_build_success_annotations_truncates_snippets(
        self, annotation_service
    ):
        """Truncate source snippets to max 240 chars."""
        long_content = 'x' * 500
        web_fetch_result = ToolExecutionResult(
            tool_name='web_fetch',
            status=ToolExecutionStatus.SUCCESS,
            tool_call=ToolCallRecord(
                name='web_fetch',
                arguments={'url': 'https://example.com'},
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                status=ToolExecutionStatus.SUCCESS,
            ),
            payload=WebFetchPayload(
                kind='web_fetch',
                url='https://example.com',
                title='Page',
                content=long_content,
                excerpt=None,
            ),
        )

        annotations = annotation_service.build_success_annotations(
            executed_tools=[web_fetch_result]
        )

        assert len(annotations.sources) == 1
        # Truncated text should be max 240 + "..." (may be fewer due to word boundary)
        assert len(annotations.sources[0].snippet) <= 243
        assert annotations.sources[0].snippet.endswith('...')

    def test_build_success_annotations_enforces_source_budget(
        self, annotation_service
    ):
        """Enforce max 3 sources budget."""
        fetches = []
        for i in range(5):
            result = ToolExecutionResult(
                tool_name='web_fetch',
                status=ToolExecutionStatus.SUCCESS,
                tool_call=ToolCallRecord(
                    name='web_fetch',
                    arguments={'url': f'https://example.com/{i}'},
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    status=ToolExecutionStatus.SUCCESS,
                ),
                payload=WebFetchPayload(
                    kind='web_fetch',
                    url=f'https://example.com/{i}',
                    title=f'Page {i}',
                    content=f'Content {i}',
                    excerpt=f'Excerpt {i}',
                ),
            )
            fetches.append(result)

        annotations = annotation_service.build_success_annotations(
            executed_tools=fetches
        )

        assert len(annotations.sources) == 3  # Max 3

    def test_build_success_annotations_includes_tool_usage(
        self, annotation_service
    ):
        """Include tool annotations for tools that ran."""
        search_result = ToolExecutionResult(
            tool_name='web_search',
            status=ToolExecutionStatus.SUCCESS,
            tool_call=ToolCallRecord(
                name='web_search',
                arguments={'query': 'test'},
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                status=ToolExecutionStatus.SUCCESS,
            ),
            payload=WebSearchPayload(
                kind='web_search',
                results=[],
            ),
        )

        fetch_result = ToolExecutionResult(
            tool_name='web_fetch',
            status=ToolExecutionStatus.SUCCESS,
            tool_call=ToolCallRecord(
                name='web_fetch',
                arguments={'url': 'https://example.com'},
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                status=ToolExecutionStatus.SUCCESS,
            ),
            payload=WebFetchPayload(
                kind='web_fetch',
                url='https://example.com',
                title='Page',
                content='Content',
            ),
        )

        annotations = annotation_service.build_success_annotations(
            executed_tools=[search_result, fetch_result]
        )

        assert len(annotations.tools) == 2
        assert annotations.tools[0].name == 'web_search'
        assert annotations.tools[0].status == ToolAnnotationStatus.COMPLETED
        assert annotations.tools[1].name == 'web_fetch'
        assert annotations.tools[1].status == ToolAnnotationStatus.COMPLETED

    def test_build_success_annotations_enforces_tool_budget(
        self, annotation_service
    ):
        """Enforce max 2 tools budget."""
        tools = []
        for _i, tool_name in enumerate(
            ['web_search', 'web_fetch', 'web_search']
        ):
            if tool_name == 'web_search':
                payload = WebSearchPayload(kind='web_search', results=[])
            else:
                payload = WebFetchPayload(
                    kind='web_fetch',
                    url='https://example.com',
                    title='Page',
                    content='Content',
                )

            result = ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.SUCCESS,
                tool_call=ToolCallRecord(
                    name=tool_name,
                    arguments={},
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    status=ToolExecutionStatus.SUCCESS,
                ),
                payload=payload,
            )
            tools.append(result)

        annotations = annotation_service.build_success_annotations(
            executed_tools=tools
        )

        # Should have max 2 tools, no duplicates
        assert len(annotations.tools) <= 2


class TestFailureAnnotations:
    """Test failure annotation building."""

    def test_build_failure_annotations_llm_timeout(self, annotation_service):
        """Map LLM timeout to failure annotation."""
        error = LLMCompletionError(
            kind=LLMCompletionErrorKind.timeout,
            message='Request timed out',
        )

        annotations = annotation_service.build_failure_annotations(error=error)

        assert annotations.failure is not None
        assert annotations.failure.stage == FailureAnnotationStage.LLM
        assert annotations.failure.retryable is True
        assert 'timed out' in annotations.failure.detail.lower()

    def test_build_failure_annotations_llm_unreachable(
        self, annotation_service
    ):
        """Map LLM unreachable to retryable failure annotation."""
        error = LLMCompletionError(
            kind=LLMCompletionErrorKind.unreachable,
            message='Unable to reach LLM service',
        )

        annotations = annotation_service.build_failure_annotations(error=error)

        assert annotations.failure.stage == FailureAnnotationStage.LLM
        assert annotations.failure.retryable is True

    def test_build_failure_annotations_llm_backend_error(
        self, annotation_service
    ):
        """Map LLM backend error to retryable failure annotation."""
        error = LLMCompletionError(
            kind=LLMCompletionErrorKind.backend_error,
            message='Backend error',
        )

        annotations = annotation_service.build_failure_annotations(error=error)

        assert annotations.failure.stage == FailureAnnotationStage.LLM
        assert annotations.failure.retryable is True

    def test_build_failure_annotations_invalid_response_not_retryable(
        self, annotation_service
    ):
        """Map invalid response to non-retryable failure annotation."""
        error = LLMCompletionError(
            kind=LLMCompletionErrorKind.invalid_response,
            message='Invalid response from LLM',
        )

        annotations = annotation_service.build_failure_annotations(error=error)

        assert annotations.failure.stage == FailureAnnotationStage.LLM
        assert annotations.failure.retryable is False

    def test_build_failure_annotations_no_error_is_unknown(
        self, annotation_service
    ):
        """Unknown stage when no error provided."""
        annotations = annotation_service.build_failure_annotations(error=None)

        assert annotations.failure.stage == FailureAnnotationStage.UNKNOWN
        assert annotations.failure.retryable is False

    def test_build_failure_annotations_clears_sources_and_tools(
        self, annotation_service
    ):
        """Failure annotations should not include sources or tools."""
        error = LLMCompletionError(
            kind=LLMCompletionErrorKind.timeout,
            message='Timeout',
        )

        annotations = annotation_service.build_failure_annotations(error=error)

        assert len(annotations.sources) == 0
        assert len(annotations.tools) == 0
        assert len(annotations.memory_hits) == 0
        assert len(annotations.memory_saved) == 0
        assert annotations.failure is not None


class TestTextTruncation:
    """Test text truncation utility."""

    def test_truncate_text_short_text_unchanged(self, annotation_service):
        """Short text should not be truncated."""
        short_text = 'This is short.'
        truncated = annotation_service._truncate_text(short_text, 100)
        assert truncated == short_text

    def test_truncate_text_long_text_with_ellipsis(self, annotation_service):
        """Long text should be truncated with ellipsis."""
        long_text = 'A' * 300
        truncated = annotation_service._truncate_text(long_text, 100)
        assert len(truncated) <= 103  # 100 + "..."
        assert truncated.endswith('...')

    def test_truncate_text_preserves_word_boundaries(self, annotation_service):
        """Truncation should try to preserve word boundaries."""
        text = 'The quick brown fox jumps over the lazy dogs and cats and birds'
        truncated = annotation_service._truncate_text(text, 40)
        # Should end at reasonable word boundary, not mid-word
        assert len(truncated) <= 42  # 40 + "..."
        assert '...' in truncated
