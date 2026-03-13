# Family AI Assistant

A self-hosted, multi-user AI assistant designed for household use.
Supports **text chat with a local LLM**, **persistent conversation history**, and **per-user authentication**.

---

## Features

- **Multi-user support**
  Each family member authenticates with their Google account and has their own conversation history.
- **Conversation management**
  Persistent conversations stored in PostgreSQL — create new chats, resume old ones, and browse history.
- **LLM chat**
  Text chat powered by llama.cpp running locally (via Docker or on the host machine).
- **Authentication & security**
  Google OAuth 2.0 with server-side session cookies. Per-user data isolation enforced at the API layer.

---

## Tech Stack

- **Backend:** Python 3.13+ / FastAPI
- **Frontend:** TypeScript / React 18 / Vite
- **LLM Runtime:** llama.cpp (llama-cpp-python server, OpenAI-compatible API)
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
docker compose up --build
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
