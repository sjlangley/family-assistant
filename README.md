# Family AI Assistant

A self-hosted, multi-user AI assistant designed for household use.
Supports **text chat with a local LLM**, **persistent conversation history**, **background summary and durable-fact memory**, **bounded web research tools**, and **per-user authentication**.

---

## Features

- **Multi-user support**
  Each family member authenticates with their Google account and has their own conversation history.
- **Conversation management**
  Persistent conversations stored in PostgreSQL — create new chats, resume old ones, and browse history.
- **Conversation memory**
  Successful replies now trigger background memory extraction that refreshes a per-conversation summary and saves per-user durable facts in PostgreSQL for later turns.
- **LLM chat**
  Text chat powered by a local OpenAI-compatible LLM runtime, with Docker Compose now defaulting to Ollama.
- **Bounded web research**
  Conversation replies can now use a native tool loop with `web_search` for discovery and `web_fetch` for grounded page reads.
- **Authentication & security**
  Google OAuth 2.0 with server-side session cookies. Per-user data isolation enforced at the API layer.

---

## Tech Stack

- **Backend:** Python 3.13+ / FastAPI
- **Frontend:** TypeScript / React 18 / Vite
- **LLM Runtime:** Ollama by default in Docker Compose, or another local OpenAI-compatible server
- **Database:** PostgreSQL 16 (SQLModel / SQLAlchemy async)
- **Authentication:** Google OAuth 2.0 (server-side sessions)
- **Linting & Formatting:** Ruff + Pyrefly (backend), ESLint + Prettier (frontend)

---

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
3. Install Node.js 22+ dependencies for the frontend
4. Configure Google OAuth credentials
5. Start PostgreSQL, the LLM server, the backend, and the frontend

See individual READMEs for detailed instructions:

- [Backend Setup](apps/assistant-backend/README.md)
- [Frontend Setup](apps/assistant-ui/README.md)
- [LLM Server Setup](apps/llm-server/README.md)

## Project Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Implementation Plan](docs/IMPLEMENTATION_PLAN.md)
- [Design System](DESIGN.md)
- [Roadmap / TODOs](TODOS.md)
