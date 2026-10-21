# AI Agent Guidelines

This is the single source of truth for all AI agent behaviour in this repository. `AGENTS.md` defers
to this file, and `CLAUDE.md` points at `AGENTS.md`.

______________________________________________________________________

## Design System

Always read `DESIGN.md` before making any visual or UI decisions. All font choices, colors, spacing,
and aesthetic direction are defined there. Do not deviate without explicit user approval. In QA
mode, flag any code that doesn't match `DESIGN.md`.

______________________________________________________________________

## Test-Driven Development

Follow TDD for all code changes:

1. **Write a failing test first.** Before writing any production code, add a test that captures the
   expected behaviour and confirm it fails (red).
2. **Write the minimum production code** to make the test pass (green).
3. **Refactor** — clean up both the production code and the test while keeping all tests passing.
4. **Never skip the red step.** A test that was never failing gives no confidence.
5. **One behaviour per test.** Keep tests focused and descriptive so failures are easy to diagnose.
6. **Test files mirror source files.** Place tests in `tests/` (backend) or alongside source under
   `src/` (frontend), following existing conventions.
7. **Do not delete or weaken existing tests** to make new code pass — fix the code instead.

______________________________________________________________________

## Required Validation Before Commit or Push

**CRITICAL: These are pre-commit gates, not post-commit checks.**

Treat local validation as a hard gate, not a nice-to-have. Do not create a commit, push a branch, or
open a PR until every relevant check for the files you changed has been run locally and is passing.
Do not rely on CI to tell you what you should have checked before committing.

**The workflow is:**

1. Make code changes
2. Run ALL validation commands for changed files
3. Fix any errors found
4. Re-run ALL validation commands
5. Only when all checks pass → create commit
6. Never commit with failing checks

**Exception:** If you discover a check failure after committing, create a separate fix commit with
the corrected code. Do not amend or rewrite history on branches that have been pushed.

### Pre-commit hooks (all changes)

All commits go through [pre-commit](https://pre-commit.com). The config is `.pre-commit-config.yaml`
and CI re-runs the full suite on every PR (`.github/workflows/pre-commit.yml`).

- Install the hooks **once** after cloning, with both the `pre-commit` and `commit-msg` hooks:
  `pre-commit install`. This needs the backend venv (`apps/assistant-backend/.venv`, so pyrefly can
  resolve imports) and `npm ci` in `apps/assistant-ui` to exist first.
- Run every hook against the whole repo with `pre-commit run --all-files`.
- **Never** bypass the hooks with `git commit --no-verify`. If a hook fails, fix the cause. Hooks
  that auto-fix (ruff, prettier, mdformat, whitespace) leave the changes unstaged: review them,
  `git add` them and commit again.
- The hooks cover format, lint and type checks (ruff, pyrefly, prettier, eslint, tsc), Markdown
  (mdformat, markdownlint), workflow and `dependabot.yml` schemas, shellcheck and secret scanning.
  The `commit-msg` hook enforces Conventional Commits with a subject of 72 characters or fewer.
  Locally the secret scan covers staged changes; CI also scans the commit history reachable from
  `HEAD`. Run the same scan with
  `pre-commit run betterleaks-history --all-files --hook-stage manual`.
- Hooks do **not** run tests or the production build. Keep `pytest`, `npm run test:coverage` and
  `npm run build` as explicit steps below.
- Bump hook versions with `pre-commit autoupdate`. Keep the `ruff-pre-commit` rev in step with the
  `ruff` pin in `apps/assistant-backend/pyproject.toml`.
- `apps/*/CHANGELOG.md` is owned by release-please and the vendored `.agents/skills/` is third-party
  content. Both are excluded from every hook; do not edit them by hand to satisfy a linter.

### Frontend changes: `apps/assistant-ui/**`

**WORKFLOW: Run these in order from `apps/assistant-ui` BEFORE EVERY COMMIT:**

```bash
npm run format        # Auto-fix formatting (REQUIRED, not format:check)
npm run lint          # Check linting rules
npm run typecheck     # Verify TypeScript types
npm run test:coverage # Run all tests with coverage
npm run build         # Verify production build works
```

**All five commands must pass with zero errors before creating a commit.** Do not commit if any
check fails. Fix the issue first, then re-run all checks.

### Backend changes: `apps/assistant-backend/**`

**WORKFLOW: Run these in order from `apps/assistant-backend` BEFORE EVERY COMMIT:**

```bash
source .venv/bin/activate  # Activate virtual environment
ruff format src/ tests/     # Auto-fix formatting
ruff check src/ tests/      # Check linting rules
pyrefly check              # Type check with pyrefly (checks src/, per pyrefly.toml)
pytest -v                   # Run all tests
```

**All checks must pass with zero errors before creating a commit.** Do not commit if any check
fails. Fix the issue first, then re-run all checks.

### Scope rules

- If you touch both apps, run both validation suites.
- If you only change documentation such as `*.md` files, app-specific checks are not required, but
  the pre-commit hooks (mdformat, markdownlint) still run on commit.
- Do not claim checks were run when they were skipped.

### Reporting requirements

**Before creating each commit, explicitly state:**

```text
Pre-commit validation for [backend/frontend]:
✅ format - passed
✅ lint - passed
✅ typecheck - passed (frontend) OR pyrefly - passed (backend)
✅ test:coverage - passed (frontend) OR pytest - passed (backend)
✅ build - passed (frontend only)
```

If a required check fails, do not commit. Report the failure, fix it, re-run all checks, then
commit.

If you cannot run a required check due to environment issues, stop before commit and explain the
blocker.

______________________________________________________________________

## Brevity

These cover the repo's own files and the prose around a change.

No comment where the code already says it. A comment restating the line goes stale, then misleads.
Comment only the non-obvious why: a constraint invisible from the line, a workaround, an override of
an upstream default. One line.

Reasoning goes in the issue or the PR description, not the file. Squash merge makes the description
the commit body, so it is permanent and reachable from `git blame`.

PR descriptions are proportionate. A typo fix needs a sentence; no body at all where the subject and
diff already tell the story. Testing carries evidence, not process.

______________________________________________________________________

## Scope of a Change

One concern per pull request, refactoring in its own.

Do not reformat or rename what the task did not touch. Prettier rewraps whole files here, so one
unrelated edit produces a diff nobody can read.

No drive-by fixes. Open an issue.

No summary or report documents. The PR description is the record.

Flag scope growth before writing the code, not after.

______________________________________________________________________

## Commits and Pull Requests

Conventional Commits, subject line 72 characters or fewer, lowercase, no trailing period. The scope
is the affected area of the repo, for example `ci(pre-commit): add hook for X`. The commitizen
`commit-msg` hook enforces the length.

release-please reads the commit subjects on `main` to cut releases, so use `feat` or `fix` only when
the change should ship in a release. Tooling and housekeeping use `ci`, `chore`, `style`, `docs`,
`test` or `refactor`.

Squash merge. The repo is configured so the PR title becomes the commit subject and the PR
description becomes the commit body, so both are permanent. Write them for someone reading `git log`
in a year. The `Lint PR` workflow checks the title; for a single-commit PR the title must match that
commit.

One branch per PR, cut from `main`, named `<agent>/<type>/<slug>`: `claude/…`, or `ai/…` for an
agent without a prefix of its own. Concurrent agents get a worktree each.

Do not push to `main`, force-push a shared branch, or merge your own PR. The merge is the one point
where a person reads the change before it lands.

Every PR references an issue with `Fixes: #n`, or `Refs: #n` where several PRs land against one
issue. No issue means create one first; a one-line issue is enough.

Agent-assisted work carries a `Co-authored-by` trailer at the end of the PR description. The
identity is the agent's own, not always Claude:

| Agent          | Trailer identity                                            |
| -------------- | ----------------------------------------------------------- |
| Claude Code    | `Claude <noreply@anthropic.com>`                            |
| GitHub Copilot | `generated by GitHub, ...+Copilot@users.noreply.github.com` |

No model name and no version, so that `git log` can answer how much of the repo was written with an
agent: a string that changes with every model release cannot be counted. Add a row when another
agent starts being used. A trailer on a branch commit is discarded by the squash, so the description
is the only place it survives.

______________________________________________________________________

## Getting to Green

CI must be green before a pull request goes for review. Work that is not there yet goes in a draft.

- Do not commit with `--no-verify`, or otherwise skip the hooks.
- Do not delete, skip, or comment out a failing test. Fix the code, or say in the PR why the test
  itself was wrong.
- Do not weaken a lint rule, widen a suppression, or lower a threshold to make existing code pass.
  Adding a rule is fine; removing one is a discussion, not a commit.

______________________________________________________________________

## Database Migrations

### Alembic Infrastructure

Database schema evolution is managed via Alembic migrations in `apps/assistant-backend/alembic/`.

**Key principles:**

- All schema changes MUST go through Alembic migrations.
- Never use `SQLModel.metadata.create_all()` for schema changes in production.
- Migrations must be idempotent (safe to run multiple times).
- Always validate base table dependencies.

### Driver Strategy

The application uses different database drivers for different contexts:

- **Runtime (FastAPI)**: `postgresql+asyncpg` for async operations
- **Migrations (Alembic)**: `postgresql+psycopg` for synchronous operations

The conversion is automatic in `alembic/env.py` — you don't need to configure separate connection
strings.

### Creating Migrations

**Auto-generate from model changes:**

```bash
cd apps/assistant-backend
alembic revision --autogenerate -m "description of changes"
```

**Create empty migration (for data migrations):**

```bash
alembic revision -m "description of changes"
```

Always review auto-generated migrations before applying them. Alembic's autogenerate is good but not
perfect.

### Applying Migrations

**For existing databases** (conversations/messages tables already exist):

```bash
alembic upgrade head
```

**For fresh databases** (CI, new local setups):

1. Bootstrap base schema first via `SQLModel.metadata.create_all()` (conversations, messages
   tables).
2. Mark migrations as applied: `alembic stamp head`.
3. Future migrations will work normally.

See `apps/assistant-backend/alembic/README` for detailed bootstrap instructions.

### Migration Guidelines

1. **Include helpers for idempotency:**

   ```python
   def _has_table(table_name: str) -> bool:
       return table_name in sa.inspect(op.get_bind()).get_table_names()

   if not _has_table('new_table'):
       op.create_table(...)
   ```

2. **Validate dependencies:**

   ```python
   def _require_base_tables() -> None:
       missing = [t for t in ('conversations', 'messages') if not _has_table(t)]
       if missing:
           raise RuntimeError(f'Missing base tables: {missing}')
   ```

3. **Test both upgrade and downgrade:**

   - Run `alembic upgrade head` on a test database.
   - Run `alembic downgrade -1` to verify rollback works.
   - Run `alembic upgrade head` again to verify idempotency.

4. **Model imports required.** All SQLModel table classes must be imported in `alembic/env.py` for
   autogenerate to work:

   ```python
   from assistant.models.conversation_sql import Conversation, Message
   from assistant.models.memory_sql import ConversationMemorySummary, DurableFact
   ```

### Common Issues

**"No module named 'assistant'"**:

- Run from `apps/assistant-backend/` directory.
- Ensure dev dependencies are installed: `pip install -e ".[dev]"`.

**"greenlet_spawn has not been called"**:

- This means you're using asyncpg in Alembic context.
- Check `alembic/env.py` driver conversion is working.

**Fresh database migration fails**:

- Migration assumes base tables exist.
- See "For fresh databases" bootstrap process above.
