---
status: accepted
date: "2026-03-11"
supersedes: []
superseded_by:
---

# 0004. Isolate conversations and memory per user

## Context

Recorded retrospectively. The decision was made when conversations were first persisted, in #36
(2026-03-11).

The assistant is used by several family members, each signed in with their own Google account (ADR
0003). The user's identity (`userid`, the Google `sub`) is stored as a `user_id` string on every
conversation and, later, on every memory row.

In the code, `user_id` scopes:

- conversation queries in `services/conversation_service.py`, which answer "Conversation not found"
  (HTTP 404) for a conversation that belongs to someone else;
- the conversation summaries and durable facts in `models/memory_sql.py`, including the unique
  indexes on durable facts;
- the Chroma queries in `services/memory_storage.py`, which filter on `user_id`;
- prompt assembly in `services/context_assembly.py`, which loads only the current user's facts.

`docs/ARCHITECTURE.md` lists household shared-memory features under "Current Boundaries" as not
shipped.

## Considered options

### Scope every conversation and memory record to its owner

No alternatives were formally weighed at the time.

- Good: family members cannot see each other's chats or remembered facts by default.
- Bad: nothing is shared between family members, so a fact one person tells the assistant is unknown
  to the others.

## Decision

We will scope every conversation, summary, durable fact and index entry to the user who created it.

We will treat any sharing between family members as a future, explicit opt-in, not as a default.

## Consequences

- Good: privacy is the default, and each query's `user_id` filter is one place to review.
- Good: sharing can be added later without having to undo a shared-by-default design.
- Bad: every new query that touches conversations or memory has to remember the `user_id` filter.
  The database does not enforce it; no row-level security is configured.
- Bad: household shared memory, listed as not shipped in `docs/ARCHITECTURE.md`, needs a new design
  and a new ADR.
