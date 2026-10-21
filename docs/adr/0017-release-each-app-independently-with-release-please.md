---
status: accepted
date: "2026-04-17"
supersedes: []
superseded_by:
---

# 0017. Release each app independently with release-please

## Context

Recorded retrospectively. The decision was made in #92 (commit `8491108`, 2026-04-17), "Set up
manifest-driven Release Please for backend/UI and compose version metadata".

The backend and the frontend ship as separate Docker images (ADR 0002). `release-please-config.json`
declares two packages, `apps/assistant-backend` (release type `python`) and `apps/assistant-ui`
(release type `node`), with `separate-pull-requests` and `include-component-in-tag` set, so each app
gets its own release pull request, version, tag and `CHANGELOG.md`. `.release-please-manifest.json`
holds the current versions. An `extra-files` entry per app keeps the matching version variable in
`docker-compose.yml` in step.

`.github/workflows/release-please.yml` runs `googleapis/release-please-action` on every push to
`main`. release-please reads Conventional Commits to choose the next version and write the
changelog.

## Considered options

### release-please, with one release per app

No alternatives were formally weighed at the time.

- Good: the changelogs are written automatically, and each app has its own version because the apps
  ship as separate images.
- Bad: the release notes and versions depend on the commit messages.

## Decision

We will use release-please to version and release each app independently, driven by Conventional
Commits.

We will keep the app versions in the release manifest and in `docker-compose.yml`, and let
release-please update them.

## Consequences

- Good: no manual changelog or version edits, and a change to one app does not bump the other.
- Bad: commit types decide the release. `feat`, `fix`, `perf`, `revert` and breaking changes cut a
  release for either app, and `deps` and `docs` also do for the Python backend, so tooling changes
  use types its changelog hides, such as `ci`, `chore` or `style`.
- Bad: with squash merges, the pull request title becomes the commit message, so the title has to be
  a valid Conventional Commit.
- Bad: release-please owns `apps/*/CHANGELOG.md` and rewrites it in its own format, so formatters
  exclude those files (see #151).
