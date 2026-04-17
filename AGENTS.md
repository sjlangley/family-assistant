# AGENTS.md

## Required Validation Before Commit Or Push

Treat local validation as a hard gate, not a nice-to-have.
Do not create a commit, push a branch, or open a PR until every relevant check for the files you changed has been run locally and is passing.
Do not rely on CI to tell you what you should have checked before committing.

### Frontend changes: `apps/assistant-ui/**`

Run these from `apps/assistant-ui` whenever you touch frontend code, styles, config, or tests:

```bash
npm run format
npm run lint
npm run typecheck
npm run test:coverage
npm run build
```

### Backend changes: `apps/assistant-backend/**`

Run these from `apps/assistant-backend` whenever you touch backend code, migrations, config, or tests:

```bash
ruff format src/ tests/
ruff check src/ tests/
ruff format --check src/ tests/
pyrefly check src/
pytest -v
```

### Mixed changes

If you touch both apps, run both validation suites before committing or pushing.

### Docs-only changes

If you only change documentation such as `*.md` files, app-specific checks are not required.
Do not claim checks were run when they were skipped.

### Reporting requirements

Before finishing the task, explicitly report:

- Which validation commands you ran
- Whether they passed
- Which checks were intentionally skipped, and why

If a required check fails, fix it before committing or pushing.
If you cannot run a required check, stop before commit or push and explain the blocker.
