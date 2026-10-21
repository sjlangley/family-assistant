---
status: accepted
date: "2026-04-13"
supersedes: []
superseded_by:
---

# 0005. Use PostgreSQL as source of truth with Chroma as a derived index

## Context

Recorded retrospectively. Chroma was first added in #43 (2026-03-17) as a vector memory store
(`MemoryStorage.add_memory` still writes entries under a random ID). The decision to make PostgreSQL
the record was made in #57 (2026-04-13), which added the `conversation_memory_summaries` and
`durable_facts` tables (`models/memory_sql.py`).

Those tables hold what the assistant remembers. A durable fact carries its `subject`, optional
`fact_key`, `confidence`, `source_type`, source conversation and message, a source excerpt and an
`active` flag. A summary carries a `version`. Both are keyed by `user_id` (ADR 0004).

`services/memory_storage.py` mirrors rows to Chroma with `index_conversation_summary` and
`index_durable_fact`, which upsert under a stable document ID derived from the Postgres row ID.
`services/context_assembly.py` asks Chroma for ranked candidate fact IDs only when it loads facts
for a conversation's first message, then reloads the facts from Postgres before building the prompt.
If that Chroma query fails or returns nothing, it falls back to recency-based selection from
Postgres. Later messages in an existing conversation never query Chroma.

## Considered options

### Chroma alone as the memory record

This is what #43 started with.

- Good: a single store to run.
- Bad: a vector database cannot hold provenance, versions, active or inactive state and per-user
  queries well enough to be the record.

### PostgreSQL as the record, Chroma as a derived index

- Good: memory facts keep provenance, versions and active state, and can be queried per user and
  audited.
- Bad: every write has to update two stores, and they can drift apart.

## Decision

We will store summaries and durable facts in PostgreSQL as the source of truth.

We will use Chroma only as a derived index for ranking, with stable IDs tied to the Postgres rows,
and we will reload the actual content from PostgreSQL before it reaches a prompt.

## Consequences

- Good: trust and auditability. A remembered fact can record its source conversation, message and
  excerpt, and can be deactivated without losing it.
- Good: once the backend has built its memory service, a Chroma failure degrades ranking rather than
  stopping the assistant, because context assembly falls back to recency-based selection from
  PostgreSQL.
- Bad: that tolerance does not cover Chroma being unreachable when `MemoryStorage` is first built.
  Its constructor connects to Chroma and creates the collection, and every conversation endpoint
  needs it, so they all fail until Chroma is reachable.
- Bad: the two stores can drift. A row written to PostgreSQL but not indexed is invisible to
  semantic ranking until it is indexed again.
- Bad: the stack needs both PostgreSQL and a Chroma server in `docker-compose.yml`.
