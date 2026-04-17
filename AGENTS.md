# AGENTS.md

All agent behaviour for this repository is governed by
[AI_AGENT_GUIDELINES.md](./AI_AGENT_GUIDELINES.md).

Read that file in full before taking any action. The sections you must follow
are:

- **Test-Driven Development** — write a failing test before production code.
- **Required Validation Before Commit or Push** — run the full local suite;
  never rely on CI as a substitute.
- **Database Migrations** — all schema changes go through Alembic.
- **Design System** — consult `DESIGN.md` before any visual/UI change.
