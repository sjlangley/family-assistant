# Prompt Token Compression Implementation Plan

## Summary

Implement prompt budgeting and token compression in the backend conversation
path, centered on
`apps/assistant-backend/src/assistant/services/context_assembly.py`.

The goal is to reduce prompt waste, lower truncation frequency, and create a
stable foundation for future model presets and attachment-aware prompting. The
first version should remain backend-only, preserve the current product API, and
use deterministic local token estimation to drive adaptive context selection.

## Product Intent

The current system already has the right architectural pieces:

- canonical transcript and memory in Postgres
- bounded context assembly
- streaming with truthful `finish_reason`
- trust metadata and tool annotations

What is missing is a smarter way to decide how much context to send. Today, the
backend uses fixed limits for:

- recent turns
- durable fact count
- fact text length
- summary text length

That was a good first version, but it is not robust once conversations get
longer, summaries get denser, or future features like presets and attachments
increase prompt pressure.

This project should make context assembly budget-aware instead of count-aware.

## Decisions Locked In

### Scope

- Backend only in v1.
- No user-facing UI changes.
- No primary API contract changes for chat or conversation routes.
- No adoption of LangChain or similar orchestration frameworks.
- No dependency on exact provider-side token counts in v1.

### Library Choice

- Preferred long-term library: tokenizers (the core of transformers) for
  model-aware tokenization and future chat-template-aware counting.
- Acceptable v1 fallback: a lightweight local estimator with a swappable
  interface.
- Do not adopt `tiktoken` as the core long-term counter unless the product
  standardizes on OpenAI tokenization semantics.
- Do not add `LangChain`; borrow patterns only.
- Do not make `Selective Context` the default implementation. It can be
  revisited later as an experimental reducer behind an interface once the
  rule-based budgeter is in place.

### Counting Strategy

- Introduce a `PromptTokenEstimator` interface.
- First implementation may be heuristic if needed for speed of delivery.
- Design the interface so a later `TokenizersPromptTokenEstimator` can replace
  it without changing compression logic.
- All compression decisions must depend only on the estimator interface, not a
  specific library.

### Compression Policy

Use this order whenever the candidate prompt is over budget:

1. Drop weakest durable facts.
2. Shrink older transcript turns while preserving the newest exchange.
3. Compress summary to a smaller emergency budget.
4. Further truncate fact text if still needed.
5. Fall back to the minimum viable prompt:
   current user message + newest exchange + smallest viable memory block.

Never drop the current user message.
Never silently produce an invalid chat message list.
Never reorder preserved transcript turns.

### Context Priorities

Priority order is fixed for v1:

1. New user message
2. Newest exchange:
   the most recent assistant turn, any associated tool calls/results, and the
   immediately preceding user turn.
3. Saved summary
4. Relevant durable facts
5. Older recent turns
6. Weakly relevant overflow facts

### Observability

- Compression decisions must be explainable in logs and service metadata.
- No raw full-prompt logging.
- No sensitive content dumping beyond existing acceptable debug boundaries.

## Architecture Changes

### New Internal Concepts

Add these backend concepts:

- `PromptSection`
  Represents one candidate context section before final rendering.
  Fields:
  - `kind`
  - `content`
  - `estimated_tokens`
  - `priority`
  - `required`
  - `source_ids`
  - `compression_state`

- `PromptBudget`
  Configuration and active budget values.
  Fields:
  - `target_tokens`
  - `hard_max_tokens`
  - `summary_soft_max`
  - `summary_emergency_max`
  - `facts_soft_max`
  - `recent_turns_soft_max`

- `PromptCompressionResult`
  Returned alongside final messages from context assembly.
  Fields:
  - `messages`
  - `estimated_total_tokens`
  - `estimated_tokens_by_section`
  - `included_summary`
  - `included_recent_turn_count`
  - `included_fact_ids`
  - `dropped_fact_ids`
  - `compression_actions`
  - `selection_method`

- `PromptTokenEstimator`
  Interface with methods to:
  - estimate plain text tokens
  - estimate message-list tokens
  - optionally estimate section tokens

### Context Assembly Flow

Refactor `ContextAssemblyService` into this pipeline:

1. Load canonical inputs from Postgres and Chroma-backed ranking exactly as
   today.
2. Build candidate prompt sections rather than final messages immediately.
3. Estimate section and total token cost.
4. Apply compression policy until under target budget or minimum viable shape
   is reached.
5. Render compressed sections into final OpenAI-style messages.
6. Return messages plus compression metadata.

### Settings

Add backend settings for prompt budgeting.

Recommended initial env vars:

- `PROMPT_TARGET_TOKENS`
- `PROMPT_HARD_MAX_TOKENS`
- `PROMPT_SUMMARY_SOFT_MAX_TOKENS`
- `PROMPT_SUMMARY_EMERGENCY_MAX_TOKENS`
- `PROMPT_FACTS_SOFT_MAX_TOKENS`
- `PROMPT_RECENT_TURNS_SOFT_MAX_TOKENS`

Defaults should be conservative and tuned for current Qwen usage, but still
independent of `LLM_MAX_TOKENS`.

## Behavioral Spec

### Under Budget

If candidate context is under budget:

- output should be materially unchanged from current behavior
- only metadata and logging differ

### Over Budget With Many Facts

If the prompt exceeds budget mainly because of durable facts:

- trim lowest-priority facts first
- preserve fact ordering among retained facts
- do not trim transcript before exhausting removable facts

### Over Budget With Long Transcript

If still over budget after fact trimming:

- preserve the newest exchange
- remove older retained transcript turns from oldest to newest
- keep summary if present before dropping the newest exchange

### Over Budget With Large Summary

If still over budget:

- shrink summary to emergency max
- preserve summary presence if possible rather than removing it immediately

### Extreme Pressure

If prompt still exceeds budget after all normal steps:

- keep current user message
- keep newest exchange if available
- keep minimal summary or fact block if one still fits
- emit explicit compression actions showing final fallback was used

## PR Breakdown

### PR 1: Budget Types And Estimator Interface

**Purpose**
Create the token-budget foundation without changing runtime behavior.

**Changes**

- Add `PromptBudget`, `PromptSection`, `PromptCompressionResult`, and
  `PromptTokenEstimator` abstractions.
- Add a default estimator implementation.
- Add env-backed prompt budget settings and wire them into backend settings
  loading.
- Thread token metadata through context assembly without changing selection
  behavior.

**Reviewable outcome**

- New types and tests are in place.
- Budget configuration is available for later compression PRs.
- Existing context assembly behavior is unchanged.
- Metadata is computed and available internally.

**Tests**

- estimator returns deterministic counts
- section counts sum to total
- settings load correctly and apply configured budget values
- current assembly tests still pass unchanged

### PR 2: Section-Based Context Assembly Refactor

**Purpose**
Convert current message construction into section construction while preserving
output parity.

**Changes**

- Replace direct `_build_message_list` assembly with:
  - candidate section creation
  - final render step
- Preserve current ordering and current effective behavior while sourcing budget
  thresholds from configured settings instead of local constants where
  applicable.

**Reviewable outcome**

- Refactor only, no product behavior change.
- Future compression logic has a clean insertion point.

**Tests**

- parity tests for:
  - no summary
  - summary present
  - facts present
  - new conversation

### PR 3: Fact Compression

**Purpose**
Introduce the first small behavior change.

**Changes**

- If over budget, drop weakest facts before touching summary or transcript.
- Record `dropped_fact_ids` and compression actions.

**Reviewable outcome**

- Easy to reason about.
- Small blast radius.
- Directly useful even before transcript compression lands.

**Tests**

- failing test first: fact-heavy prompt trims facts first
- retained facts preserve ranking order
- transcript remains unchanged while removable facts still exist

### PR 4: Adaptive Transcript Compression

**Purpose**
Make recent-turn selection budget-aware.

**Changes**

- Preserve newest exchange.
- Remove older turns oldest-first once facts are exhausted.
- Keep role order stable.

**Reviewable outcome**

- Core adaptive selection behavior arrives in one focused PR.

**Tests**

- failing test first: newest exchange always retained
- no-summary conversations shrink transcript correctly
- summary-present conversations still prefer summary over older turns

### PR 5: Summary Emergency Compression And Minimum Viable Fallback

**Purpose**
Handle extreme prompt pressure safely.

**Changes**

- Add emergency summary truncation.
- Add final fallback rules.
- Ensure compressed result always produces a valid final message list.

**Reviewable outcome**

- Edge-case behavior becomes explicit and safe.

**Tests**

- huge summary compresses under pressure
- pathological oversized context still yields valid prompt
- current user message is never dropped

### PR 6: Settings, Logging, And Operator Visibility

**Purpose**
Make the feature inspectable once compression behavior is complete.

**Changes**

- Add structured logs for token usage and compression actions without logging
  raw full-prompt or raw message content.
- Optionally add a debug-only inspection seam if logs are insufficient, but
  keep it limited to redacted or summarized prompt-shaping metadata only
  (never raw message content), gate it behind an explicit debug flag, and
  disable it by default in production.

**Reviewable outcome**

- Operators can reason about prompt shaping without reading code.

**Tests**

- logs and metadata contain expected compression fields
- no sensitive full-prompt leakage

## Test Plan

### Main Unit-Test Seam

Use `apps/assistant-backend/tests/services/test_context_assembly_service.py` as
the primary seam for behavior tests.

### Integration Coverage

Add narrow integration tests only where needed to prove wiring from
conversation service to LLM request construction.

### Required New Scenarios

- under-budget prompt preserves current shape
- fact-heavy prompt trims facts before transcript
- transcript-heavy prompt preserves newest exchange
- summary-present prompt prefers summary over older transcript turns
- extreme prompt pressure triggers minimum viable fallback
- metadata accurately reflects included and dropped content
- token estimates are deterministic for the same inputs

### Validation Per Repo Rules

Before any commit for this work:

- `ruff format src/ tests/`
- `ruff check src/ tests/`
- `pyrefly check src/`
- `pytest -v`

## Risks And Mitigations

- Risk: token estimation drift from provider reality
  Mitigation:
  hide counting behind `PromptTokenEstimator` and keep compression policy
  estimator-agnostic

- Risk: over-compression removes needed context
  Mitigation:
  encode preservation rules in tests, especially newest exchange and current
  user message

- Risk: refactor and behavior changes getting mixed together
  Mitigation:
  keep refactor-only PRs separate from compression-behavior PRs

- Risk: future model presets needing different counting
  Mitigation:
  estimator and budget objects are preset-ready even if presets are not
  implemented yet

## Follow-On Value

After this project lands:

- model presets become safer because each preset can supply its own estimator
  and budget profile
- attachment ingestion has a clear place to compete for prompt budget
- `Continue` and truncation frequency should decrease under normal use
- prompt shaping becomes observable instead of implicit

## Assumptions

- We are not changing product surface area in this effort.
- We want a clean internal foundation, not a one-off heuristic patch.
- `tokenizers` is the preferred long-term counting backend, but the
  interface comes first.
- This plan should be implemented with TDD and one small reviewable PR at a
  time.
