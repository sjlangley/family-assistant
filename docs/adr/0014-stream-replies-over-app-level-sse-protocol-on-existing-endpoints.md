---
status: accepted
date: "2026-04-18"
supersedes: []
superseded_by:
---

# 0014. Stream replies over an app-level SSE protocol on the existing endpoints

## Context

Recorded retrospectively. The design was written up in the streaming PRD (#95, 2026-04-18) and
implemented in a series of changes from #99 to #104 and #106. The options and reasons below are
taken from `docs/STREAMING_RESPONSES_PRD.md`.

Before this work, a reply was one blocking model call, so the user saw a spinner for the 10 to 60
seconds or more that a local or reasoning model can take. The product goal was to show the reply as
it is generated, and keep tool calling and background memory extraction working.

The backend now returns `text/event-stream` from `POST /api/v1/conversations/with-message` and
`POST /api/v1/conversations/{id}/messages` when the request body has `stream: true`
(`routers/conversations.py`). `SSEEncoder` (`utils/sse.py`) emits the app's own events: `thought`,
`token`, `tool_call`, `done` and `error`. The frontend reads the stream with `fetch` in
`apps/assistant-ui/src/lib/api.ts` and the `useStreamingConversation` hook.

## Considered options

### Server-Sent Events

- Good: the reply is a one-way stream from server to client, and SSE is simpler to implement and
  maintain than WebSockets and more efficient than long polling.

### WebSockets

- Bad: the PRD lists full bidirectional WebSockets as a non-goal. They are not needed for this use
  case.

### Long polling

- Bad: less efficient than SSE, per the PRD.

### Streaming on the existing endpoints, selected by `stream: true`

- Good: keeps the API surface clean. The resource created is the same message, and only the delivery
  changes.

### A new `/stream` endpoint

- Bad: the PRD chose the existing endpoints over it. It adds a second path for the same resource.

## Decision

We will deliver streamed replies as Server-Sent Events.

We will define an application-level event protocol (`thought`, `token`, `tool_call`, `done`,
`error`) and not pass the model server's chunks through.

We will stream on the existing conversation endpoints, selected by `stream: true` in the request
body, and keep the JSON response when it is absent.

## Consequences

- Good: replies appear as they are generated, and the protocol is independent of the model server's
  chunk format, so the UI does not depend on the runtime (ADR 0007).
- Good: reasoning is a separate event type, which ADR 0016 relies on. Closing the connection lets
  the backend see the cancellation, which the Stop button uses (ADR 0015).
- Bad: the backend and frontend both have to implement the protocol by hand, and a new event type
  needs both sides to change.
- Bad: each endpoint has two response shapes, JSON and event stream, to document and test.
- Bad: tool calls inside a stream complicate the loop, which has to pause the output while a tool
  runs (ADR 0008).
