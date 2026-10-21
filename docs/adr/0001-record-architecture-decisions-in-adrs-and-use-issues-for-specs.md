---
status: accepted
date: "2026-10-21"
supersedes: []
superseded_by:
---

# 0001. Record architecture decisions in ADRs and use issues for specs

## Context

Until now the repository has kept product requirement documents and plans in `docs/`
(`STREAMING_RESPONSES_PRD.md`, `MODEL_PRESETS_PRD.md`, `PROMPT_TOKEN_REDUCTION_PLAN.md`,
`ATTACHMENT_INGESTION_IMPLEMENTATION_PLAN.md`), a roadmap in `TODOS.md`, and an overview in
`docs/ARCHITECTURE.md`. A PRD mixes the specification, the options weighed, the rollout plan and the
decision in one file. Once the work ships, the PRD becomes an implementation record: the streaming
PRD says as much in its Status section. Several decisions in the code, such as the choice of Chroma,
Alembic or release-please, have no record of why they were made.

Agents and people working on the repository need to find the decisions that bind them without
reading every plan.

## Considered options

### Keep PRD and plan documents in `docs/`

This is the status quo.

- Good: nothing to change; the existing documents already hold some of the reasoning.
- Bad: decisions are buried inside documents that describe work in progress, so a reader cannot tell
  which parts are still in force.

### ADRs in `docs/adr/` for decisions, GitHub issues for specs, plans and roadmap items

- Good: one file per decision with a status, so a decision can be superseded without rewriting
  history. A script can check the format.
- Bad: specs and plans no longer live in the repository, and the existing documents have to be moved
  or removed in a later change.

## Decision

We will record each architecture decision as an ADR in `docs/adr/`, following the template and
status rules checked by the `adr-check` script.

We will keep specifications, plans and roadmap items in GitHub issues, and stop adding PRDs, plans
and `TODOS.md` entries to the repository.

We will keep `DESIGN.md` as the design system specification, and keep the READMEs and `DOCKER.md` as
how-to documents.

We will run `adr-check` as a pre-commit hook and in CI to enforce the ADR format.

## Consequences

- Good: a reader can find what is in force by status, and a changed decision leaves a visible trail
  through `supersedes` and `superseded_by`.
- Good: ADRs 0002 to 0017 record the decisions already visible in the code, so later changes can be
  checked against them.
- Bad: the existing PRDs, plans, `TODOS.md` and `docs/ARCHITECTURE.md` stay in the repository until
  a follow-up change moves their content into issues. Until then there are two places to look.
- Bad: accepted ADRs cannot be edited, so changing a decision costs a new ADR.
- Bad: contributors have to learn the ADR format, and `adr-check` fails the build when it is wrong.
