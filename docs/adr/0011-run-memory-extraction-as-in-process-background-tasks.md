---
status: accepted
date: "2026-04-16"
supersedes: []
superseded_by:
---

# 0011. Run memory extraction as in-process background tasks

## Context

Recorded retrospectively. The date is approximate. It is the merge date of #80 (2026-04-16), the
first change in which `extract_and_save_background` and FastAPI `BackgroundTasks` appear in the
backend source, found by searching the history.

Memory extraction (ADR 0010) is a second model call that runs after the assistant message has been
saved. `ConversationService` schedules `extract_and_save_background` with FastAPI's
`BackgroundTasks` after a successful reply, in the plain reply paths and in the streaming path (ADR
0014), whenever memory storage is configured. The job runs in the web process after the response is
sent. It opens its own database session through `get_db_session()` (`utils/database.py`), reloads
the conversation from PostgreSQL, and logs any failure without affecting the saved reply. When it
succeeds it adds a `memory_saved` annotation to the assistant message.

`entrypoint.sh` starts one gunicorn worker (`--workers 1`), a setting that dates from the initial
scaffold in #1.

## Considered options

### FastAPI `BackgroundTasks` in the web process

A queue with a separate worker was deferred until it is needed. No other alternatives were recorded.

- Good: simplest first. It needs no extra infrastructure.
- Bad: jobs live only in the memory of the web process.

## Decision

We will run memory extraction as a FastAPI background task in the backend process, after the
assistant message is persisted.

We will defer a job queue and a separate worker until they are needed.

## Consequences

- Good: no queue, broker or worker to deploy, and extraction failures cannot fail a reply.
- Bad: a job that has not finished when the process restarts or stops is lost, and nothing retries
  it. That conversation's memory is not updated.
- Bad: the jobs run inside the web process, which `entrypoint.sh` starts with a single worker, so
  extraction shares that process with request handling.
- Bad: each job creates and disposes its own database engine instead of reusing the app's (#137).
- Moving to a queue and worker later is a new decision that supersedes this ADR.
