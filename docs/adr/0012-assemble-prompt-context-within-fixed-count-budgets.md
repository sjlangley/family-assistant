---
status: accepted
date: "2026-04-14"
supersedes: []
superseded_by:
---

# 0012. Assemble prompt context within fixed count budgets

## Context

Recorded retrospectively. The decision was made in #71 (2026-04-14), which added
`ContextAssemblyService` as "bounded prompt assembly".

`services/context_assembly.py` builds the message list for each model call from PostgreSQL (ADR
0005), with limits set as constants in that file:

| Constant                           | Value | Limits                                   |
| ---------------------------------- | ----- | ---------------------------------------- |
| `MAX_RECENT_MESSAGES_WITH_SUMMARY` | 4     | recent messages when a summary exists    |
| `MAX_RECENT_MESSAGES_NO_SUMMARY`   | 8     | recent messages when there is no summary |
| `MAX_DURABLE_FACTS`                | 5     | facts put in the prompt                  |
| `MAX_FACT_CANDIDATES`              | 15    | facts considered when ranking            |
| `MAX_FACT_TEXT_LENGTH`             | 200   | characters per fact                      |
| `MAX_SUMMARY_TEXT_LENGTH`          | 1000  | characters of summary                    |

The prompt holds the system prompt, the summary and facts as labelled messages, the recent turns and
the new message. Facts are chosen by relevance to the recent turns, or, for a new conversation, by
Chroma ranking with a recency fallback. The budgets count messages and characters. They do not count
tokens.

## Considered options

### Fixed counts of messages, facts and characters

No alternatives were formally weighed at the time.

- Good: the author built it this way to learn, starting simple.
- Bad: counts say nothing about how many tokens the prompt actually uses.

## Decision

We will bound the prompt with fixed counts: a number of recent messages, a number of durable facts,
and a maximum length for each fact and for the summary.

We will keep these limits as named constants in `services/context_assembly.py`.

## Consequences

- Good: the limits are easy to read, change and test, and a prompt cannot grow without bound as a
  conversation lengthens.
- Bad: a few long messages can still make a large prompt, and short ones waste the available space.
  Nothing measures the real size against the model's context window.
- Bad: when a conversation has a summary, only the last 4 messages are sent, so older detail
  survives only if the summary kept it.
- `docs/PROMPT_TOKEN_REDUCTION_PLAN.md` proposes measuring prompt size in tokens, and replacing the
  fixed-count history inclusion with adaptive selection. If that goes ahead it would supersede this
  decision.
