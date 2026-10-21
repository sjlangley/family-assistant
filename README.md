# Family AI Assistant

A self-hosted, multi-user household assistant built around trustworthy text chat. The current
shipped core combines a local OpenAI-compatible LLM, canonical Postgres-backed conversation memory,
a bounded web research path, and persisted trust metadata in the desktop chat UI.

## What Exists Today

- **Multi-user conversations** Google-authenticated users get isolated conversation history and
  memory at the API and storage layers.
- **Canonical conversation memory** Successful replies trigger background extraction that refreshes
  one latest summary per conversation and per-user durable facts in PostgreSQL.
- **Bounded research tools** Conversation replies can use an explicit allowlist of tools, with
  `web_search` for source discovery and `web_fetch` for grounded page reads.
- **Persisted trust metadata** Assistant messages store compact `annotations` so reloads preserve
  tool usage, evidence sources, memory hits, memory saves, and terminal failure context.
- **Desktop trust UI** The conversation shell renders an inline trust row plus an evidence panel
  driven entirely by persisted annotations.
- **Real-time streaming responses** Assistant replies stream in real-time via Server-Sent Events,
  with token-limit handling (configurable via `LLM_MAX_TOKENS`, default: 1024). When responses
  truncate due to length, UI displays a Continue button.
- **Direct chat endpoint** The backend also keeps a simpler `/api/v1/chat/completions` path for
  non-conversation chat requests through the shared LLM completion seam.

## Tech Stack

- **Backend:** Python 3.13+, FastAPI, SQLModel, SQLAlchemy async
- **Frontend:** TypeScript, React 19, Vite
- **LLM runtime:** Ollama by default in Docker Compose, or another local OpenAI-compatible server
- **Storage:** PostgreSQL 16 for canonical data, Chroma for retrieval support
- **Authentication:** Google OAuth 2.0 with server-side sessions
- **Validation:** Ruff + Pyrefly + pytest on the backend, ESLint + Prettier + TypeScript + Vitest on
  the frontend

## Getting Started

### Quick Start with Docker (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/sjlangley/family-assistant.git
cd family-assistant

# 2. Configure environment
cp .env.example .env
# Edit .env with your Google OAuth credentials and other settings

# 3. Start all services
docker compose up -d --build

# 4. Pull the default local model once
docker compose exec ollama ollama pull qwen2.5:7b
```

See [DOCKER.md](DOCKER.md) for detailed Docker setup instructions.

### Manual Development Setup

1. Clone the repo
2. Install Python 3.13+ dependencies via pip
3. Install Node.js 22.13+ dependencies for the frontend
4. Configure Google OAuth credentials
5. Start PostgreSQL, the LLM server, the backend, and the frontend

See individual READMEs for detailed instructions:

- [Backend Setup](apps/assistant-backend/README.md)
- [Frontend Setup](apps/assistant-ui/README.md)
- [LLM Server Setup](apps/llm-server/README.md)

### Pre-commit Hooks

Commits are checked by [pre-commit](https://pre-commit.com) (ruff, pyrefly, prettier, eslint, tsc,
mdformat, markdownlint, the ADR format check (adr-check), shellcheck, secret scanning, and
Conventional Commit messages). CI runs the same hooks on every pull request. The adr-check hook
needs a `python3.14` executable on your `PATH`. Install the tool once, then the hooks:

```bash
# 1. Backend venv, so the pyrefly hook can resolve imports
python3 -m venv apps/assistant-backend/.venv
apps/assistant-backend/.venv/bin/pip install -e "apps/assistant-backend[dev]"

# 2. Frontend dependencies, so the prettier/eslint/tsc hooks use the pinned versions
npm ci --prefix apps/assistant-ui

# 3. Install pre-commit (uv tool install pre-commit, pipx install pre-commit, or pip) and the hooks
pre-commit install   # installs both the pre-commit and commit-msg hooks

# Run every hook against the whole repo
pre-commit run --all-files
```

Do not bypass the hooks with `git commit --no-verify`; fix what they report. Hooks do not run tests,
so still run `pytest` and `npm run test:coverage` (see the app READMEs). Update pinned hook versions
with `pre-commit autoupdate`.

## Project Docs

- [Architecture decisions](docs/adr/README.md)
- [Design System](DESIGN.md)
- [Roadmap and specs](https://github.com/sjlangley/family-assistant/issues) (GitHub issues)

## For AI Agents

This repo includes configuration files for AI coding assistants:

- [AGENTS.md](AGENTS.md) - Top-level agent behavior guidelines
- [CLAUDE.md](CLAUDE.md) - Points Claude Code at `AGENTS.md`
- [AI_AGENT_GUIDELINES.md](AI_AGENT_GUIDELINES.md) - Comprehensive agent workflow rules (test-driven
  development, validation requirements, commit conventions)
