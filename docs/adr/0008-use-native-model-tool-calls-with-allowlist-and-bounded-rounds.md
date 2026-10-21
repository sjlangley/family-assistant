---
status: accepted
date: "2026-04-14"
supersedes: []
superseded_by:
---

# 0008. Use native model tool calls with an allowlist and bounded rounds

## Context

Recorded retrospectively. The decision was made in #73 (2026-04-14), which added the first tool
layer and a current-time tool. The completion seam from #70 (ADR 0020) already carried `tool_calls`.

The backend sends tool definitions to the model in the OpenAI function format with
`tool_choice: auto`, and the model asks for tools in its reply. `ToolFactory`
(`services/tools/factory.py`) is the allowlist: `get_tool_service()` in `services/__init__.py`
registers `CurrentTimeTool`, `WebSearchTool` and `WebFetchTool`, and a name outside that set raises
`UnsupportedToolError`. `ToolService` executes one named tool with parsed arguments.

The loop in `services/conversation_service.py` runs for at most `MAXIMUM_TOOL_ROUNDS` (3, in
`constants.py`) model calls, appending each result as a `tool` message. It is used by both the plain
and the streaming reply paths.

## Considered options

### Hand-built tool loop using the model's native tool calls

The author's note contrasts this with using an agent framework. No other alternatives were recorded.

- Good: the author built it by hand in order to learn how tool calling works.
- Bad: the loop, argument parsing and error handling are code to maintain here.

## Decision

We will use the model's native tool calls through the OpenAI-compatible API, with a loop written in
this repository rather than an agent framework.

We will expose only tools registered in `ToolFactory`.

We will stop a reply that is still asking for tools after `MAXIMUM_TOOL_ROUNDS` model calls, and
record it as a failure.

## Consequences

- Good: every step of the tool flow is visible in this repository, which was the aim.
- Good: a model cannot call anything that is not registered, and a reply cannot loop forever.
- Bad: an unknown or disabled tool, unparseable arguments or a tool exception ends the whole reply
  with a failure. The model is not given the error to recover from.
- Bad: a reply that needs more than the bounded rounds fails rather than degrading, and the results
  of a final round of tool calls are never shown to the model.
- Bad: a model that does not support native tool calls cannot use tools.
- Each new tool has to be written, registered in `get_tool_service()` and given trust annotations
  (ADR 0013).
