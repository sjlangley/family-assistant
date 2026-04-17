# CLAUDE.md

## Design System
Always read `DESIGN.md` before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match `DESIGN.md`.

## Required Validation Before Commit Or Push
Treat local validation as a hard gate.
Do not create a commit, push a branch, or open a PR until every relevant check for the files you changed has been run locally and is passing.
Do not rely on CI as a substitute for running the checks yourself.

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

### Scope rules
- If you touch both apps, run both validation suites.
- If you only change documentation such as `*.md` files, app-specific checks are not required.
- Do not claim checks were run when they were skipped.

### Reporting requirements
- Explicitly report which validation commands you ran and whether they passed.
- Explicitly report any skipped checks and why they were skipped.
- If a required check fails or cannot be run, stop before commit or push and explain the blocker.

## Database Migrations

### Alembic Infrastructure
Database schema evolution is managed via Alembic migrations in `apps/assistant-backend/alembic/`.

**Key principles:**
- All schema changes MUST go through Alembic migrations
- Never use `SQLModel.metadata.create_all()` for schema changes in production
- Migrations must be idempotent (safe to run multiple times)
- Always validate base table dependencies

### Driver Strategy
The application uses different database drivers for different contexts:
- **Runtime (FastAPI)**: `postgresql+asyncpg` for async operations
- **Migrations (Alembic)**: `postgresql+psycopg` for synchronous operations

The conversion is automatic in `alembic/env.py` - you don't need to configure separate connection strings.

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

**Always review auto-generated migrations** before applying them. Alembic's autogenerate is good but not perfect.

### Applying Migrations

**For existing databases** (conversations/messages tables already exist):
```bash
alembic upgrade head
```

**For fresh databases** (CI, new local setups):
1. Bootstrap base schema first via `SQLModel.metadata.create_all()` (conversations, messages tables)
2. Mark migrations as applied: `alembic stamp head`
3. Future migrations will work normally

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
   - Run `alembic upgrade head` on a test database
   - Run `alembic downgrade -1` to verify rollback works
   - Run `alembic upgrade head` again to verify idempotency

4. **Model imports required:**
   All SQLModel table classes must be imported in `alembic/env.py` for autogenerate to work:
   ```python
   from assistant.models.conversation_sql import Conversation, Message
   from assistant.models.memory_sql import ConversationMemorySummary, DurableFact
   ```

### Common Issues

**"No module named 'assistant'"**:
- Run from `apps/assistant-backend/` directory
- Ensure dev dependencies installed: `pip install -e ".[dev]"`

**"greenlet_spawn has not been called"**:
- This means you're using asyncpg in Alembic context
- Check `alembic/env.py` driver conversion is working

**Fresh database migration fails**:
- Migration assumes base tables exist
- See "For fresh databases" bootstrap process above
