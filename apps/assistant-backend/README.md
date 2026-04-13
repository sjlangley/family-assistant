# assistant-backend

Backend service for the Family Assistant application.

Provides authenticated REST APIs for user management, conversation history, and LLM chat
completions. Uses Google OAuth 2.0 for authentication, PostgreSQL for persistent storage,
and an external llama.cpp server for LLM inference.

---

## Implemented Features

* **Google OAuth 2.0 authentication** — verifies Google ID tokens and manages server-side sessions
* **Session management** — cookie-based sessions via Starlette `SessionMiddleware`
* **User API** — retrieve the currently authenticated user
* **LLM chat completions** — proxies chat requests to a local llama.cpp server
* **Shared LLM completion seam** — one typed backend path now powers both the direct chat endpoint and conversation replies, with common response validation and error handling
* **Bounded conversation context assembly** — existing conversation replies now use the latest saved summary, active per-user durable facts, and a capped recent-turn window instead of blindly resending the full transcript
* **Conversation management** — create conversations, add messages, list and retrieve history
* **Health check endpoint**
* **PostgreSQL storage** — async SQLModel / SQLAlchemy with automatic schema creation
* **CORS middleware** — configurable allowed origins

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/login` | Authenticate with a Google ID token (Bearer); sets session cookie |
| `POST` | `/auth/logout` | Clear the session cookie |
| `GET` | `/user/current` | Return the currently authenticated user |
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/chat/completions` | Send a chat message and receive an LLM response |
| `GET` | `/api/v1/conversations` | List all conversations for the current user |
| `POST` | `/api/v1/conversations/with-message` | Create a new conversation with an initial message |
| `GET` | `/api/v1/conversations/{id}/messages` | Get all messages in a conversation |
| `POST` | `/api/v1/conversations/{id}/messages` | Add a message to an existing conversation |

---

## Running the Server

### Requirements

* Python 3.13+
* PostgreSQL 16 (or SQLite for tests via `DATABASE_URL=sqlite+aiosqlite:///:memory:`)
* A running llama.cpp server (see `apps/llm-server/README.md`)

Install dependencies:

```bash
pip install -e ".[dev]"
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Description | Required |
|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth 2.0 client ID | Yes |
| `SESSION_SECRET_KEY` | Secret for signing session cookies | Yes |
| `LLM_BASE_URL` | Base URL of the llama.cpp server | Yes |
| `LLM_MODEL` | Model name to pass to the LLM API | No (default: `gpt-4`) |
| `LLM_TIMEOUT_SECONDS` | Request timeout for LLM calls | No (default: `120`) |
| `DATABASE_URL` | Full SQLAlchemy database URL | No (uses TCP params below) |
| `DATABASE_HOST` | PostgreSQL host | No (default: `localhost`) |
| `DATABASE_PORT` | PostgreSQL port | No (default: `5432`) |
| `DATABASE_NAME` | PostgreSQL database name | No (default: `conversations`) |
| `DATABASE_USER` | PostgreSQL username | No (default: `nobody`) |
| `DATABASE_PASSWORD` | PostgreSQL password | No |
| `CLIENT_ORIGINS` | Comma-separated allowed CORS origins | No |
| `AUTH_DISABLED` | Disable auth for local development | No (default: `false`) |
| `ENVIRONMENT` | `development`, `staging`, or `production` | No (default: `production`) |
| `LOG_LEVEL` | Logging level | No (default: `INFO`) |

### Start the development server

```bash
uvicorn assistant.app:app --reload --port 8080
```

The server will run at:

```
http://localhost:8080
```

---

## Testing

Tests are written using **pytest** with `pytest-asyncio`.

Run tests:

```bash
pytest
```

Run with coverage report:

```bash
pytest --cov --cov-report=term
```

Coverage target: **90%** (enforced in CI).

---

## Linting and Static Analysis

Code quality is enforced with:

* **Ruff** — linting and formatting
* **Pyrefly** — static type analysis

Run Ruff:

```bash
ruff check src/ tests/
ruff format src/ tests/
```

Run Pyrefly:

```bash
pyrefly check src/
```

All commits must pass formatting, linting, tests, and static analysis.

---

## Commit Standards

Commits follow **Conventional Commits**.

Examples:

```
feat: add authentication middleware
fix: correct health endpoint
test: add health endpoint tests
chore: update dependencies
```

---

## License

Apache 2.0
