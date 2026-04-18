"""Stream parser for OpenAI-compatible LLM streaming responses.

This module provides parsing and state management for streaming chat completion
chunks. It distinguishes between reasoning content (thought) and user-visible
tokens, supports both native reasoning fields and tag-based parsing such as
<think>...</think> blocks, and handles chunk-boundary edge cases.

Design principles:
- Transport-agnostic: no HTTPX or raw socket handling
- Type-safe: uses Pydantic models for input and output
- Stateful: tracks partial tags across chunk boundaries
- Tolerant: handles empty/partial chunks gracefully
"""

from dataclasses import dataclass, field
import re

from assistant.models.llm import (
    ChatCompletionStreamResponse,
    StreamParserOutput,
)


@dataclass
class StreamParserState:
    """Internal state for tracking partial tags and accumulated content.

    This state allows the parser to handle tags split across chunk boundaries.
    It should be reused across multiple stream chunks in sequence.
    """

    in_thought: bool = False
    thought_buffer: str = field(default_factory=str)
    pending_close_tag: str = field(default_factory=str)
    reasoning_start_tag: str = '<think>'
    reasoning_end_tag: str = '</think>'

    def reset(self) -> None:
        """Reset parser state for a new conversation."""
        self.in_thought = False
        self.thought_buffer = ''
        self.pending_close_tag = ''


class StreamParser:
    """Parser for OpenAI-compatible streaming chat completion responses.

    Converts individual stream chunks into typed parser outputs that distinguish
    reasoning content from user-visible tokens. Handles:
    - Native reasoning_content field (e.g., DeepSeek-R1)
    - Tag-based reasoning (<think>...</think>) split across chunks
    - Partial/empty chunks
    - Terminal chunks with finish_reason and usage
    - Tool-call deltas
    """

    def __init__(self):
        """Initialize the stream parser."""
        self.state = StreamParserState()

    def parse_chunk(
        self, chunk_data: dict | ChatCompletionStreamResponse
    ) -> StreamParserOutput:
        """Parse a single stream chunk into typed output.

        Handles both raw dict (from NDJSON) and validated Pydantic models.
        Manages tag-based reasoning across chunk boundaries.

        Args:
            chunk_data: Raw dict or ChatCompletionStreamResponse from LLM stream

        Returns:
            StreamParserOutput with distinguished thought/token/metadata

        Raises:
            ValueError: If chunk structure is invalid
        """
        # Validate and normalize chunk to Pydantic model
        if isinstance(chunk_data, dict):
            try:
                chunk = ChatCompletionStreamResponse.model_validate(chunk_data)
            except Exception as exc:
                raise ValueError(
                    f'Invalid stream chunk structure: {exc}'
                ) from exc
        else:
            chunk = chunk_data

        # Extract first choice (streaming typically sends one choice)
        if not chunk.choices:
            return StreamParserOutput(model=chunk.model)

        choice = chunk.choices[0]
        delta = choice.delta

        # Initialize output
        output = StreamParserOutput(model=chunk.model)

        # Extract native reasoning if present
        if delta.reasoning_content:
            output.thought = delta.reasoning_content
        elif delta.content:
            # Process content for tag-based reasoning parsing
            processed = self._process_content_for_tags(delta.content)
            output.thought = processed.get('thought')
            output.token = processed.get('token')
        else:
            # Empty delta (can happen mid-stream)
            pass

        # Preserve tool calls
        if delta.tool_calls:
            output.tool_calls = delta.tool_calls

        # Terminal metadata
        if choice.finish_reason:
            output.finish_reason = choice.finish_reason

        if chunk.usage:
            output.usage = chunk.usage

        return output

    def _process_content_for_tags(self, content: str) -> dict[str, str | None]:
        """Process content for <think> tag parsing across boundaries.

        Handles:
        - Opening tag at end of chunk (pending close in next chunk)
        - Closing tag at start of chunk (completing previous thought)
        - Complete tag within single chunk
        - No tags (regular token)

        Args:
            content: Content delta from this chunk

        Returns:
            Dict with 'thought' and/or 'token' keys
        """
        result: dict[str, str | None] = {'thought': None, 'token': None}

        # If we have pending close tag, check if this chunk contains it
        if self.state.pending_close_tag:
            close_match = re.search(
                re.escape(self.state.reasoning_end_tag), content, re.DOTALL
            )
            if close_match:
                # Found closing tag - extract accumulated thought
                thought_tail = content[: close_match.start()]
                self.state.thought_buffer += thought_tail
                result['thought'] = self.state.thought_buffer

                # Extract remaining content after closing tag
                remaining = content[close_match.end() :]
                self.state.in_thought = False
                self.state.thought_buffer = ''
                self.state.pending_close_tag = ''

                # Process remaining content recursively
                if remaining:
                    remaining_result = self._process_content_for_tags(remaining)
                    if remaining_result['thought']:
                        result['thought'] = (
                            result['thought'] or ''
                        ) + remaining_result['thought']
                    if remaining_result['token']:
                        result['token'] = remaining_result['token']
            else:
                # No closing tag found - accumulate as thought
                self.state.thought_buffer += content
            return result

        # Look for opening and closing tags
        open_match = re.search(
            re.escape(self.state.reasoning_start_tag), content
        )
        close_match = re.search(
            re.escape(self.state.reasoning_end_tag), content, re.DOTALL
        )

        if not open_match:
            # No opening tag - regular token
            result['token'] = content
            return result

        # Found opening tag
        if close_match and close_match.start() > open_match.start():
            # Complete tag within this chunk: <think>...content...</think>
            before_tag = content[: open_match.start()]
            inside_tag = content[open_match.end() : close_match.start()]
            after_tag = content[close_match.end() :]

            if before_tag:
                result['token'] = before_tag
            if inside_tag:
                result['thought'] = inside_tag

            # Recursively process content after tag
            if after_tag:
                after_result = self._process_content_for_tags(after_tag)
                if after_result['thought']:
                    result['thought'] = (
                        result['thought'] or ''
                    ) + after_result['thought']
                if after_result['token']:
                    result['token'] = (result['token'] or '') + after_result[
                        'token'
                    ]
        else:
            # Opening tag found but no closing tag - start accumulating
            before_tag = content[: open_match.start()]
            after_tag = content[open_match.end() :]

            if before_tag:
                result['token'] = before_tag

            self.state.in_thought = True
            self.state.thought_buffer = after_tag
            self.state.pending_close_tag = self.state.reasoning_end_tag

        return result

    def reset(self) -> None:
        """Reset parser state. Call this between conversations."""
        self.state.reset()
