"""Service for building persisted trust annotations on assistant responses."""

from assistant.models.annotations import (
    AssistantAnnotations,
    FailureAnnotation,
    FailureAnnotationStage,
    SourceAnnotation,
    ToolAnnotation,
    ToolAnnotationStatus,
)
from assistant.models.llm import LLMCompletionError
from assistant.models.tool import (
    ToolExecutionResult,
    ToolExecutionStatus,
    WebFetchPayload,
)


class AssistantAnnotationService:
    """Builds compact, budget-conscious trust annotations for assistant responses.

    Handles both successful responses (with tool outputs and sources) and
    terminal failures (with failure metadata).
    """

    # Budget limits - enforced at persistence time
    MAX_SOURCES = 3
    MAX_SOURCES_SNIPPET_LENGTH = 240
    MAX_TOOLS = 2
    MAX_MEMORY_HITS = 2
    MAX_MEMORY_SAVED = 1

    def build_success_annotations(
        self,
        *,
        executed_tools: list[ToolExecutionResult],
    ) -> AssistantAnnotations:
        """Build success annotations from tool execution results.

        Only extracts sources from web_fetch payloads (actual fetched content),
        never from raw web_search snippets alone.

        Enforces all budget limits.
        """
        sources = self._extract_sources_from_fetches(executed_tools)
        tools = self._extract_tool_annotations(executed_tools)

        return AssistantAnnotations(
            sources=sources,
            tools=tools,
            memory_hits=[],
            memory_saved=[],
            failure=None,
        )

    def build_failure_annotations(
        self,
        *,
        error: LLMCompletionError | None = None,
    ) -> AssistantAnnotations:
        """Build failure annotations for terminal assistant error rows.

        Maps LLM error kinds to appropriate failure stages.
        """
        stage = self._determine_failure_stage(error)

        failure_annotation = FailureAnnotation(
            stage=stage,
            retryable=self._is_error_retryable(error),
            detail=self._format_error_detail(error),
        )

        return AssistantAnnotations(
            sources=[],
            tools=[],
            memory_hits=[],
            memory_saved=[],
            failure=failure_annotation,
        )

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers for success annotations
    # ─────────────────────────────────────────────────────────────────────

    def _extract_sources_from_fetches(
        self,
        executed_tools: list[ToolExecutionResult],
    ) -> list[SourceAnnotation]:
        """Extract sources only from web_fetch results (not raw search snippets).

        Budget: max 3 sources, snippets capped at 240 chars.
        """
        sources = []

        for tool_result in executed_tools:
            if tool_result.status != ToolExecutionStatus.SUCCESS:
                continue

            if tool_result.tool_name != 'web_fetch':
                continue

            if not isinstance(tool_result.payload, WebFetchPayload):
                continue

            payload: WebFetchPayload = tool_result.payload

            snippet = payload.excerpt or self._truncate_text(
                payload.content, self.MAX_SOURCES_SNIPPET_LENGTH
            )

            source = SourceAnnotation(
                title=payload.title or 'Untitled',
                url=payload.url,
                snippet=snippet,
                rationale='Referenced in the assistant response',
            )
            sources.append(source)

            if len(sources) >= self.MAX_SOURCES:
                break

        return sources

    def _extract_tool_annotations(
        self,
        executed_tools: list[ToolExecutionResult],
    ) -> list[ToolAnnotation]:
        """Extract tool annotations from executed tools.

        Budget: max 2 tools. Only includes tools that actually ran (not just
        those that were attempted but failed at parsing level).
        """
        tools = []
        seen_tool_names = set()

        for tool_result in executed_tools:
            tool_name = tool_result.tool_name

            # Skip duplicates (use first occurrence)
            if tool_name in seen_tool_names:
                continue

            # Only include tools with valid payloads (not failed parses)
            if tool_result.status == ToolExecutionStatus.ERROR:
                continue

            status_map = {
                ToolExecutionStatus.SUCCESS: ToolAnnotationStatus.COMPLETED,
                ToolExecutionStatus.ERROR: ToolAnnotationStatus.FAILED,
            }

            tool_annotation = ToolAnnotation(
                name=tool_name,
                status=status_map[tool_result.status],
            )
            tools.append(tool_annotation)
            seen_tool_names.add(tool_name)

            if len(tools) >= self.MAX_TOOLS:
                break

        return tools

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers for failure annotations
    # ─────────────────────────────────────────────────────────────────────

    def _determine_failure_stage(
        self,
        error: LLMCompletionError | None,
    ) -> FailureAnnotationStage:
        """Map LLM error kind to failure stage."""
        if error is None:
            return FailureAnnotationStage.UNKNOWN

        # All known error kinds from LLM service are LLM-stage errors
        # (timeout, unreachable, backend_error, invalid_response)
        # Tool-stage errors would be caught and mapped differently
        return FailureAnnotationStage.LLM

    def _is_error_retryable(
        self,
        error: LLMCompletionError | None,
    ) -> bool:
        """Determine if a failure is transient and retryable."""
        if error is None:
            return False

        retryable_kinds = {
            'timeout',
            'unreachable',
            'backend_error',
        }

        return error.kind in retryable_kinds

    def _format_error_detail(
        self,
        error: LLMCompletionError | None,
    ) -> str | None:
        """Format error message for user display."""
        if error is None:
            return None

        # Return the error message if available
        if hasattr(error, 'message') and error.message:
            return error.message

        kind_labels = {
            'timeout': 'Request timed out',
            'unreachable': 'Unable to reach LLM service',
            'backend_error': 'LLM service error',
            'invalid_response': 'Invalid LLM response',
        }

        return kind_labels.get(error.kind, 'Unknown error')

    # ─────────────────────────────────────────────────────────────────────
    # Utility helpers
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _truncate_text(text: str, max_length: int) -> str:
        """Truncate text to max length, preserving word boundaries."""
        if len(text) <= max_length:
            return text

        truncated = text[:max_length].rstrip()
        if truncated and truncated[-1] not in '.!?':
            # Try to end at word boundary
            last_space = truncated.rfind(' ')
            if last_space > max_length * 0.7:
                truncated = truncated[:last_space]

        return truncated + '...'
