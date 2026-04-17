# Family AI Assistant

A self-hosted, multi-user household assistant built around trustworthy text chat.
The current shipped core combines a local OpenAI-compatible LLM, canonical Postgres-backed conversation memory, a bounded web research path, and persisted trust metadata in the desktop chat UI.

## What Exists Today

- **Multi-user conversations**
  Google-authenticated users get isolated conversation history and memory at the API and storage layers.
- **Canonical conversation memory**
  Successful replies trigger background extraction that refreshes one latest summary per conversation and per-user durable facts in PostgreSQL.
- **Bounded research tools**
  Conversation replies can use an explicit allowlist of tools, with `web_search` for source discovery and `web_fetch` for grounded page reads.
- **Persisted trust metadata**
  Assistant messages store compact `annotations` so reloads preserve tool usage, evidence sources, memory hits, memory saves, and terminal failure context.
- **Desktop trust UI**
  The conversation shell renders an inline trust row plus an evidence panel driven entirely by persisted annotations.
- **Direct chat endpoint**
  The backend also keeps a simpler `/api/v1/chat/completions` path for non-conversation chat requests through the shared LLM completion seam.

## Tech Stack

- **Backend:** Python 3.13+, FastAPI, SQLModel, SQLAlchemy async
- **Frontend:** TypeScript, React 19, Vite
- **LLM runtime:** Ollama by default in Docker Compose, or another local OpenAI-compatible server
- **Storage:** PostgreSQL 16 for canonical data, Chroma for retrieval support
- **Authentication:** Google OAuth 2.0 with server-side sessions
- **Validation:** Ruff + Pyrefly + pytest on the backend, ESLint + Prettier + TypeScript + Vitest on the frontend

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
- [Design System](DESIGN.md)
- [Roadmap / TODOs](TODOS.md)
