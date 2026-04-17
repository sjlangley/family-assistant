# Model Presets PRD

## Summary

This document defines the first implementation plan for user-selectable
model presets in Family Assistant.

The product goal is to let users choose between a small curated set of
assistant modes per message, while keeping model-specific prompt
construction, reasoning controls, response parsing, and memory extraction
logic behind backend abstractions.

This work is both:

- a learning project for experimenting with multiple local model setups
- a foundation for a real product feature with stable UI behavior

## Product Goals

- Let the user choose between `2-3` curated presets from the chat UI.
- Support presets that may point to:
  - the same base model with different behavior such as `quick` vs
    `thinking`
  - different Ollama models entirely
- Apply the selected preset per message, not per conversation.
- Keep the UI simple with a dropdown model selector near the message
  composer.
- Allow experimentation with prompt construction, reasoning controls,
  response parsing, and extraction models without changing the UI
  contract.

## Non-Goals

- Exposing every locally installed Ollama model directly to end users
- Committing to one universal reasoning token format across models
- Refactoring the full memory storage schema up front
- Solving image generation in this scope

## Confirmed Product Decisions

- Preset selection is per message.
- The first UI can be a simple dropdown below or beside the text input.
- Initial presets may all point at the same base model.
- Curated presets only; no raw Ollama model picker in the main product
  UI.
- The curated preset list can live in the repository as checked-in
  configuration.
- Memory extraction should remain configurable and may later use a
  simpler or smaller model than the user-facing reply preset.

## Problem Statement

The current backend assumes a single configured model and a mostly
uniform request and response shape.

That assumption breaks down once we support:

- multiple user-facing model options
- different reasoning modes for the same model
- model-specific prompt controls such as Gemma thinking tokens
- model-specific response parsing rules
- future experimentation with separate extraction models

We need a design that keeps the product surface stable while allowing the
backend to adapt to model-specific behavior.

## Key Technical Observations

### Presets should be the product surface

The user should select from app-defined presets, not raw model names.

This lets us present a stable UI contract such as:

- `Quick`
- `Thinking`
- `Balanced`

without forcing the UI to understand Ollama-specific model behavior.

### Reasoning controls are not universal

We should not assume that `<think>`-style or `<|think|>`-style control
tokens are universal across models.

Some models can be controlled through Ollama-native request fields such
as `think`, while others may require prompt-level conventions or emit
model-specific thought markers.

This means reasoning behavior must be handled by backend adapters, not by
hardcoded UI logic.

### Response parsing may vary by preset

Different presets may require different response parsing strategies.

Examples:

- plain content extraction
- Ollama-native `thinking` field handling
- model-specific tag stripping
- tool-call normalization

### Memory extraction is a separate concern

The user-selected reply preset should not automatically determine the
model used for summary and durable-fact extraction.

Extraction has different goals:

- predictable formatting
- lower cost
- lower latency
- fewer reasoning artifacts

We should therefore treat extraction model selection as preset-driven
configuration, not an implicit copy of the visible chat preset.

## Proposed Solution

### Curated preset registry

Introduce a checked-in backend registry of user-facing model presets.

The initial implementation can use a Python module or JSON file in the
repository.

Each preset should define:

- `id`
- `label`
- `description`
- `ollama_model`
- `reasoning_mode`
- `capabilities`
- `request_strategy`
- `response_strategy`
- `show_reasoning_in_ui`
- `memory_extraction_preset`

Example conceptual presets:

- `qwen-quick`
- `qwen-thinking`
- `qwen-balanced`

All three may initially map to `qwen2.5` while differing in behavior.

### Backend preset API

Add a backend endpoint for the UI to query the curated preset list.

Initial endpoint:

```text
GET /api/v1/model-presets
```

The response should include only curated presets approved for the
product.

It should not expose the raw set of locally installed Ollama models in
the main UI path.

### Request adapter layer

Introduce a model preset request adapter that is responsible for:

- constructing the final prompt or system prompt
- applying reasoning controls for the selected preset
- choosing the appropriate Ollama request shape
- passing through model-specific request options

This layer keeps prompt-generation logic out of the conversation route
handlers and out of the UI.

### Response adapter layer

Introduce a matching response adapter that is responsible for:

- extracting final assistant content
- extracting reasoning traces when available
- stripping model-specific markers from persisted message content
- normalizing metadata for annotations or UI rendering

This layer should define what gets:

- shown to the user as the main response
- optionally shown as reasoning
- persisted into conversation history
- fed back into the next turn

### Per-message preset selection

Each user message should carry the selected preset identifier.

Each assistant message should record:

- preset id used
- underlying model used
- any reasoning mode metadata needed for debugging or analysis

This allows mixed-preset conversations while preserving traceability.

### Memory extraction configuration

Keep the current extraction path, but move toward a dedicated extraction
preset configuration.

Initial behavior:

- continue using `qwen2.5` for extraction
- make the extraction preset configurable in the registry

Future behavior:

- experiment with smaller or more stable extraction models
- tune extraction parameters independently from user-facing reply presets

## Architecture Changes

### New concepts

- `ModelPresetRegistry`
- `ModelRequestAdapter`
- `ModelResponseAdapter`
- `ExtractionPresetResolver`

### Existing areas likely touched

- backend settings and configuration loading
- chat and conversation request models
- LLM service orchestration
- conversation persistence
- assistant annotations
- background memory extraction flow
- frontend composer UI
- frontend API client and types
- tests across backend and frontend

## Data Model Implications

We should plan for message-level metadata that records preset usage.

At minimum, we likely need assistant and or user message metadata for:

- selected preset id
- resolved model id
- reasoning mode

Recommended initial approach:

- store preset usage in a structured message metadata field
- avoid adding multiple dedicated columns in the first iteration

This gives us flexibility while we experiment with which fields are
actually useful to persist.

Example shape:

```json
{
  "preset_id": "qwen-thinking",
  "resolved_model": "qwen2.5:7b",
  "reasoning_mode": "thinking"
}
```

We can later promote stable high-value fields such as `preset_id` to
dedicated columns if querying, indexing, or analytics needs justify it.

## UI Changes

The initial UI change is intentionally small:

- add a dropdown selector near the message composer
- fetch presets from the backend
- show the curated preset label in the dropdown
- remember the last selected preset locally for convenience
- send the chosen preset id with each message

Future UI enhancements may include:

- preset descriptions
- reasoning indicators
- optional reasoning disclosure panels

The UI does not need to enforce a strict naming philosophy for preset
labels.

The label should be whatever makes sense to the developer and the
intended users, as long as it is clear enough in the dropdown.

The underlying model name remains backend metadata and does not need to
appear in the primary model selector UI.

## Reasoning Display Policy

Initial recommendation:

- persist clean final assistant content as the canonical message body
- do not include prior reasoning traces in normal conversation history
- treat reasoning as optional metadata for display or debugging

This avoids contaminating future turns and memory extraction with raw
thought traces.

## Rollout Plan

### Phase 1

Create the preset registry and backend preset API.

Deliverables:

- checked-in preset config
- preset registry loader
- `GET /api/v1/model-presets`

### Phase 2

Add per-message preset selection end to end.

Deliverables:

- frontend dropdown selector
- request payload updates
- backend handling of preset id per message
- persistence of preset metadata

### Phase 3

Introduce request and response adapter abstractions.

Deliverables:

- adapter interfaces
- default adapter for current `qwen2.5` behavior
- first reasoning-capable adapter path

### Phase 4

Separate extraction preset configuration from user-facing reply preset
selection.

Deliverables:

- extraction preset config
- extraction path reads configured preset
- tests covering extraction independence

### Phase 5

Experiment with additional presets and model-specific parsing behavior.

Deliverables:

- Gemma-specific preset support if adopted
- reasoning visibility decisions in the UI
- tuning and evaluation notes

## Testing Strategy

We should add coverage for:

- preset API contract
- per-message preset transport
- request adapter behavior
- response parsing behavior
- persistence of preset metadata
- extraction preset resolution
- mixed-preset conversation flows

## Open Questions

- Should reasoning traces ever be persisted beyond transient UI metadata?
- Do we want one extraction preset globally, or per user-facing preset?
- When Gemma presets are introduced, should we use Ollama-native
  reasoning controls, prompt tokens, or both?

## Recommended First Milestone

The smallest meaningful slice is:

- checked-in curated preset registry
- preset list API
- composer dropdown
- per-message preset id transport
- preset metadata persistence
- default `qwen2.5` adapter
- extraction continues using `qwen2.5`

That gives us a real user-facing feature and the core abstraction seam
without forcing all model-specific parsing work into the first pass.
