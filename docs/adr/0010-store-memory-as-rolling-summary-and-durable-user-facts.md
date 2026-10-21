---
status: accepted
date: "2026-04-13"
supersedes: []
superseded_by:
---

# 0010. Store memory as a rolling conversation summary and durable user facts

## Context

Recorded retrospectively. The tables came in #57 (2026-04-13), and the extraction that fills them
arrived in #80 (2026-04-16). The decision date is the earlier one.

The assistant keeps two kinds of memory in PostgreSQL (`models/memory_sql.py`, ADR 0005):

- one summary per conversation (`conversation_memory_summaries`). The row is unique per conversation
  and is overwritten, with its `version` incremented, on each update.
- durable facts about the user (`durable_facts`), each with a subject, text, confidence of low,
  medium or high, a source, and an `active` flag. A fact with a `fact_key` is replaced by a newer
  one with the same key; one without is de-duplicated on subject and text. The extraction prompt
  does not ask for a `fact_key`.

After a successful reply, `ConversationService.extract_and_save_background` asks the model for a
brief one-sentence summary of "this conversation update" and any important facts about the user, as
JSON. The prompt holds the new assistant message and up to three messages before it, not the
previous summary. The reply is parsed leniently: the text between the first `{` and the last `}` is
read, and facts missing a subject or text are dropped. Parsing failures leave memory unchanged.

## Considered options

### A summary per conversation, updated as it continues, plus durable facts per user

No alternatives were formally weighed at the time.

- Good: the author built it this way to learn how memory systems work.
- Bad: memory quality depends on the configured model producing valid JSON with useful facts.

## Decision

We will remember a conversation as one summary that is overwritten as the conversation continues.

We will remember the user as a set of durable facts extracted from conversations, each with its
source and confidence.

We will extract both with a model call after each successful reply.

## Consequences

- Good: prompt context stays small, since only the latest summary and a few facts are injected (ADR
  0012).
- Good: each fact records where it came from, and the assistant's trust annotations report what was
  actually saved (ADR 0013).
- Bad: a summary replaces its predecessor and is written from the latest few messages only, so
  earlier wording is not kept. Only the latest `version` exists.
- Bad: extraction is a second model call per reply and can miss facts or record wrong ones.
