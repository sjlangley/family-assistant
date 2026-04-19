import pytest

from assistant.services.stream_parser import StreamParser


@pytest.fixture
def parser():
    """Fixture providing a fresh StreamParser instance."""
    return StreamParser()


def test_parse_tool_call_split_across_chunks(parser):
    """It handles tool call deltas split across multiple chunks."""
    # Chunk 1: Initial call with ID and name
    chunk1 = {
        'id': 'chatcmpl-123',
        'object': 'chat.completion.chunk',
        'created': 1234567890,
        'model': 'test-model',
        'choices': [
            {
                'index': 0,
                'delta': {
                    'tool_calls': [
                        {
                            'index': 0,
                            'id': 'call_abc123',
                            'type': 'function',
                            'function': {
                                'name': 'get_weather',
                                'arguments': '',
                            },
                        }
                    ]
                },
                'finish_reason': None,
            }
        ],
    }

    output1 = parser.parse_chunk(chunk1)
    assert output1.tool_calls is not None
    assert len(output1.tool_calls) == 1
    assert output1.tool_calls[0].id == 'call_abc123'
    assert output1.tool_calls[0].function.name == 'get_weather'
    assert output1.tool_calls[0].function.arguments == ''

    # Chunk 2: Arguments delta
    chunk2 = {
        'id': 'chatcmpl-123',
        'object': 'chat.completion.chunk',
        'created': 1234567891,
        'model': 'test-model',
        'choices': [
            {
                'index': 0,
                'delta': {
                    'tool_calls': [
                        {
                            'index': 0,
                            'function': {
                                'arguments': '{"locat',
                            },
                        }
                    ]
                },
                'finish_reason': None,
            }
        ],
    }

    output2 = parser.parse_chunk(chunk2)
    assert output2.tool_calls is not None
    assert output2.tool_calls[0].function.arguments == '{"locat'

    # Chunk 3: Final arguments delta
    chunk3 = {
        'id': 'chatcmpl-123',
        'object': 'chat.completion.chunk',
        'created': 1234567892,
        'model': 'test-model',
        'choices': [
            {
                'index': 0,
                'delta': {
                    'tool_calls': [
                        {
                            'index': 0,
                            'function': {
                                'arguments': 'ion": "NYC"}',
                            },
                        }
                    ]
                },
                'finish_reason': None,
            }
        ],
    }

    output3 = parser.parse_chunk(chunk3)
    assert output3.tool_calls is not None
    assert output3.tool_calls[0].function.arguments == '{"location": "NYC"}'
