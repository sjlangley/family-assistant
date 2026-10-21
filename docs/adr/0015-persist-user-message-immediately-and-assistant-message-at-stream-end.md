---
status: accepted
date: "2026-04-20"
supersedes: []
superseded_by:
---

# 0015. Persist the user message immediately and the assistant message at stream end

## Context

Recorded retrospectively. The rule was written into the streaming PRD (#95, ADR 0014) and
implemented in #106 (2026-04-20). The Stop control that depends on it came in #113 (2026-04-21). The
reasons are taken from the persistence section of `docs/STREAMING_RESPONSES_PRD.md`.

A streamed reply takes seconds to minutes and can fail, be cut short or be stopped by the user. The
PRD aims for a consistent history that keeps failure recovery meaningful, with messages persisted to
PostgreSQL once the stream is complete.

`ConversationService` (`services/conversation_service.py`) saves in two phases:

1. The conversation and the user message are committed as soon as the request is accepted.
2. `_stream_assistant_lifecycle` saves the assistant message when the stream reaches a terminal
   state:
   - on success, with the full content, reasoning trace, tool annotations and `finish_reason`;
   - on a model or tool error after output has started, with the content received so far and a
     failure annotation;
   - on cancellation, such as the client disconnecting after the Stop button, with the content so
     far and an error saying the stream was interrupted.

If an error happens before any output, no assistant message is saved and the user message remains.
Background memory extraction is scheduled only after a successful save (ADR 0011).

## Considered options

### User message at once, assistant message at the end of the stream

The PRD does not list alternatives for this rule.

- Good: the user's turn is durable even if generation or streaming fails, and the assistant row is
  written once, complete, with its annotations.
- Bad: the assistant's partial text exists only in memory until the stream ends, so it is lost if
  the process stops mid-stream.

## Decision

We will persist the user message as soon as a request is accepted.

We will persist the assistant message once, when the stream reaches a terminal state: success, an
error after output has started, or cancellation after output has started.

## Consequences

- Good: history never loses what the user asked, and an interrupted reply is kept as an assistant
  message in a terminal error state.
- Good: the annotations (ADR 0013) are written in the same save as the content, so they match it.
- Bad: if the backend process dies mid-stream, the assistant message is not saved at all, and the
  history ends with an unanswered user message.
- Bad: a failure before the first output leaves a user message with no reply and no failure record
  on an assistant message.
- Bad: while a reply is streaming, a second client loading the conversation does not see it.
