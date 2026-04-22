# Prompt Token Compression Implementation Plan

## Summary

Implement prompt budgeting and token compression in the backend conversation
path, centered on
`apps/assistant-backend/src/assistant/services/context_assembly.py`.

The goal is to reduce prompt waste, lower truncation frequency, and create a
stable foundation for future model presets and attachment-aware prompting. This
plan is intentionally backend-only for v1, preserves the current product API,
and is specific enough that an implementing engineer should not need to invent
core behavior, precedence rules, or rollout order.

## Why This Work Comes Next

The current system already has the right architectural primitives:

- canonical transcript and memory in Postgres
- bounded context assembly
- streaming with truthful `finish_reason`
- trust metadata and tool annotations
- a bounded tool loop

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
- No new LLM call for compression or summarization in this project.
- No persistence changes to stored summaries or durable facts in this project.
- No adoption of LangChain or similar orchestration frameworks.
- No dependency on exact provider-side token counts in v1.

### User Experience

- The user should not see a new visible state such as "Compressing context".
- Prompt compression is an internal assembly concern only.
- Under-budget requests should be materially indistinguishable from current
  behavior.

### Library Choice

- Preferred long-term tokenizer surface: Hugging Face tokenizer APIs via
  `transformers`, using the normal tokenizer loading path and the tokenizer
  backend selected by the library.
- Preferred underlying backend for standard models: the Tokenizers-backed
  backend, not a custom Python tokenizer.
- Do not plan around `PythonBackend` as the default implementation. The
  Transformers docs describe `PythonBackend` as the choice for highly
  specialized custom tokenizers that cannot be expressed by the normal backend.
- Acceptable v1 fallback: a lightweight local estimator with a swappable
  interface if the model-aware path would delay shipping.
- Do not adopt `tiktoken` as the core long-term counter unless the product
  standardizes on OpenAI tokenization semantics.
- Do not add `LangChain`; borrow ideas only.
- Do not make `Selective Context` the default implementation. It can be
  revisited later as an experimental reducer behind an interface once the
  rule-based budgeter is in place.

### Token Counting Strategy

- Introduce a `PromptTokenEstimator` interface.
- Prefer counting rendered chat input, not raw text fragments in isolation.
- Prefer model-aware local counting over word count or character count.
- The first shipped implementation may be heuristic if needed for speed of
  delivery, but it must be deterministic and conservative rather than exact.
- "Conservative" means it should slightly overestimate prompt size under normal
  conditions rather than underestimate and risk blowing the real budget.
- The interface must support a later `TransformersPromptTokenEstimator`
  implementation without changing compression logic.
- All compression decisions must depend only on the estimator interface, not a
  specific tokenizer library.

### Compression Policy

Use this order whenever the candidate prompt is over budget:

1. Drop weakest durable facts.
2. Shrink older transcript turns while preserving the newest interaction
   bundle.
3. Compress summary to a smaller emergency budget.
4. Further truncate retained fact text if still needed.
5. Fall back to the minimum viable prompt:
   current user message + newest interaction bundle + smallest viable memory
   block.

Never drop the current user message.
Never silently produce an invalid chat message list.
Never reorder preserved transcript turns.
Never insert an extra LLM summarization pass into the request path.

Fact-text truncation in step 4 is deterministic, not semantic rewriting:

- truncate only facts that survived ranked fact selection
- preserve fact ordering
- shorten each retained fact's text locally to a smaller prompt-time limit
- do not rerank facts during this step
- do not call an LLM to rewrite fact text
- do not persist the shortened fact text back to storage

### Definition Of "Weakest Durable Facts"

"Weakest durable facts" is not an LLM judgment in this project. It is the tail
of the already-ranked fact list produced by the existing retrieval and ranking
pipeline.

For v1:

- Existing conversations:
  use the current `ContextAssemblyService` ranking behavior.
  When recent turns exist, that means relevance-first ordering using the
  current heuristics.
  When recent turns do not support relevance ranking, fall back to recency.
- New conversations:
  use the current Chroma candidate retrieval when available, then reload from
  canonical Postgres rows in ranked order, then fall back to recency if needed.
- Compression trims from the tail of that ranked list.
- This project does not introduce a new semantic reranker or a new LLM-based
  fact scoring step.

### Definition Of "Newest Interaction Bundle"

For v1, the newest preserved interaction bundle is:

- the latest user turn that led to the assistant response being preserved
- the latest assistant response
- any immediately associated tool-call and tool-result messages required to
  make that assistant response intelligible and grounded

This definition replaces the narrower "latest user + latest assistant" rule.
If a tool-assisted final answer exists, compression must preserve the whole
final interaction bundle, not just the visible assistant text.

### Summary Compression

"Compress summary" in this document means local prompt-time shortening of the
already-saved summary text.

It does not mean:

- sending the summary to an LLM for rewriting
- storing a new compressed summary row in Postgres
- mutating the canonical saved summary during request handling
- surfacing a user-visible compression status

V1 summary compression is local, deterministic, and request-scoped only.

How this works in code:

- load the canonical saved summary text from Postgres
- do not ask an LLM to rewrite it
- do not persist a new summary row
- shorten only the copy being assembled into the current prompt
- prefer token-aware truncation using the same tokenizer/counting path used by
  the estimator
- if the model-aware tokenizer path is not yet available in the first
  foundation PR, allow a temporary deterministic fallback that truncates by a
  conservative character budget

Before and after example:

Stored summary in Postgres:

```text
The family previously discussed George Langley's birth year, possible migration
records, conflicting census evidence from 1901 and 1911, Mary Langley's
marriage timing, and whether a probate record from Sussex refers to the same
person. They also reviewed two web sources and noted that one source may be
derivative rather than primary.
```

Normal prompt-time inclusion when under the soft summary budget:

```text
[Conversation summary]:
The family previously discussed George Langley's birth year, possible migration
records, conflicting census evidence from 1901 and 1911, Mary Langley's
marriage timing, and whether a probate record from Sussex refers to the same
person. They also reviewed two web sources and noted that one source may be
derivative rather than primary.
```

Emergency compressed version for this one request only:

```text
[Conversation summary]:
The family previously discussed George Langley's birth year, possible migration
records, conflicting census evidence from 1901 and 1911, Mary Langley's
marriage timing...
```

The important point is that the stored summary does not change. Only the prompt
copy is shortened for the current request.

Illustrative pseudocode:

```python
def shorten_summary_for_prompt(
    summary_text: str,
    *,
    estimator: PromptTokenEstimator,
    emergency_max_tokens: int,
    fallback_max_chars: int = 600,
) -> str:
    """Return a request-local shortened copy of the saved summary."""
    if estimator.estimate_text(summary_text) <= emergency_max_tokens:
        return summary_text

    # Preferred path: token-aware truncation using the same tokenizer family
    # that backs prompt estimation.
    if hasattr(estimator, "truncate_text_to_tokens"):
        shortened = estimator.truncate_text_to_tokens(
            summary_text,
            max_tokens=emergency_max_tokens,
        )
        if shortened != summary_text:
            return shortened.rstrip() + "..."

    # Temporary fallback for early PRs if token-aware truncation is not yet
    # implemented. This is deterministic, local, and request-scoped only.
    if len(summary_text) <= fallback_max_chars:
        return summary_text
    return summary_text[: fallback_max_chars - 3].rstrip() + "..."
```

Implementation note:

- This behavior is not "library supported" as one turnkey compression feature.
- The tokenizer library helps with token counting and token-aware truncation.
- The compression policy itself is application logic that we implement in
  `ContextAssemblyService` or a helper it owns.
- In v1, this is intentionally simple deterministic shortening, not semantic
  rewriting.

### Fact Compression At Storage Time

This project does not change how durable facts are stored.

Specifically:

- no storage-time fact rewriting
- no migration to denser persisted fact schema
- no background job to re-compress facts

Storage-time fact normalization or compaction may become future work, but it is
out of scope here. This project only changes which facts are selected and how
their text is truncated for prompt assembly.

### Observability And Data Handling

- Compression decisions must be explainable in logs and service metadata.
- No raw full-prompt logging.
- No raw message-content inspection endpoint in production.
- Any optional debug inspection seam must expose only redacted or summarized
  prompt-shaping metadata, never raw prompt content.
- Any optional debug inspection seam must be explicitly gated and disabled by
  default in production.

## Tokenization Guidance

This plan should follow Hugging Face tokenizer guidance for the long-term
model-aware counting path.

Relevant design implications from the tokenizer docs:

- Transformers v5 uses a unified tokenizer surface and selects the appropriate
  backend internally.
- The standard backend for most models is the Tokenizers-backed backend.
- `PythonBackend` exists for highly specialized tokenizers and is not the
  normal choice for standard model-aware token counting.
- Chat-style messages should be counted after applying the model's chat
  template when available, because the rendered control tokens materially
  affect token counts.

Implementation consequence:

- The long-term estimator should use a normal tokenizer loading path and count
  the rendered chat input, not only the raw `content` fields.
- If the target tokenizer supports chat templating, use it for the
  model-specific counting path.
- If a model does not expose usable chat templating in the selected tokenizer
  path, the estimator may fall back to deterministic wrapper-overhead logic,
  but that should be documented in code and kept behind the same estimator
  interface.

## Architecture Changes

### New Internal Concepts

Add these backend concepts. The code below is illustrative pseudocode, not
final implementation code.

```python
from dataclasses import dataclass
from typing import Literal


@dataclass
class PromptSection:
    # Logical section kind so compression rules can reason by behavior.
    kind: Literal[
        "system_instructions",
        "summary",
        "durable_facts",
        "recent_turns",
        "new_user_message",
        "tool_context",
    ]
    # Renderable content or structured messages for this section.
    content: object
    # Estimated tokens for this section in its current form.
    estimated_tokens: int
    # Compression priority; lower means more protected.
    priority: int
    # Required sections cannot be removed, only potentially shortened.
    required: bool
    # Canonical IDs behind this section for observability and testing.
    source_ids: list[str]
    # Human-readable note about how this section was shaped.
    compression_state: str
```

```python
@dataclass
class PromptBudget:
    # Soft target we try to fit under before calling the model.
    target_tokens: int
    # Hard upper bound after all compression decisions.
    hard_max_tokens: int
    # Normal summary budget before emergency fallback.
    summary_soft_max: int
    # Smaller emergency budget for the saved summary.
    summary_emergency_max: int
    # Maximum token budget allocated to the facts section before trimming.
    facts_soft_max: int
    # Maximum token budget allocated to older recent turns.
    recent_turns_soft_max: int
```

```python
@dataclass
class PromptCompressionResult:
    # Final chat messages that will be sent to the LLM.
    messages: list[dict]
    # Estimated total prompt tokens for the final rendered prompt.
    estimated_total_tokens: int
    # Token breakdown by logical section for logs/debug/test assertions.
    estimated_tokens_by_section: dict[str, int]
    # Whether a saved summary made it into the final prompt.
    included_summary: bool
    # Number of transcript messages retained in the final prompt.
    included_recent_turn_count: int
    # Durable facts retained after compression.
    included_fact_ids: list[str]
    # Durable facts dropped during compression.
    dropped_fact_ids: list[str]
    # Ordered audit trail of compression steps taken.
    compression_actions: list[str]
    # Reuse current ranking terminology such as "relevance", "recency", or
    # "chroma" so behavior stays explainable.
    selection_method: str
```

```python
class PromptTokenEstimator:
    # Estimate tokens for plain text in isolation.
    def estimate_text(self, text: str) -> int: ...

    # Estimate tokens for a fully rendered message list.
    def estimate_messages(self, messages: list[dict]) -> int: ...

    # Optional helper for section-level accounting if the implementation needs
    # more than whole-message estimation.
    def estimate_section(self, section: PromptSection) -> int: ...
```

### Context Assembly Flow

Refactor `ContextAssemblyService` into this pipeline:

1. Load canonical inputs from Postgres and Chroma-backed ranking exactly as
   today.
2. Build candidate prompt sections rather than final messages immediately.
3. Rank facts using the existing ranking rules and mark the ranked list
   explicitly so tail trimming is deterministic.
4. Render or partially render candidate sections as needed for token
   estimation.
5. Estimate section and total token cost.
6. Apply compression policy until under target budget or minimum viable shape
   is reached.
7. Render compressed sections into final OpenAI-style messages.
8. Return messages plus compression metadata.

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

These settings must land early in the PR sequence so later compression PRs can
test real configured behavior rather than temporary hardcoded values.

Meaning of each setting:

- `PROMPT_TARGET_TOKENS`
  The normal soft ceiling for the assembled prompt before compression stops.
- `PROMPT_HARD_MAX_TOKENS`
  The maximum allowed estimated prompt size after all compression and fallback
  steps.
- `PROMPT_SUMMARY_SOFT_MAX_TOKENS`
  The normal token budget allocated to the saved summary before emergency
  compression is needed.
- `PROMPT_SUMMARY_EMERGENCY_MAX_TOKENS`
  The smaller token budget used when the summary must be shortened more
  aggressively under pressure.
- `PROMPT_FACTS_SOFT_MAX_TOKENS`
  The normal token budget allocated to the durable-facts section before fact
  trimming begins.
- `PROMPT_RECENT_TURNS_SOFT_MAX_TOKENS`
  The normal token budget allocated to older recent transcript turns, excluding
  the protected newest interaction bundle.

## Behavioral Spec

### Under Budget

If candidate context is under budget:

- output should be materially unchanged from current behavior
- only metadata and logging differ
- no extra truncation should be introduced just because compression machinery
  exists

### Over Budget With Many Facts

If the prompt exceeds budget mainly because of durable facts:

- trim the tail of the already-ranked fact list
- preserve ranking order among retained facts
- do not trim transcript before exhausting removable facts
- do not invent a new fact-ranking algorithm in this slice

### Over Budget With Long Transcript

If still over budget after fact trimming:

- preserve the newest interaction bundle
- remove older retained transcript turns from oldest to newest
- keep summary if present before dropping the newest interaction bundle
- do not create a separate PR 0 for transcript compression; it belongs in the
  same budgeting project after the foundational abstractions and settings exist

### Over Budget With Large Summary

If still over budget:

- shrink summary to emergency max
- preserve summary presence if possible rather than removing it immediately
- perform local truncation only
- do not trigger a new summarization LLM call
- do not persist the shortened summary

### Extreme Pressure

If prompt still exceeds budget after all normal steps:

- keep current user message
- keep newest interaction bundle if available
- keep minimal summary or fact block if one still fits
- emit explicit compression actions showing final fallback was used
- remain within the hard max according to the selected estimator

## Accuracy Requirements

The estimator does not need to be exact in v1, but it does need to be useful.

Required properties:

- deterministic for the same input
- monotonic enough that longer rendered prompts estimate larger than shorter
  ones in ordinary cases
- conservative enough to avoid frequent underestimation
- stable enough for unit tests to assert on behavior

Not acceptable as the default implementation:

- raw word count
- raw character count
- opaque nondeterministic heuristics

Acceptable v1 fallback:

- a deterministic estimator based on rendered content plus conservative wrapper
  overhead

Preferred long-term path:

- model-aware local counting using Hugging Face tokenizer APIs and rendered chat
  input

## PR Breakdown

### PR 1: Budget Types, Settings, And Estimator Interface

**Purpose**
Create the token-budget foundation without changing runtime behavior.

**Changes**

- Add `PromptBudget`, `PromptSection`, `PromptCompressionResult`, and
  `PromptTokenEstimator` abstractions.
- Add env-backed prompt budget settings and wire them into backend settings
  loading.
- Add a default estimator implementation.
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
- Make the final interaction bundle explicit in code, including tool-call and
  tool-result messages when present.

**Reviewable outcome**

- Refactor only, no product behavior change.
- Future compression logic has a clean insertion point.

**Tests**

- parity tests for:
  - no summary
  - summary present
  - facts present
  - new conversation
  - tool-using transcript cases where the final interaction bundle is
    identified correctly

### PR 3: Fact Compression

**Purpose**
Introduce the first small behavior change.

**Changes**

- If over budget, drop weakest facts before touching summary or transcript.
- Define "weakest" as the tail of the already-ranked fact list.
- Record `dropped_fact_ids` and compression actions.

**Reviewable outcome**

- Easy to reason about.
- Small blast radius.
- Directly useful even before transcript compression lands.

**Tests**

- failing test first: fact-heavy prompt trims facts first
- retained facts preserve ranking order
- transcript remains unchanged while removable facts still exist
- no new ranking logic is introduced accidentally

### PR 4: Adaptive Transcript Compression

**Purpose**
Make recent-turn selection budget-aware.

**Changes**

- Preserve newest interaction bundle.
- Remove older turns oldest-first once facts are exhausted.
- Keep role order stable.

**Reviewable outcome**

- Core adaptive selection behavior arrives in one focused PR.

**Tests**

- failing test first: newest interaction bundle always retained
- no-summary conversations shrink transcript correctly
- summary-present conversations still prefer summary over older turns
- tool-assisted final answers keep their associated tool messages

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
- summary compression does not persist changes back to storage

### PR 6: Logging And Operator Visibility

**Purpose**
Make the feature inspectable once compression behavior is complete.

**Changes**

- Add structured logs for token usage and compression actions without logging
  raw full-prompt or raw message content.
- Optionally add a debug-only inspection seam if logs are insufficient, but
  keep it limited to redacted or summarized prompt-shaping metadata only,
  gate it behind an explicit debug flag, and disable it by default in
  production.

**Reviewable outcome**

- Operators can reason about prompt shaping without reading code.

**Tests**

- logs and metadata contain expected compression fields
- no sensitive full-prompt leakage
- debug inspection is gated correctly if implemented

## Test Plan

### Main Unit-Test Seam

Start in
`apps/assistant-backend/tests/services/test_context_assembly_service.py`.

If the compression suite starts to exceed roughly 300 lines or mixes unrelated
behaviors, split into targeted files by behavior area. Suggested examples:

- `test_context_assembly_budgeting.py`
- `test_context_assembly_fact_compression.py`
- `test_context_assembly_transcript_compression.py`
- `test_context_assembly_summary_fallback.py`

Maintainability is a requirement, not a nice-to-have.

### Integration Coverage

Add narrow integration tests only where needed to prove wiring from
conversation service to LLM request construction.

### Required New Scenarios

- under-budget prompt preserves current shape
- fact-heavy prompt trims facts before transcript
- transcript-heavy prompt preserves newest interaction bundle
- summary-present prompt prefers summary over older transcript turns
- tool-assisted final answer preserves associated tool messages
- extreme prompt pressure triggers minimum viable fallback
- summary compression is request-local and does not mutate storage
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
  hide counting behind `PromptTokenEstimator`, prefer rendered-chat counting,
  and keep compression policy estimator-agnostic

- Risk: over-compression removes needed context
  Mitigation:
  encode preservation rules in tests, especially the current user message and
  newest interaction bundle

- Risk: refactor and behavior changes getting mixed together
  Mitigation:
  keep refactor-only PRs separate from compression-behavior PRs

- Risk: future model presets needing different counting or templates
  Mitigation:
  estimator and budget objects are preset-ready even if presets are not
  implemented yet

- Risk: debug inspection accidentally exposing sensitive content
  Mitigation:
  no raw content in logs, no raw content in debug inspection, explicit gating,
  off by default in production

## Follow-On Value

After this project lands:

- model presets become safer because each preset can supply its own estimator
  and budget profile
- attachment ingestion has a clear place to compete for prompt budget
- `Continue` and truncation frequency should decrease under normal use
- prompt shaping becomes observable instead of implicit
- storage-time fact normalization can be considered later as a distinct follow-on

## Assumptions

- We are not changing product surface area in this effort.
- We want a clean internal foundation, not a one-off heuristic patch.
- The preferred long-term counting path uses standard Hugging Face tokenizer
  APIs and their normal tokenizer backends, not a custom `PythonBackend`.
- The estimator interface comes first so the implementation can ship in stages.
- This plan should be implemented with TDD and one small reviewable PR at a
  time.

## Sources

- Hugging Face Transformers tokenizer backend guidance, including backend
  selection and `PythonBackend` positioning
- Hugging Face chat templating and tokenizer API guidance for rendered
  chat-message handling
