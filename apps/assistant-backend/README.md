

# assistant-backend

Backend service for a self-hosted AI assistant.

This service will eventually provide the backend APIs, orchestration, and model integration for
a multi-user household AI assistant. The long-term goal is to support authenticated users,
personal memory, and integrations with local AI models.

The project is currently in an **initial scaffold stage**.

---

## Current Status

Implemented so far:

* FastAPI application scaffold
* Health check endpoint
* Python project configuration via `pyproject.toml`
* Formatting, linting, and static analysis tooling

No authentication, AI models, or memory systems have been implemented yet.

---

## Running the Server

Start the development server:

```bash
uvicorn assistant.app:app --reload
```

The server will run at:

```
http://localhost:8000
```

Health check endpoint:

```
GET /health
```

---

## Development

### Requirements

* Python 3.13+

Dependencies and tooling are configured via `pyproject.toml`.

---

## Testing

Tests are written using **pytest**.

Run tests:

```bash
pytest
```

Coverage targets:

* Minimum: **80%**
* Preferred: **90%**

---

## Linting and Static Analysis

Code quality is enforced with:

* **Ruff** — linting and formatting
* **Pyrefly** — static type analysis

Run Ruff:

```bash
ruff check .
ruff format .
```

Run Pyrefly:

```bash
pyrefly
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
