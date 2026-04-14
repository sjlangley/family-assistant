"""Deterministic tool used to validate the tool layer end to end."""

from datetime import UTC, datetime

from assistant.models.tool import (
    TimePayload,
    ToolCallRecord,
    ToolExecutionResult,
    ToolExecutionStatus,
)
from assistant.services.tools.base import BaseTool


class CurrentTimeTool(BaseTool):
    """Return the server's current UTC time in a normalized result envelope."""

    name = 'get_current_time'

    def definition(self) -> dict:
        """Expose a minimal no-argument tool definition to the model."""

        return {
            'type': 'function',
            'function': {
                'name': self.name,
                'description': 'Return the current server time in ISO 8601 format.',
                'parameters': {
                    'type': 'object',
                    'properties': {},
                    'required': [],
                    'additionalProperties': False,
                },
            },
        }

    async def execute(self, arguments: dict) -> ToolExecutionResult:
        """Capture the current UTC time and format it for LLM/tool consumers."""

        started_at = datetime.now(UTC)
        now = datetime.now(UTC)

        payload = TimePayload(
            kind=self.name,
            iso_timestamp=now.isoformat(),
            display_text=now.strftime('%Y-%m-%d %H:%M:%S UTC'),
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
            llm_context=f'Current server time: {payload.display_text} ({payload.iso_timestamp})',
            annotation_inputs={
                'tool_name': self.name,
                'label': 'Current time',
            },
            payload=payload,
            error=None,
        )
