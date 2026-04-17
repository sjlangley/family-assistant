# assistant-backend

Backend service for the Family Assistant application.

Provides authenticated REST APIs for user management, conversation history, and LLM chat
completions. Uses Google OAuth 2.0 for authentication, PostgreSQL for persistent storage,
Chroma for retrieval support, and an external OpenAI-compatible LLM server for inference.

---

## Implemented Features

- **Google OAuth 2.0 authentication** — verifies Google ID tokens and manages server-side sessions
- **Session-backed auth** — cookie-based sessions via Starlette `SessionMiddleware`
- **User API** — retrieves the currently authenticated user
- **Shared LLM completion seam** — one typed path powers both `/api/v1/chat/completions` and conversation replies
- **Conversation orchestration** — creates conversations, appends messages, and persists terminal assistant failures instead of dropping outcomes
- **Bounded context assembly** — conversation replies use recent turns, one latest saved summary, and active per-user durable facts from PostgreSQL
- **Canonical memory storage** — conversation summaries and durable facts are stored in Postgres and mirrored into Chroma only for retrieval support
- **Tool orchestration** — `ToolFactory` and `ToolService` expose an explicit allowlist with a bounded model-native tool loop
- **Built-in tools** — `get_current_time` is the deterministic validation tool, and the shipped research path is `web_search` plus `web_fetch`
- **Fetch safety** — `web_fetch` only allows public `http` and `https` targets, re-validates redirects, and blocks localhost and private-network destinations
- **Persisted trust annotations** — assistant rows can store sources, tools, memory hits, memory saves, and terminal failure metadata
- **Background extraction** — successful replies schedule summary and durable-fact extraction after the response is persisted
- **Health check endpoint**
- **CORS middleware** — configurable allowed origins

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
* A running OpenAI-compatible LLM server such as Ollama (see `apps/llm-server/README.md`)

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
| `LLM_BASE_URL` | Base URL of the local OpenAI-compatible LLM server | Yes |
| `LLM_MODEL` | Model name to pass to the LLM API | No (default in Docker Compose: `qwen2.5:7b`) |
| `LLM_TIMEOUT_SECONDS` | Request timeout for LLM calls | No (default: `120`) |
| `DATABASE_URL` | Full SQLAlchemy database URL | No (uses TCP params below) |
| `DATABASE_HOST` | PostgreSQL host | No (default: `localhost`) |
| `DATABASE_PORT` | PostgreSQL port | No (default: `5432`) |
| `DATABASE_NAME` | PostgreSQL database name | No (default: `conversations`) |
| `DATABASE_USER` | PostgreSQL username | No (default: `nobody`) |
| `DATABASE_PASSWORD` | PostgreSQL password | No |
| `CHROMA_HOST` | Chroma host name | Yes |
| `CHROMA_PORT` | Chroma port | No (default: `8100`) |
| `CHROMA_COLLECTION_NAME` | Chroma collection for mirrored memory docs | No (default: `assistant_memory`) |
| `CLIENT_ORIGINS` | Comma-separated allowed CORS origins | No |
| `ALLOWED_HOSTED_DOMAINS` | Optional Google Workspace hosted domains allowlist | No |
| `AUTH_DISABLED` | Disable auth for local development | No (default: `false`) |
| `ENVIRONMENT` | `development`, `staging`, or `production` | No (default: `production`) |
| `LOG_LEVEL` | Logging level | No (default: `INFO`) |

Tool-specific defaults such as search result caps and fetch timeouts are currently code-local inside the tool implementations.

### Start the development server

```bash
uvicorn assistant.app:app --reload --port 8080
```

The server will run at:

```
http://localhost:8080
```

## Database Migrations

Use Alembic for schema changes on existing databases:

```bash
alembic upgrade head
```

The app still calls `SQLModel.metadata.create_all()` during startup so an empty local database can bootstrap the base tables. Treat that as local convenience, not the schema migration strategy for evolving installs.

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

## Validation

Run the backend validation suite from `apps/assistant-backend`:

```bash
ruff format src/ tests/
ruff check src/ tests/
ruff format --check src/ tests/
pyrefly check src/
pytest -v
```

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
