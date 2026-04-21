# Copilot Instructions for Family Assistant

This document provides accurate, up-to-date guidance for GitHub Copilot and human
developers working in this repository.

## Project Overview

Family Assistant is a self-hosted, multi-user, multi-modal AI assistant for
household use. It uses Google OAuth 2.0 for authentication and supports per-user
memory isolation.

**Tech stack:**
- **Backend**: Python 3.13+ / FastAPI (`apps/assistant-backend/`)
- **Frontend**: TypeScript / React 19 / Vite (`apps/assistant-ui/`)
- **Database**: PostgreSQL 16
- **LLM Runtime**: llama.cpp / Ollama (external service, `apps/llm-server/`)
- **Auth**: Google OAuth 2.0 with session cookies

---

## Repository Structure

```
apps/
  assistant-backend/   # FastAPI Python backend
    src/assistant/     # Application source
      routers/         # API route handlers
      models/          # Pydantic models
      security/        # Auth & session management
      services/        # Business logic (LLM, tool loop, etc.)
        tools/         # Concrete backend tools: current time, web search, web fetch
    tests/             # Pytest test suite
  assistant-ui/        # React TypeScript frontend
    src/
      components/      # React components
      lib/             # API client, auth context
      types/           # TypeScript type definitions
  llm-server/          # Local LLM setup instructions (README only)
docs/                  # Architecture documentation
.github/workflows/     # CI/CD pipelines
docker-compose.yml     # Full stack orchestration
.env.example           # Environment variable template
```

---

## Backend (`apps/assistant-backend/`)

### Language & Runtime
- Python **3.13+** (uses `StrEnum` and other 3.13+ features)
- FastAPI with Starlette `SessionMiddleware` (cookie: `family-assistant-session`)

### Running locally
```bash
cd apps/assistant-backend
pip install -e ".[dev]"
uvicorn assistant.app:app --reload --port 8000
```

### Testing
```bash
cd apps/assistant-backend
pytest                         # run all tests
pytest --cov --cov-report=term # with coverage report
```
- Coverage threshold: **90%** (enforced in CI via `cov-fail-under=90`)
- Tests live in `tests/` mirroring the `src/assistant/` structure
- Uses `pytest-asyncio` for async test support

### Linting & Formatting
```bash
cd apps/assistant-backend
ruff check src/ tests/         # lint
ruff format src/ tests/        # format
pyrefly check src/             # type checking
```
- **Ruff** handles both linting and formatting (configured in `/ruff.toml`)
- **Pyrefly** for type analysis
- Single quotes for all strings (`quote-style = "single"` in `ruff.toml`)
- 80-character line length
- Google Python Style Guide

### Code Style (Python)
- Type annotations required for all public functions and class attributes
- Docstrings required for all public classes and functions
- Single quotes for strings
- Imports sorted per `ruff.toml` isort configuration (`known-first-party = ["assistant"]`)

### Backend capabilities to keep in mind
- Conversation replies use one bounded native tool loop through `ConversationService`
- Token limits enforced via `LLM_MAX_TOKENS` setting (default: 1024 tokens)
- Truncation recovery: finish_reason tracking enables Continue button in UI
- Tool definitions and dispatch live in `src/assistant/services/tools/`
- The currently shipped backend tools are:
  - `get_current_time`
  - `web_search`
  - `web_fetch`
- `web_fetch` is intentionally limited to public web targets and must keep its SSRF protections intact

---

## Frontend (`apps/assistant-ui/`)

### Language & Runtime
- TypeScript 5 with strict mode enabled
- React 18 + Vite 5 + Tailwind CSS 3

### Running locally
```bash
cd apps/assistant-ui
npm ci
npm run dev                    # dev server (requires VITE_* env vars)
```

Required environment variables (Vite bakes these in at build time):
- `VITE_API_BASE_URL` — backend URL (e.g. `http://localhost:8080`)
- `VITE_GOOGLE_CLIENT_ID` — Google OAuth client ID

### Testing
```bash
cd apps/assistant-ui
npm run test                   # run Vitest
npm run test:coverage          # with coverage report
```
- Uses **Vitest** (not Jest) with `jsdom` environment
- Test setup file: `src/setupTests.ts` (extends `@testing-library/jest-dom`)
- Coverage threshold: **80%** minimum

### Linting, Formatting & Type Checking
```bash
cd apps/assistant-ui
npm run lint          # ESLint
npm run format        # Prettier (write)
npm run format:check  # Prettier (check only)
npm run typecheck     # tsc --noEmit
npm run build         # production build (also validates types)
```
- **ESLint** + **Prettier** for linting and formatting
- Strict TypeScript (`tsconfig.json`)

---

## Docker / Full Stack

```bash
cp .env.example .env           # fill in required values
docker compose up --build      # start all services
```

Service URLs:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8080
- Health check: http://localhost:8080/health

See `.env.example` for all required environment variables. Secrets to set:
- `SESSION_SECRET_KEY` — generate with `openssl rand -hex 32`
- `GOOGLE_OAUTH_CLIENT_ID` / `VITE_GOOGLE_CLIENT_ID` — must be identical

The LLM server runs **outside Docker** on the host machine. The backend connects
to it via `LLM_BASE_URL` (default: `http://host.docker.internal:8000`).

---

## CI/CD Workflows

| Workflow | Trigger | Steps |
|---|---|---|
| `assistant-backend-lint.yml` | push/PR on `apps/assistant-backend/` | ruff check, ruff format, pyrefly |
| `assistant-backend-test.yml` | push/PR on `apps/assistant-backend/` | pytest with coverage, codecov upload |
| `assistant-backend-docker-build.yml` | push/PR on `apps/assistant-backend/` | Docker build + health check |
| `assistant-ui-ci.yml` | push/PR on `apps/assistant-ui/` | lint, format:check, typecheck, test:coverage, build, codecov |
| `assistant-ui-docker-build.yml` | push/PR on `apps/assistant-ui/` | Docker build + health check |

All CI checks must pass before merging.

---

## Commit & PR Guidelines

- Use **conventional commit syntax**: `feat:`, `fix:`, `chore:`, `test:`, `docs:`
- All commits must pass formatting, linting, and tests before merging
- Each PR should include unit tests for new code
- Coverage must not drop below the thresholds above

---

## Key Principles

1. **Never hardcode secrets** — use environment variables
2. **Per-user memory isolation** — never mix data between users
3. **No bypassing lint/format checks** — all code must pass CI
4. **Modular design** — keep routers, services, and models separate
5. **Type safety** — type annotations in Python, strict TypeScript in frontend
