---
status: accepted
date: "2026-04-13"
supersedes: []
superseded_by:
---

# 0013. Persist trust annotations on assistant messages

## Context

Recorded retrospectively. The `annotations` column on messages came in #57 (2026-04-13).
`AssistantAnnotationService`, which fills it, came in #77 (2026-04-15).

`DESIGN.md` sets the principle "Put proof next to the answer it explains", and its decision log
records keeping proof attached to each answer instead of a separate debug screen (2026-04-13).

Each assistant message has a JSON `annotations` field (`models/annotations.py`, added by Alembic
migration `57bad9ffdeea`). It can hold the sources used, the tools that ran and whether they
completed or failed, the memory facts put in the prompt (`memory_hits`), the memory saved afterwards
(`memory_saved`), a structured failure, the `finish_reason`, and the reasoning trace (ADR 0016).

`services/assistant_annotations.py` builds the annotations when the message is saved, within small
budgets: 3 sources, 2 tools, 2 memory hits and 1 memory-saved entry. Sources come only from pages
that `web_fetch` actually fetched, never from search snippets alone. `memory_saved` is added after
background extraction has committed (ADR 0011). `ConversationsChat.tsx` renders the annotations as a
trust row and evidence panel.

## Considered options

### Store the trust metadata with the message, built by the backend

No alternatives were formally weighed at the time.

- Good: it follows the trust-first design in `DESIGN.md`, and only the backend knows what really
  happened during a reply.
- Bad: annotation fields become part of the stored message format and the API.

## Decision

We will build trust annotations in the backend and persist them in the `annotations` field of the
assistant message they explain.

We will have the frontend render the persisted annotations and not generate trust information
itself.

## Consequences

- Good: the proof shown for a reply is the same after a reload, and cannot differ from what the
  backend recorded.
- Good: failures are recorded the same way as successes, so a failed reply still explains itself.
- Bad: the annotation shape is a stored contract. Changing a field means handling messages already
  saved, and the frontend type in `apps/assistant-ui/src/types/api.ts` must follow it.
- Bad: the budgets cap what is shown (3 sources, 2 tools, and so on), so the record is a summary of
  what happened, not a full log.
- Bad: `memory_saved` is written after the reply, so it can be missing if extraction is lost (ADR
  0011).
