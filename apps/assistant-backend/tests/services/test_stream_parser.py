"""Tests for StreamParser module.

Covers parsing of OpenAI-compatible streaming chunks, including:
- Native reasoning fields
- Tag-based reasoning (<think>...</think>) across boundaries
- Content-only and reasoning-only chunks
- Tool-call deltas and terminal metadata
- Edge cases and error handling
"""

import pytest

from assistant.models.llm import (
    ChatCompletionStreamResponse,
    ChatCompletionStreamResponseChoice,
    ChatCompletionStreamResponseDelta,
)
from assistant.services.stream_parser import StreamParser


@pytest.fixture
def parser():
    """Fixture providing a fresh StreamParser instance."""
    return StreamParser()


class TestStreamParserBasic:
    """Basic streaming chunk parsing tests."""

    def test_parse_content_only_chunk(self, parser):
        """It extracts user-visible content from a standard token chunk."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {'content': 'Hello world'},
                    'finish_reason': None,
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        assert output.token == 'Hello world'
        assert output.thought is None
        assert output.finish_reason is None

    def test_parse_pydantic_model(self, parser):
        """It accepts validated Pydantic ChatCompletionStreamResponse."""
        chunk = ChatCompletionStreamResponse(
            id='chatcmpl-456',
            object='chat.completion.chunk',
            created=1234567890,
            model='test-model',
            choices=[
                ChatCompletionStreamResponseChoice(
                    index=0,
                    delta=ChatCompletionStreamResponseDelta(
                        content='Test content'
                    ),
                    finish_reason=None,
                )
            ],
        )

        output = parser.parse_chunk(chunk)
        assert output.token == 'Test content'
        assert output.model == 'test-model'

    def test_parse_empty_delta(self, parser):
        """It handles empty deltas gracefully."""
        chunk_dict = {
            'id': 'chatcmpl-789',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {},
                    'finish_reason': None,
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        assert output.token is None
        assert output.thought is None


class TestStreamParserNativeReasoning:
    """Tests for native reasoning_content field."""

    def test_parse_native_reasoning_chunk(self, parser):
        """It extracts native reasoning_content field directly."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'deepseek-r1',
            'choices': [
                {
                    'index': 0,
                    'delta': {
                        'reasoning_content': 'Let me think about this...'
                    },
                    'finish_reason': None,
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        assert output.thought == 'Let me think about this...'
        assert output.token is None

    def test_parse_native_reasoning_with_content(self, parser):
        """It preserves both native reasoning and content in same chunk."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'deepseek-r1',
            'choices': [
                {
                    'index': 0,
                    'delta': {
                        'reasoning_content': 'Reasoning here',
                        'content': 'Final answer',
                    },
                    'finish_reason': None,
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        # Native reasoning takes precedence
        assert output.thought == 'Reasoning here'


class TestStreamParserTagBased:
    """Tests for tag-based reasoning parsing (<think>...</think>)."""

    def test_parse_complete_think_tag_in_chunk(self, parser):
        """It extracts reasoning within <think> tags in a single chunk."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {'content': '<think>Hmm, this is complex</think>'},
                    'finish_reason': None,
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        assert output.thought == 'Hmm, this is complex'
        assert output.token is None

    def test_parse_think_tag_with_surrounding_content(self, parser):
        """It separates content before and after think tag."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {
                        'content': 'Start of response <think>reasoning</think> end of response'
                    },
                    'finish_reason': None,
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        assert output.thought == 'reasoning'
        # Token contains both before and after
        assert 'Start of response' in output.token
        assert 'end of response' in output.token

    def test_parse_think_tag_split_across_chunks(self, parser):
        """It handles <think> tag split across multiple chunks."""
        # Chunk 1: Opening tag with partial content
        chunk1 = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {'content': 'Start <think>partial reason'},
                    'finish_reason': None,
                }
            ],
        }

        output1 = parser.parse_chunk(chunk1)
        assert output1.token == 'Start '
        # Thought buffer accumulates but not yet emitted
        assert output1.thought is None

        # Chunk 2: Continuation of reasoning
        chunk2 = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {'content': 'ing continued'},
                    'finish_reason': None,
                }
            ],
        }

        output2 = parser.parse_chunk(chunk2)
        assert output2.token is None
        assert output2.thought is None  # Still accumulating

        # Chunk 3: Closing tag
        chunk3 = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {'content': '</think>End'},
                    'finish_reason': None,
                }
            ],
        }

        output3 = parser.parse_chunk(chunk3)
        assert output3.thought == 'partial reasoning continued'
        assert output3.token == 'End'

    def test_parse_multiple_think_tags_in_chunks(self, parser):
        """It handles multiple <think> blocks across chunks."""
        # First thought block
        chunk1_data = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {
                        'content': '<think>first thought</think>visible1 '
                    },
                    'finish_reason': None,
                }
            ],
        }

        output1 = parser.parse_chunk(chunk1_data)
        assert output1.thought == 'first thought'
        assert 'visible1' in output1.token

        # Reset and test second thought block
        parser.reset()
        chunk2_data = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {
                        'content': '<think>second thought</think>visible2'
                    },
                    'finish_reason': None,
                }
            ],
        }

        output2 = parser.parse_chunk(chunk2_data)
        assert output2.thought == 'second thought'
        assert output2.token == 'visible2'


class TestStreamParserToolCalls:
    """Tests for tool-call delta handling."""

    def test_parse_tool_call_delta(self, parser):
        """It preserves tool_calls metadata in stream chunks."""
        chunk_dict = {
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
                                'id': 'call_abc123',
                                'type': 'function',
                                'function': {
                                    'name': 'get_weather',
                                    'arguments': '{"location": "NYC"}',
                                },
                            }
                        ]
                    },
                    'finish_reason': None,
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        assert output.tool_calls is not None
        assert len(output.tool_calls) == 1
        assert output.tool_calls[0].function.name == 'get_weather'


class TestStreamParserTerminal:
    """Tests for terminal metadata (finish_reason, usage)."""

    def test_parse_finish_reason(self, parser):
        """It captures finish_reason in final chunk."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {'content': 'Final token'},
                    'finish_reason': 'stop',
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        assert output.token == 'Final token'
        assert output.finish_reason == 'stop'

    def test_parse_usage_in_final_chunk(self, parser):
        """It captures token usage in final chunk."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {},
                    'finish_reason': 'stop',
                }
            ],
            'usage': {
                'prompt_tokens': 10,
                'completion_tokens': 15,
                'total_tokens': 25,
            },
        }

        output = parser.parse_chunk(chunk_dict)
        assert output.usage is not None
        assert output.usage.prompt_tokens == 10
        assert output.usage.completion_tokens == 15
        assert output.usage.total_tokens == 25
        assert output.finish_reason == 'stop'

    def test_parse_empty_final_chunk(self, parser):
        """It handles empty final chunk with just finish_reason."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {},
                    'finish_reason': 'stop',
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        assert output.token is None
        assert output.thought is None
        assert output.finish_reason == 'stop'


class TestStreamParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_invalid_chunk_missing_choices(self, parser):
        """It rejects chunks with missing choices array."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [],
        }

        output = parser.parse_chunk(chunk_dict)
        # Empty choices returns minimal output
        assert output.model == 'test-model'
        assert output.token is None
        assert output.thought is None

    def test_invalid_chunk_shape(self, parser):
        """It raises ValueError for invalid chunk structure."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            # Missing required fields
        }

        with pytest.raises(ValueError, match='Invalid stream chunk structure'):
            parser.parse_chunk(chunk_dict)

    def test_parse_whitespace_only_tokens(self, parser):
        """It preserves whitespace tokens (important for formatting)."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {'content': '   \n\t  '},
                    'finish_reason': None,
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        assert output.token == '   \n\t  '

    def test_parser_state_reset(self, parser):
        """It properly resets internal state between conversations."""
        # Partial first conversation
        chunk1 = {
            'id': 'chatcmpl-1',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {'content': '<think>unfinished'},
                    'finish_reason': None,
                }
            ],
        }
        parser.parse_chunk(chunk1)
        assert parser.state.in_thought is True

        # Reset state
        parser.reset()
        assert parser.state.in_thought is False
        assert parser.state.thought_buffer == ''

        # New conversation should not be affected
        chunk2 = {
            'id': 'chatcmpl-2',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {'content': 'clean response'},
                    'finish_reason': None,
                }
            ],
        }
        output = parser.parse_chunk(chunk2)
        assert output.token == 'clean response'

    def test_multiline_thinking_blocks(self, parser):
        """It handles multiline thinking content with newlines."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {
                        'content': '<think>Line 1\nLine 2\nLine 3</think>Final answer'
                    },
                    'finish_reason': None,
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        assert output.thought == 'Line 1\nLine 2\nLine 3'
        assert output.token == 'Final answer'

    def test_nested_angle_brackets_in_content(self, parser):
        """It handles content with angle brackets that aren't tags."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {
                        'content': '<think>computing 5 < 10</think>Result: true'
                    },
                    'finish_reason': None,
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        # The entire <think>...</think> is parsed as thinking
        assert output.thought == 'computing 5 < 10'
        assert output.token == 'Result: true'

    def test_consecutive_think_tags(self, parser):
        """It handles consecutive <think> blocks without intervening content."""
        chunk_dict = {
            'id': 'chatcmpl-123',
            'object': 'chat.completion.chunk',
            'created': 1234567890,
            'model': 'test-model',
            'choices': [
                {
                    'index': 0,
                    'delta': {
                        'content': '<think>thought1</think><think>thought2</think>response'
                    },
                    'finish_reason': None,
                }
            ],
        }

        output = parser.parse_chunk(chunk_dict)
        # First thought block is captured
        assert 'thought1' in output.thought or 'thought2' in output.thought
        assert 'response' in output.token
