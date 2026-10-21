# AGENTS.md

All agent behaviour for this repository is governed by
[AI_AGENT_GUIDELINES.md](./AI_AGENT_GUIDELINES.md).

Read that file in full before taking any action. The sections you must follow are:

- **Architecture Decision Records** — read `docs/adr/` before any architectural change; accepted
  ADRs bind, and a conflicting change needs a superseding ADR, never an edit.
- **Test-Driven Development** — write a failing test before production code.
- **Required Validation Before Commit or Push** — run the full local suite; never rely on CI as a
  substitute.
- **Database Migrations** — all schema changes go through Alembic.
- **Scope of a Change** and **Brevity** — one concern per PR; no drive-by fixes or restating
  comments.
- **Commits and Pull Requests** — Conventional Commits, squash merge, `Fixes: #n`, and the agent
  `Co-authored-by` trailer in the PR description.
- **Getting to Green** — never skip hooks, delete failing tests or weaken lint rules.
- **Design System** — consult `DESIGN.md` before any visual/UI change.

<!-- Claude Code import, so the full guidelines load with this file. -->

@AI_AGENT_GUIDELINES.md
