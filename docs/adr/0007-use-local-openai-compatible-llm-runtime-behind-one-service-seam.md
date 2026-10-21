---
status: accepted
date: "2026-03-10"
supersedes: []
superseded_by:
---

# 0007. Use a local OpenAI-compatible LLM runtime behind one service seam

## Context

Recorded retrospectively. The chat endpoint and its OpenAI-compatible client came in #24
(2026-03-10) and #29 (2026-03-10), which moved the LLM calls into a service layer. The single
completion seam came in #70 (2026-04-13). The local runtime changed from `llama-cpp-python` to
Ollama in PR #74 (2026-04-15).

The backend talks to a model server over HTTP at `LLM_BASE_URL`, using `/v1/chat/completions`
(`services/llm_service.py`). `LLMService.complete_messages()` is the one typed path that builds the
request, calls the server, validates the response and classifies failures as timeout, unreachable,
backend error or invalid response. The chat router and the conversation service both use it, and
streaming goes through the same service. The model name is `LLM_MODEL`.

`docker-compose.yml` runs an `ollama` service, and `apps/llm-server/README.md` describes running a
server by hand. The default model is `qwen2.5:7b`. The #24 description says the endpoint targets
"llama.cpp, OpenAI, or compatible API".

## Considered options

### Local model runtime, reached through an OpenAI-compatible API

- Good: family data stays on the household's own hardware, and any server with the same API can be
  swapped in.
- Bad: needs local hardware and a downloaded model (the README asks for 8 GB or more of RAM).

### Hosted OpenAI-compatible provider

- Good: the API shape is the same, so a hosted backend can be added later. #156 plans OpenRouter.
- Bad: family data would be sent to a third party, so it is not the default.

### llama.cpp (`llama-cpp-python`) as the local runtime

This was the first local runtime, replaced in #74.

- Good: it stays available as a manual alternative in `apps/llm-server/README.md`.
- Bad: #74 records that Ollama's `/v1/chat/completions` returned structured `tool_calls` for the
  current-time tool flow, and the README gives Ollama's clean local tool-calling response shape as
  the reason it is the default (see ADR 0008).

## Decision

We will run a local model behind an OpenAI-compatible `/v1/chat/completions` API, with Ollama as the
default runtime in `docker-compose.yml`.

We will send every model call through `LLMService`, so the rest of the backend does not depend on a
particular runtime or provider.

## Consequences

- Good: privacy, because family data stays local by default, and swappability, because a hosted
  backend can be added behind the same seam (#156).
- Good: error handling and response parsing live in one place.
- Bad: response quality and speed depend on the local hardware and the model pulled with Ollama.
- Bad: the OpenAI-compatible shape is the lowest common denominator. Provider-specific behaviour,
  such as reasoning fields, has to be handled in the parser (ADR 0016).
