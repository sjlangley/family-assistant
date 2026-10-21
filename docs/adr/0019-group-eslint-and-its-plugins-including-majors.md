---
status: accepted
date: "2026-10-21"
supersedes: []
superseded_by:
---

# 0019. Group ESLint and its plugins, including majors

## Context

[ADR 0018](0018-group-dependabot-updates-while-keeping-major-versions-separate.md) keeps major
updates as individual pull requests. Two Dependabot pull requests then showed a limit of that rule
for packages that depend on each other. #149 (ESLint 9 to 10 alone) and #50 (`@eslint/js` alone)
both failed `npm ci` with `ERESOLVE`, because `eslint-plugin-react-hooks` 7.0.1 did not accept
ESLint 10 in its peer range. Neither could pass on its own.

PR #165 upgraded `eslint`, `@eslint/js`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`
and `typescript-eslint` together, and in the same change added the `eslint` group to
`.github/dependabot.yml` so that future ESLint majors arrive with their plugins in one pull request.
This ADR records that grouping. It adds an exception to ADR 0018 and does not replace it.

## Considered options

### Keep ESLint majors ungrouped, as ADR 0018 decides

- Good: one major upgrade at a time, so each can be reviewed, merged or reverted alone.
- Bad: a package whose peer range is tied to another package can never pass alone, as #149 and #50
  showed.

### Add an `eslint` group that includes majors, listed before `npm-development`

- Good: ESLint and its plugins land in one pull request, so peer ranges are resolved together.
- Bad: if a plugin has not yet widened its peer range, the grouped pull request still fails.
- Bad: the grouped pull request is larger than a single-package one.

## Decision

We will group `eslint`, `@eslint/*`, `eslint-plugin-*`, `typescript-eslint` and
`@typescript-eslint/*` in an `eslint` Dependabot group that includes major, minor and patch updates.

We will list the `eslint` group before `npm-development` in `.github/dependabot.yml`, because
Dependabot assigns a dependency to the first group that matches.

## Consequences

- Good: an ESLint major arrives together with the plugins whose peer ranges it needs, so the pull
  request can pass `npm ci`.
- Bad: a plugin that has not yet widened its peer range still fails the grouped pull request, and
  the whole group waits.
- Bad: ESLint majors are no longer reviewed on their own, and a grouped pull request is larger.
- Bad: the grouping can only be exercised by GitHub's Dependabot service, not locally. The
  `check-dependabot` pre-commit hook validates the file against its schema only.
- ADR 0018 still holds for every other group: majors outside the `eslint` group stay individual pull
  requests.
