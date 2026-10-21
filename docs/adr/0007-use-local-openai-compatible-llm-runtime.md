---
status: accepted
date: "2026-03-10"
supersedes: []
superseded_by:
---

# 0007. Use a local OpenAI-compatible LLM runtime

## Context

Recorded retrospectively. The chat endpoint and its OpenAI-compatible client came in #24
(2026-03-10) and #29 (2026-03-10), which moved the LLM calls into a service layer. The #24
description says the endpoint targets "llama.cpp, OpenAI, or compatible API". The first local
runtime was `llama-cpp-python`.

The backend talks to a model server over HTTP at `LLM_BASE_URL`, using `/v1/chat/completions`
(`services/llm_service.py`). The model name is `LLM_MODEL`. `apps/llm-server/README.md` describes
running a server by hand.

The later change of default runtime to Ollama and the single completion seam are separate decisions,
recorded in [ADR 0020](0020-use-ollama-as-default-runtime-behind-one-llm-service-seam.md).

## Considered options

### Local model runtime, reached through an OpenAI-compatible API

- Good: family data stays on the household's own hardware, and any server with the same API can be
  swapped in.
- Bad: needs local hardware and a downloaded model (the README asks for 8 GB or more of RAM).

### Hosted OpenAI-compatible provider

- Good: the same API shape works for it, as the #24 description's mention of OpenAI shows.
- Bad: family data would be sent to a third party, so it is not the default.

## Decision

We will run a local model behind an OpenAI-compatible `/v1/chat/completions` API.

We will keep the API shape provider-neutral, so a hosted backend can be added later (#156 plans
OpenRouter).

## Consequences

- Good: privacy, because family data stays local by default, and swappability, because a hosted
  backend can be added with the same API (#156).
- Bad: response quality and speed depend on the local hardware and the model that is loaded.
- Bad: the OpenAI-compatible shape is the lowest common denominator. Provider-specific behaviour,
  such as reasoning fields, has to be handled in the parser (ADR 0016).
