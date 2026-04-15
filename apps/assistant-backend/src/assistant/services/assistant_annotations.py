"""Service for building persisted trust annotations on assistant responses."""

from assistant.models.annotations import (
    AssistantAnnotations,
    FailureAnnotation,
    FailureAnnotationStage,
    MemoryHitAnnotation,
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
        fact_ids: list | None = None,
    ) -> AssistantAnnotations:
        """Build success annotations from tool execution results.

        Only extracts sources from web_fetch payloads (actual fetched content),
        never from raw web_search snippets alone.

        Includes memory facts that were injected into the prompt context.

        Enforces all budget limits.
        """
        sources = self._extract_sources_from_fetches(executed_tools)
        tools = self._extract_tool_annotations(executed_tools)
        memory_hits = self._extract_memory_hits(fact_ids or [])

        return AssistantAnnotations(
            sources=sources,
            tools=tools,
            memory_hits=memory_hits,
            memory_saved=[],
            failure=None,
        )

    def build_failure_annotations(
        self,
        *,
        error: LLMCompletionError | None = None,
        executed_tools: list[ToolExecutionResult] | None = None,
        attempted_tool_execution: bool = False,
    ) -> AssistantAnnotations:
        """Build failure annotations for terminal assistant error rows.

        Maps error origins to appropriate failure stages and preserves
        tool/source metadata from work accomplished before the failure.
        """
        executed = executed_tools or []
        stage = self._determine_failure_stage(
            error,
            executed_tools=executed,
            attempted_tool_execution=attempted_tool_execution,
        )

        failure_annotation = FailureAnnotation(
            stage=stage,
            retryable=self._is_error_retryable(error),
            detail=self._format_error_detail(error),
        )

        # Preserve tool metadata and sources even on failure
        sources = self._extract_sources_from_fetches(executed)
        tools = self._extract_tool_annotations(executed)

        return AssistantAnnotations(
            sources=sources,
            tools=tools,
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

        Budget: max 2 tools. Includes both successful and failed tools
        for transparency and debugging.
        """
        tools = []
        seen_tool_names = set()
        status_map = {
            ToolExecutionStatus.SUCCESS: ToolAnnotationStatus.COMPLETED,
            ToolExecutionStatus.ERROR: ToolAnnotationStatus.FAILED,
        }

        for tool_result in executed_tools:
            tool_name = tool_result.tool_name

            # Skip duplicates (use first occurrence)
            if tool_name in seen_tool_names:
                continue

            tool_annotation = ToolAnnotation(
                name=tool_name,
                status=status_map[tool_result.status],
            )
            tools.append(tool_annotation)
            seen_tool_names.add(tool_name)

            if len(tools) >= self.MAX_TOOLS:
                break

        return tools

    def _extract_memory_hits(
        self,
        fact_ids: list,
    ) -> list[MemoryHitAnnotation]:
        """Extract memory facts injected into the prompt.

        Budget: max 2 facts. Only includes facts that were actually
        used in context assembly.
        """
        # Return count-limited list of fact IDs wrapped in dicts for Pydantic validation
        return [
            {'label': 'Memory Fact', 'summary': f'Fact ID: {fid}'}
            for fid in fact_ids[: self.MAX_MEMORY_HITS]
        ]

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers for failure annotations
    # ─────────────────────────────────────────────────────────────────────

    def _determine_failure_stage(
        self,
        error: LLMCompletionError | None,
        executed_tools: list[ToolExecutionResult] | None = None,
        attempted_tool_execution: bool = False,
    ) -> FailureAnnotationStage:
        """Map error origin to appropriate failure stage.

        Checks both whether tools were successfully executed and whether
        the tool loop was attempted (which catches early parsing/execution failures).
        """
        if error is None:
            return FailureAnnotationStage.UNKNOWN

        # If tools ran before the failure, it was a tool-phase failure
        if executed_tools:
            return FailureAnnotationStage.TOOL

        # If tool execution was attempted but failed early (parsing or first execution),
        # it's still a tool-phase failure
        if attempted_tool_execution:
            return FailureAnnotationStage.TOOL

        # No tools executed = LLM phase error
        # (timeout, unreachable, backend_error from LLM service)
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
