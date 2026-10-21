---
status: accepted
date: "2026-04-15"
supersedes: []
superseded_by:
---

# 0020. Use Ollama as the default runtime behind one LLM service seam

## Context

Recorded retrospectively. This follows [ADR 0007](0007-use-local-openai-compatible-llm-runtime.md),
which chose a local OpenAI-compatible runtime. Two later changes belong together here. #70
(2026-04-13) extracted one completion path, `LLMService.complete_messages()`. #74 (2026-04-15)
switched the local runtime from `llama-cpp-python` to Ollama. The date above is #74's, the later of
the two, because by then both were in force. The seam has no alternatives on record, and the options
below are those of the runtime switch.

`complete_messages()` builds the request, calls the server, validates the response and classifies
failures as timeout, unreachable, backend error or invalid response. The chat router and the
conversation service both use it. Streaming replies, added later (ADR 0014), go through a separate
`LLMService.stream_messages()` with its own request and error handling. The #70 description gives
its purpose as removing duplicate error handling and response parsing, and carrying `tool_calls` and
`finish_reason` for future tool calling.

`docker-compose.yml` runs an `ollama` service, and the default model is `qwen2.5:7b`. #74 records
that Ollama's `/v1/chat/completions` was manually verified to return structured `tool_calls` for the
current-time tool flow (ADR 0008). `apps/llm-server/README.md` says Ollama provides a clean local
tool-calling response shape for the backend tool loop. No other reason for the switch was recorded.

## Considered options

### `llama-cpp-python` as the local runtime

This was the first local runtime, replaced in #74.

- Good: it stays available as a manual alternative in `apps/llm-server/README.md`.
- Bad: #74 records no tool-call result for it. The README gives Ollama's response shape as the
  reason for the switch.

### Ollama as the local runtime

- Good: its `/v1/chat/completions` returned structured `tool_calls` for the current-time tool flow
  (#74).
- Bad: no cost of the switch was recorded in #74.

## Decision

We will use Ollama as the default runtime in `docker-compose.yml`, with `qwen2.5:7b` as the default
model.

We will send every model call through `LLMService`, so the rest of the backend does not depend on a
particular runtime or provider.

## Consequences

- Good: error handling and response parsing live in `LLMService`, not in its callers, and the tool
  loop gets structured `tool_calls` from the default runtime.
- Bad: `complete_messages()` and `stream_messages()` each carry their own error handling, so the two
  paths can drift.
- Good: a hosted backend can be added behind the same seam (#156).
- Bad: the default model is pulled through Ollama, and response quality and speed depend on the
  local hardware and that model.
- Bad: other runtimes work only if they match the `/v1/chat/completions` shape the service parses.
