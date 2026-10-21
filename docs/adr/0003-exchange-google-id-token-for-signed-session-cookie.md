---
status: accepted
date: "2026-03-09"
supersedes: []
superseded_by:
---

# 0003. Exchange a Google ID token for a signed session cookie

## Context

Recorded retrospectively. The decision was made in #4 (2026-03-09).

The assistant is used by family members who sign in with Google. The frontend obtains a Google ID
token and sends it once as a bearer token to `POST /auth/login`
(`apps/assistant-backend/src/assistant/routers/auth.py`). The backend verifies the token against
Google with the configured client ID (`security/google_bearer_token.py`) and can restrict sign-in to
listed hosted domains. It then stores the user's `email`, `userid` and `name` in a Starlette
`SessionMiddleware` cookie (`app.py`).

The cookie is named `family-assistant-session`, is valid for 7 days, uses `same_site='lax'`, and is
`https_only` in the production and staging environments. Later requests are authenticated by reading
that session (`security/session_auth.py`), not by re-verifying a token. For local development,
`AUTH_DISABLED` bypasses token verification, and only in the `local` and `development` environments.

## Considered options

### Verify the Google ID token once, then use a signed session cookie

No alternatives were weighed here. The pattern was carried over from an earlier project.

- Good: the author already had the pattern, and Google is only contacted at sign-in.
- Bad: the session lives in a cookie signed with `SESSION_SECRET_KEY`, so there is no server-side
  session store and a session cannot be revoked before it expires.

## Decision

We will verify a Google ID token once at `POST /auth/login` and then identify the user by a signed
session cookie.

We will allow token verification to be bypassed with `AUTH_DISABLED` only in the local and
development environments.

## Consequences

- Good: API requests do not call Google, and the user identity (`userid`, the Google `sub`) is
  available on every request for the per-user isolation in ADR 0004.
- Good: the cookie settings (`lax`, HTTPS-only in production and staging) are in one place in
  `app.py`.
- Bad: the cookie holds the session data itself, so the only way to end a session early is to rotate
  `SESSION_SECRET_KEY`, which signs out everyone.
- Bad: the choice was not evaluated against alternatives, so its fit for this project is untested.
