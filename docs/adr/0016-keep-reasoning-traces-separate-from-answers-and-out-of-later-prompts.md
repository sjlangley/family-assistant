---
status: accepted
date: "2026-04-19"
supersedes: []
superseded_by:
---

# 0016. Keep reasoning traces separate from answers and out of later prompts

## Context

Recorded retrospectively. The parser and the separate `thought` event came in #99 (2026-04-19), part
of the streaming work in ADR 0014. The policy is written in the "Reasoning Display Policy" section
of `docs/MODEL_PRESETS_PRD.md`, and the reasons below come from there.

Some models emit a reasoning trace as well as an answer, either in a native `reasoning_content`
field (for example DeepSeek-R1) or in `<think>...</think>` tags inside the content. `StreamParser`
(`services/stream_parser.py`) handles both, including tags split across chunks, and yields reasoning
and content separately.

The stream sends reasoning as `thought` events and the answer as `token` events (ADR 0014). On the
streaming path, the saved assistant message keeps only the clean answer in `content`. The reasoning
is stored in the `thought` field of `annotations` (ADR 0013). `ContextAssemblyService` builds later
prompts from each message's `content` only (`services/context_assembly.py`), so a trace kept out of
`content` is never sent back to the model. Memory extraction (ADR 0010) reads `content` as well.

The non-streaming JSON path, which ADR 0014 keeps when `stream` is absent, does not use
`StreamParser`. `LLMService.complete_messages()` returns the model's `content` unparsed, and the
conversation service stores it as is. A model that puts `<think>...</think>` in its content would
have the trace saved in `content` and sent back on later turns. The shipped UI uses only the
streaming path.

## Considered options

### Separate the trace from the answer, store it as metadata, and leave it out of later prompts

The policy records no alternatives.

- Good: the main dialogue stays focused, and memory extraction is not confused by internal reasoning
  steps. Reasoning is optional metadata for display or debugging.
- Bad: the trace is kept for display only, so it does not help the model on later turns.

## Decision

We will treat the reasoning trace as separate from the answer: shown as `thought` events while
streaming, and stored in `annotations.thought`.

We will save the clean final answer as the canonical `content` of the assistant message when
streaming.

We will not include reasoning traces in the conversation history sent on later turns, which avoids
context contamination. This applies to traces the parser has separated, which means streamed
replies.

## Consequences

- Good: on the streaming path, prompts and memory extraction see only answers, so reasoning does not
  contaminate context or inflate the prompt.
- Bad: the non-streaming JSON path does not separate reasoning, so the guarantee above holds only
  for streamed replies.
- Good: the UI can show the reasoning separately from the answer.
- Bad: a model's reasoning from an earlier turn is not available to it later, even when it would
  have helped.
- Bad: the parser has to know each model family's reasoning format, and a new format needs a parser
  change.
- Bad: traces add to the size of the stored annotations on every reply that has one.
