# Copilot Instructions for Family Assistant

Family Assistant is a self-hosted, multi-user household AI assistant with Google sign-in and
per-user conversation memory.

All agent behaviour is governed by [AGENTS.md](../AGENTS.md) and
[AI_AGENT_GUIDELINES.md](../AI_AGENT_GUIDELINES.md). Read them before changing anything. Accepted
architecture decisions in [docs/adr/](../docs/adr/README.md) bind; specs, plans and roadmap items
live in GitHub issues.

## Stack

- **Backend** (`apps/assistant-backend/`): Python 3.13+, FastAPI, SQLModel, PostgreSQL 16, Chroma
- **Frontend** (`apps/assistant-ui/`): TypeScript, React 19, Vite 8, Tailwind CSS 4, Vitest
- **LLM runtime**: Ollama in Docker Compose by default, or another OpenAI-compatible server
  (`apps/llm-server/`)

## Run and test

Backend, from `apps/assistant-backend`:

```bash
pip install -e ".[dev]"
uvicorn assistant.app:app --reload --port 8080
ruff format src/ tests/ && ruff check src/ tests/
pyrefly check
pytest                         # coverage must stay at or above 90%
```

Frontend, from `apps/assistant-ui`:

```bash
npm ci
npm run dev                    # needs VITE_API_BASE_URL and VITE_GOOGLE_CLIENT_ID
npm run format && npm run lint && npm run typecheck
npm run test:coverage
npm run build
```

Full stack: `cp .env.example .env`, fill in the required values, then `docker compose up --build`
(see [DOCKER.md](../DOCKER.md)). Frontend on port 3000, backend on port 8080.

## Rules

- Write a failing test first, then the code.
- Run the full local validation for every app you touched, and `pre-commit run --all-files`, before
  committing. Never use `--no-verify`.
- Schema changes go through Alembic migrations.
- Read [DESIGN.md](../DESIGN.md) before any UI change.
- Use Conventional Commits (subject of 72 characters or fewer). PRs are squash-merged, follow the PR
  template, and reference an issue with `Fixes: #n`, or `Refs: #n` where several PRs land against
  one issue.
- Keep secrets in environment variables, and never mix one user's data with another's.
