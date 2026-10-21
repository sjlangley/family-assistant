---
status: accepted
date: "2026-04-13"
supersedes: []
superseded_by:
---

# 0006. Manage schema with Alembic and bootstrap base tables at startup

## Context

Recorded retrospectively. Alembic was added in #67 (2026-04-13). Before that, the backend created
its tables with `SQLModel.metadata.create_all()` in the app's startup hook (`app.py`), which dates
from #36 (2026-03-11) and is still there.

PR #67 added `apps/assistant-backend/alembic/`. The driver is converted in `alembic/env.py`: the app
uses `postgresql+asyncpg` and Alembic uses `postgresql+psycopg`. Its first migration
(`57bad9ffdeea`) adds the `annotations` column and creates the memory tables, and it assumes the
`conversations` and `messages` tables already exist. `alembic/README` therefore tells a fresh
database to be built with `create_all` and then marked with `alembic stamp head`. Startup
`create_all` creates every table registered by then, memory tables included, so only the `stamp`
step is manual. The same README lists a baseline migration as a second option and calls it
recommended for production.

The app does not run `alembic upgrade` at startup. `create_all` creates missing tables only and does
not alter existing ones.

The reason for choosing the bootstrap over a baseline migration was not recorded. The owner now
wants to change it.

## Considered options

### Alembic migrations on top of `create_all` for the base tables

- Good: the tables that already existed needed no migration, and later changes are versioned.
- Bad: two sources of schema truth, which can drift (see #138).

### Alembic baseline migration for the whole schema

This is the second option in `alembic/README`.

- Good: `alembic upgrade head` could build a fresh database from empty.
- Bad: why it was not adopted in #67 was not recorded.

## Decision

We will manage schema changes with Alembic migrations in `apps/assistant-backend/alembic/`.

We will keep running `SQLModel.metadata.create_all()` at startup, which creates every registered
table that is missing, including the base `conversations` and `messages` tables, and bootstrap a
fresh database by starting the app and then running `alembic stamp head`.

## Consequences

- Good: schema changes since #67 are versioned migrations.
- Bad: a fresh database needs a manual `alembic stamp head` step after the app's startup
  `create_all` has created its tables, and the first migration cannot run on an empty database.
- Bad: `create_all` and the migrations can disagree; for example, `create_all` already creates the
  unique indexes that migration `af123dbd3ffa` also creates (#138).
- Bad: `AI_AGENT_GUIDELINES.md` says never to use `create_all` for schema changes in production,
  while the app calls it on every startup.
- #160 tracks making Alembic own the whole schema with a baseline migration and dropping
  `create_all` at startup. That change needs an ADR that supersedes this one.
