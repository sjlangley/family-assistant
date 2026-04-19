import json
import pytest
from assistant.utils.sse import SSEEncoder


def test_encode_token_event():
    """It encodes a token event correctly."""
    event_type = "token"
    data = "hello"
    expected = 'event: token\ndata: "hello"\n\n'
    assert SSEEncoder.encode(event_type, data) == expected


def test_encode_thought_event():
    """It encodes a thought event correctly."""
    event_type = "thought"
    data = "thinking..."
    expected = 'event: thought\ndata: "thinking..."\n\n'
    assert SSEEncoder.encode(event_type, data) == expected


def test_encode_done_event():
    """It encodes a done event with a complex dict correctly."""
    event_type = "done"
    data = {
        "message_id": "123",
        "content": "Final response",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20}
    }
    encoded = SSEEncoder.encode(event_type, data)
    
    # Check structure
    assert encoded.startswith("event: done\ndata: ")
    assert encoded.endswith("\n\n")
    
    # Verify data payload is valid JSON
    payload_str = encoded.replace("event: done\ndata: ", "").strip()
    payload = json.loads(payload_str)
    assert payload == data


def test_encode_error_event():
    """It encodes an error event correctly."""
    event_type = "error"
    data = {"kind": "timeout", "message": "LLM timed out"}
    encoded = SSEEncoder.encode(event_type, data)
    
    assert encoded.startswith("event: error\ndata: ")
    assert json.loads(encoded.replace("event: error\ndata: ", "").strip()) == data
