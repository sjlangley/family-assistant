# AI Copilot Guidelines

This document guides both human developers and AI copilots assisting with this repo.

## Goals

- Maintain **multi-user separation**
- Preserve **memory integrity** and privacy
- Follow **Google Python style standards** for backend
- Follow **TypeScript/Node best practices** for frontend
- Keep code **well-structured, modular, and testable**


## Repo Structure

- All apps and modules live in the `apps/` folder
- Backend and frontend can each have their own app directories:
  - `apps/backend/` for FastAPI code
  - `apps/frontend/` for React code
- Shared utilities can go in `apps/shared/`


## Frontend Build & Testing

- **Vite** is used as the build tool for the frontend
- Fast development server and hot reload
- Build for production
- Testing with **Vitest** (integrated with Vite)
- Supports unit and integration tests
- Use `--coverage` flag to check test coverage
- Coverage goal: minimum 80%, prefer 90%
- Use **ESLint + Prettier** for linting and formatting


## AI Copilot Rules

1. **Do not hardcode secrets** (OAuth keys, DB passwords)
2. **Inject memory only for the correct user**
3. **Follow system prompts per user**
4. **Use multi-step reasoning pipelines for tool orchestration**
5. **Generate code that passes lint/format checks before commit**:
 - Python: `pyproject.toml` + `black` + `isort` + `pylint`
 - TypeScript: ESLint + Prettier


## Commit & PR Guidelines

- All commits must **pass formatting, linting, and tests**
- Use **conventional commit syntax** (e.g., `feat:`, `fix:`, `chore:`, `test:`)
- Each PR must include:
- **Unit tests and integration tests**
- Verification of **per-user memory isolation**
- Reproducibility checks for multi-modal outputs (text, image, audio, video)


## Test Coverage

- Minimum test coverage: **80%**
- Preferred coverage: **90%+**
- Use coverage tools:
- Python: `pytest --cov`
- TypeScript: `jest --coverage`


## Coding Style

### Python (Backends)

- Google Python Style Guide
- Use `pyproject.toml` for configuration: formatting, linting, testing
- Type annotations required where possible
- Docstrings for all public classes/functions

### TypeScript/Node (Frontend)

- ESLint + Prettier configuration
- Strict typing enabled
- Modular React components
- Clear separation of API layer, UI, and state management


## Key Principles for AI Copilot

- Never bypass lint/format checks
- Always reference **apps/** directory for new modules
- Maintain **modular design** for multi-modal tools and memory injection
- Ensure **multi-user memory separation** in every feature
- Follow **conventional commits** and PR workflow
