---
status: accepted
date: "2026-03-06"
supersedes: []
superseded_by:
---

# 0002. Separate FastAPI backend and React Vite frontend in one repository

## Context

Recorded retrospectively. The decision was made when the repository was scaffolded, in PR #1 for the
backend (2026-03-06) and PR #2 for the frontend (opened 2026-03-06, merged 2026-03-07).

The repository holds two applications under `apps/`:

- `apps/assistant-backend`, a Python FastAPI service with its own `Dockerfile` and `pyproject.toml`.
- `apps/assistant-ui`, a React, TypeScript, Vite and Tailwind single-page app with its own
  `Dockerfile` and `package.json`.

`apps/llm-server` holds only setup instructions for the local model runtime. The root
`docker-compose.yml` builds and runs the two apps together with their supporting services. The
backend allows the browser origin through CORS and uses a session cookie (see ADR 0003).

## Considered options

### FastAPI backend and React with Vite frontend, as two apps in one repository

No alternatives were formally weighed at the time. A full-stack framework such as Next.js was not
seriously considered.

- Good: FastAPI and React were the stacks the author already knew.
- Bad: two toolchains, two Docker images and two test suites to keep green.

## Decision

We will build the backend as a FastAPI service in `apps/assistant-backend` and the frontend as a
React and Vite single-page app in `apps/assistant-ui`.

We will keep both in this repository, each with its own build, dependencies and image.

## Consequences

- Good: the author works in familiar stacks, and each app can be built, tested and deployed
  separately.
- Good: the apps can be versioned separately, which ADR 0017 relies on.
- Bad: the frontend's API types in `apps/assistant-ui/src/types/api.ts` are written by hand, so a
  change to a backend response needs a matching change there.
- Bad: CI, linting and dependency updates run once per ecosystem.
