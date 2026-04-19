import json
from typing import Any


class SSEEncoder:
    """Utility for encoding application events into Server-Sent Events (SSE) format.

    Follows the SSE spec: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
    Each event is formatted as:
    event: <event_type>\n
    data: <json_data>\n\n
    """

    ALLOWED_EVENT_TYPES = {'thought', 'token', 'tool_call', 'done', 'error'}

    @staticmethod
    def encode(event_type: str, data: Any) -> str:
        """Encode an event into SSE format.

        Args:
            event_type: The type of the event (e.g., 'thought', 'token', 'done')
            data: The data to include in the event (will be JSON encoded)

        Returns:
            A formatted SSE string.

        Raises:
            ValueError: If event_type is invalid or contains newlines.
        """
        if event_type not in SSEEncoder.ALLOWED_EVENT_TYPES:
            raise ValueError(f'Invalid event type: {event_type}')

        if '\n' in event_type or '\r' in event_type:
            raise ValueError('Event type cannot contain newline characters')

        json_data = json.dumps(data, ensure_ascii=False)
        return f'event: {event_type}\ndata: {json_data}\n\n'
