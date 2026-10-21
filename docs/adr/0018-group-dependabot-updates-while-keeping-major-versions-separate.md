---
status: accepted
date: "2026-10-21"
supersedes: []
superseded_by:
---

# 0018. Group Dependabot updates while keeping major versions separate

## Context

Dependabot was configured with no groups, so each ecosystem opened one pull request per dependency
every month (#143). Each needed its own CI run, review and merge. #144 added groups to
`.github/dependabot.yml`, and its review settled the cases below.

Dependabot counts a bump from `0.x` to `0.(x+1)` as a minor update. Ruff and pyrefly are pre-1.0
tools that add lint rules and type checks in minor releases, so a minor bump can fail the lint job.
A failing check on a group blocks every other update in it. After #144, #150 grouped 18 Python
updates, including SQLModel 0.0.48 and SQLAlchemy 2.1, and pyrefly failed on it until #158 fixed the
type errors.

The stale `/apps/worker` entries in `dependabot.yml` are out of scope here and tracked in #141.

## Considered options

### One pull request per dependency

This was the setup before #144.

- Good: a failing update blocks nothing else.
- Bad: many small pull requests, each needing its own CI run, review and merge.

### Group every update type, including majors

This was the reading of "one group for all actions" in #143. The #144 review rejected it.

- Good: fewest pull requests.
- Bad: a breaking major upgrade, such as `actions/checkout` 6 to 7, cannot be reviewed, merged or
  reverted on its own.

### Group minor and patch updates only, and leave majors ungrouped

- Good: routine updates arrive together, and breaking upgrades are reviewed one at a time.
- Bad: a breaking minor release in a group blocks the other updates in it.

## Decision

We will group minor and patch updates, and leave major updates as individual pull requests. The
groups are `pip-minor-patch` for the backend, `npm-production` and `npm-development` for the
frontend, and `github-actions`.

We will exclude `ruff` and `pyrefly` from `pip-minor-patch`, so they arrive as individual pull
requests.

We will leave Docker base images ungrouped, because they update rarely.

## Consequences

- Good: far fewer monthly pull requests, with majors still reviewed one at a time.
- Good: a new lint rule from ruff or pyrefly no longer blocks the other Python updates.
- Bad: other `0.x` packages stay in the group, for example `fastapi`, `uvicorn` and `sqlmodel`. A
  breaking minor release in one of them fails the grouped pull request, which was accepted as a
  visible CI failure. #150 showed this, and #158 fixed the type errors it exposed.
- Bad: the grouping can only be exercised by GitHub's Dependabot service, not locally. The
  `check-dependabot` pre-commit hook validates the file against its schema only.
- One exception followed: #165 added an `eslint` group that includes majors, so ESLint and its
  plugins land together. #149 (ESLint 9 to 10 alone) failed because a plugin's peer range did not
  yet accept the new major.
