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
    ChatCompletionMessageToolCall,
    ChatCompletionMessageToolCallFunction,
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
    thought_returned_len: int = 0
    pending_close_tag: str = field(default_factory=str)
    chunk_boundary_buffer: str = field(default_factory=str)
    reasoning_start_tag: str = '<think>'
    reasoning_end_tag: str = '</think>'
    tool_calls: dict[int, ChatCompletionMessageToolCall] = field(
        default_factory=dict
    )

    def reset(self) -> None:
        """Reset parser state for a new conversation."""
        self.in_thought = False
        self.thought_buffer = ''
        self.thought_returned_len = 0
        self.pending_close_tag = ''
        self.chunk_boundary_buffer = ''
        self.tool_calls.clear()


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

        # Extract native reasoning and content independently so providers
        # that emit both fields in the same delta do not lose user-visible
        # content. Use explicit None checks so empty-string deltas are still
        # treated as present.
        if delta.reasoning_content is not None:
            output.thought = delta.reasoning_content

        if delta.content is not None:
            # Process content for tag-based reasoning parsing
            processed = self._process_content_for_tags(delta.content)
            if processed.get('thought') is not None:
                output.thought = processed.get('thought')
            output.token = processed.get('token')

        # Preserve tool calls: accumulate streaming-tool-call deltas across chunks.
        # First chunk includes id/type/name with empty arguments, subsequent chunks
        # only include index and argument deltas. We accumulate and return the
        # current state of tool calls referenced in this delta.
        if delta.tool_calls:
            referenced_indices = []
            for t in delta.tool_calls:
                try:
                    # Use index to track which tool call this delta belongs to
                    idx = t.index if t.index is not None else 0
                    referenced_indices.append(idx)

                    # If this delta has id/type/name, initialize or update the tool call
                    if t.id is not None and t.type is not None:
                        if t.function and t.function.name:
                            func = ChatCompletionMessageToolCallFunction(
                                name=t.function.name,
                                arguments=t.function.arguments or '',
                            )
                            self.state.tool_calls[idx] = (
                                ChatCompletionMessageToolCall(
                                    id=t.id, type=t.type, function=func
                                )
                            )
                    # If this is just an arguments delta, append to existing tool call
                    elif t.function and t.function.arguments is not None:
                        if idx in self.state.tool_calls:
                            existing = self.state.tool_calls[idx]
                            existing.function.arguments += t.function.arguments
                except Exception:
                    # Skip malformed/partial entries rather than raising.
                    continue

            # Return current accumulated state of tool calls referenced in this delta
            result_calls = [
                self.state.tool_calls[idx]
                for idx in referenced_indices
                if idx in self.state.tool_calls
            ]
            if result_calls:
                output.tool_calls = result_calls

        # Terminal metadata
        if choice.finish_reason is not None:
            output.finish_reason = choice.finish_reason

        if chunk.usage is not None:
            output.usage = chunk.usage

        return output

    def _process_content_for_tags(self, content: str) -> dict[str, str | None]:
        """Process content for <think> tag parsing across boundaries.

        Handles:
        - Opening tag at end of chunk (pending close in next chunk)
        - Closing tag at start of chunk (completing previous thought)
        - Complete tag within single chunk
        - No tags (regular token)
        - Tags split across chunk boundaries (buffers last 20 chars)

        Returns incremental thought deltas, not accumulated buffers.

        Args:
            content: Content delta from this chunk

        Returns:
            Dict with 'thought' and/or 'token' keys (incremental deltas)
        """
        result: dict[str, str | None] = {'thought': None, 'token': None}

        prev_buf = self.state.chunk_boundary_buffer
        combined = prev_buf + content
        offset = len(prev_buf)

        start_tag = self.state.reasoning_start_tag
        end_tag = self.state.reasoning_end_tag

        # If we're currently inside a thought (pending close), stream incremental content
        if self.state.pending_close_tag:
            close_match = re.search(re.escape(end_tag), combined, re.DOTALL)
            if close_match:
                # Closing tag found: stream anything new up to the closing tag
                thought_end = combined[: close_match.start()]
                new_thought = thought_end[self.state.thought_returned_len :]
                if new_thought:
                    result['thought'] = new_thought

                # Remaining content after closing tag should be processed normally
                remaining = combined[close_match.end() :]
                # Reset thought state
                self.state.in_thought = False
                self.state.thought_buffer = ''
                self.state.thought_returned_len = 0
                self.state.pending_close_tag = ''
                self.state.chunk_boundary_buffer = ''

                if remaining:
                    rem = self._process_content_for_tags(remaining)
                    if rem['thought']:
                        result['thought'] = (result['thought'] or '') + rem[
                            'thought'
                        ]
                    if rem['token']:
                        result['token'] = rem['token']
            else:
                # No closing tag yet: stream new content since last returned
                new_thought = combined[self.state.thought_returned_len :]
                if new_thought:
                    result['thought'] = new_thought

                # Mark everything as returned so we don't duplicate
                self.state.thought_buffer = combined
                self.state.thought_returned_len = len(combined)
                # Keep full buffer untruncated while inside thought block
                self.state.chunk_boundary_buffer = combined
            return result

        # Not currently inside a thought: detect opening tag (handle split tags)
        open_match = re.search(re.escape(start_tag), combined)
        close_match = re.search(re.escape(end_tag), combined, re.DOTALL)

        if not open_match:
            # No full opening tag in combined content. Check for a trailing partial
            # of the start tag so we can buffer it instead of leaking to the user.
            max_prefix = 0
            for i in range(1, len(start_tag)):
                if combined.endswith(start_tag[:i]):
                    max_prefix = i
            if max_prefix:
                # Return only the new token portion (excluding buffered prefix)
                token_part = combined[:-max_prefix]
                new_token = token_part[offset:]
                if new_token:
                    result['token'] = new_token
                # Buffer the partial tag prefix for next chunk
                self.state.chunk_boundary_buffer = combined[-max_prefix:]
            else:
                # No partial tag - return content as token and keep small boundary
                result['token'] = content
                self.state.chunk_boundary_buffer = combined[-20:]
            return result

        # Found an opening tag in combined
        if close_match and close_match.start() > open_match.start():
            # Complete tag within this combined input
            before_tag = combined[: open_match.start()]
            inside_tag = combined[open_match.end() : close_match.start()]
            after_tag = combined[close_match.end() :]

            # Only return token text that is new (not from previous buffer)
            token_before_new = before_tag[offset:]
            if token_before_new:
                result['token'] = token_before_new
            if inside_tag:
                result['thought'] = inside_tag

            # Process remaining content recursively
            if after_tag:
                after_res = self._process_content_for_tags(after_tag)
                if after_res['thought']:
                    result['thought'] = (result['thought'] or '') + after_res[
                        'thought'
                    ]
                if after_res['token']:
                    result['token'] = (result['token'] or '') + after_res[
                        'token'
                    ]

            # Clear boundary buffer as we've consumed it
            self.state.chunk_boundary_buffer = ''
            return result

        # Opening tag found but no closing tag: start thought and stream what's available
        before_tag = combined[: open_match.start()]
        after_tag = combined[open_match.end() :]

        token_before_new = before_tag[offset:]
        if token_before_new:
            result['token'] = token_before_new

        # Stream all available inside-tag content immediately
        if after_tag:
            result['thought'] = after_tag

        self.state.in_thought = True
        self.state.thought_buffer = after_tag
        self.state.thought_returned_len = len(after_tag)
        self.state.pending_close_tag = end_tag
        # Keep full buffer untruncated while inside thought block
        self.state.chunk_boundary_buffer = after_tag

        return result

    def reset(self) -> None:
        """Reset parser state. Call this between conversations."""
        self.state.reset()
