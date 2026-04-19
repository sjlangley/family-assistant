import json
from typing import Any


class SSEEncoder:
    """Utility for encoding application events into Server-Sent Events (SSE) format.

    Follows the SSE spec: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
    Each event is formatted as:
    event: <event_type>\n
    data: <json_data>\n\n
    """

    @staticmethod
    def encode(event_type: str, data: Any) -> str:
        """Encode an event into SSE format.

        Args:
            event_type: The type of the event (e.g., 'thought', 'token', 'done')
            data: The data to include in the event (will be JSON encoded)

        Returns:
            A formatted SSE string.
        """
        json_data = json.dumps(data)
        return f"event: {event_type}\ndata: {json_data}\n\n"
