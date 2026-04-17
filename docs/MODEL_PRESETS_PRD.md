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
- The UI features a dropdown model selector near the message composer.
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
- The initial UI is a dropdown below or beside the text input.
- Initial presets may all point at the same base model.
- Curated presets only; no raw Ollama model picker in the main product
  UI.
- The curated preset list lives in the repository as checked-in
  configuration.
- Memory extraction is configurable and uses a stable model independent
  from the user-facing reply preset.

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

## Capability-Specific Handling

### Multimodal (Vision) Support

When a preset includes the `vision` capability:

- **Request Payload:** The frontend should include image attachments in the
  `user_message` payload.
- **Request Adapter:** The adapter is responsible for formatting the images into the
  standard message content shape (e.g., using `image_url` or base64 data) required
  by the LLM backend.
- **Validation:** The backend should reject messages with image attachments if the
  selected preset does not explicitly declare `vision` capability.

### Streaming for Reasoning Presets

Reasoning models (like `thinking` presets) can have significantly higher latency
due to long-running thought traces.

- **Policy:** Presets that support reasoning **should prioritize streaming** to
  provide immediate feedback to the user.
- **Thought Disclosure:** The streaming implementation should distinguish between
  "thinking" tokens and "content" tokens, allowing the UI to render the reasoning
  trace in a distinct (often collapsible) area as it arrives.

## Proposed Solution

### Curated preset registry

The backend maintains a checked-in registry of user-facing model presets
located in `apps/assistant-backend/src/assistant/config/model_presets.py`.

The implementation uses a Python-based registry for type-safe
configuration and ease of integration.

Each preset defines:

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

Field intent:

- `capabilities`
  - a list of features supported by the preset (e.g., `["text", "vision", "tools", "reasoning"]`)
  - used by the backend to validate behavior and by the UI to decide
    whether optional affordances (like image upload) should appear
- `request_strategy`
  - a stable identifier for the request adapter behavior used to build
    prompts and reasoning controls for this preset
  - example values might look like `default_chat`,
    `ollama_native_think`, or `gemma_think_token`
- `response_strategy`
  - a stable identifier for the response adapter behavior used to parse
    assistant output for this preset
  - example values might look like `plain_content`,
    `ollama_thinking_field`, or `gemma_tag_stripping`

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

Preset usage is recorded in message-level metadata within the existing
`annotations` field.

On user messages:

- `selected_preset_id`

On assistant messages:

- `selected_preset_id`
- `resolved_model`
- `reasoning_mode`

Standard approach:

- Store preset usage in the `annotations` JSON field.
- Avoid adding new dedicated columns in the initial implementation.

This provides flexibility while maintaining a clean schema.

Example shape in `annotations`:

```json
{
  "preset_id": "qwen-thinking",
  "resolved_model": "qwen2.5:7b",
  "reasoning_mode": "thinking"
}
```

The exact contents differ by message role:

- A user message stores `selected_preset_id`.
- An assistant message includes the resolved model and reasoning mode.

## UI Changes

The initial UI change is intentionally small:

- add a dropdown selector near the message composer
- fetch presets from the backend
- show the curated preset label in the dropdown
- remember the last selected preset locally for convenience
- send the chosen preset id with each message

### Preset Transition Logic

The UI must adapt its composer state when a user switches presets:

- **Capability Enforcement:** If a user switches from a `vision`-capable preset to a
  text-only preset, the UI should warn the user that current image attachments
  will be ignored or removed.
- **Visual Cues:** The UI should use subtle indicators (e.g., a "Thinking" badge or
  an "Image Supported" icon) to reflect the capabilities of the currently active
  preset.

## Reasoning Display Policy

Policy for handling reasoning traces:

- Persist clean final assistant content as the canonical message body.
- Reasoning traces are stored as structured metadata in `annotations`.
- **Do not** include reasoning traces in conversation history for future
  turns to avoid context contamination.
- Reasoning traces are treated as optional metadata for display or
  debugging.

This ensures that the main dialogue remains focused and that memory
extraction logic is not confused by internal reasoning steps.

## Rollout Plan

### Phase 1: Preset Registry & Registry API

Deliver a testable backend registry and the endpoint for the UI to consume.

- **Deliverables:**
  - `ModelPreset` Pydantic model and registry configuration (JSON or Python).
  - Registry loader service.
  - `GET /api/v1/model-presets` endpoint.
  - Unit tests for registry loading and API contract.

### Phase 2: Backend Payload & Persistence Support

Add the ability for the backend to receive and persist `preset_id` without
changing existing LLM behavior yet.

- **Deliverables:**
  - Update `CreateMessageRequest` and `CreateConversationWithMessageRequest`
    to include `preset_id`.
  - Update `Message` SQL model (metadata/annotations) to store the selected preset.
  - Update `ConversationService` to extract and persist the preset ID.
  - Tests for message creation with/without preset IDs.

### Phase 3: Frontend Model Selector

Implement the UI for selecting presets and passing the ID to the backend.

- **Deliverables:**
  - Frontend API client updates.
  - Dropdown component near the message composer.
  - Logic to remember the last-selected preset.
  - Handling of capability transitions (e.g., clearing images if switching to
    text-only).

### Phase 4: Adapter Architecture & Default Adapter

Refactor the LLM service to use the Adapter Pattern, preserving current behavior
as the "Default" strategy.

- **Deliverables:**
  - `BaseModelAdapter` interface.
  - `DefaultModelAdapter` (current `qwen2.5` logic).
  - Refactor `LLMService.complete_messages` to delegate to the resolver/adapter.
  - Integration tests ensuring zero regression for standard messages.

### Phase 5: First Reasoning Preset (Thinking Mode)

Implement the first non-default behavior: a "Thinking" preset.

- **Deliverables:**
  - `ReasoningModelAdapter` with `think` control and reasoning parsing.
  - Registry update to include a `thinking` preset.
  - Persistence of reasoning traces into assistant message annotations.
  - Tests for reasoning extraction and persistence.

### Phase 6: Separate Extraction Configuration

Decouple memory extraction from the user-facing preset.

- **Deliverables:**
  - Registry-driven extraction preset resolver.
  - Update `extract_and_save_background` to use the configured extraction preset.
  - Tests verifying extraction consistency regardless of chat preset.

### Phase 7: Multimodal (Vision) Support

Add the capability for image-based conversation presets.

- **Deliverables:**
  - `VisionModelAdapter` for image formatting.
  - Backend validation for image payloads vs. preset capabilities.
  - Registry update with a `vision` preset.

## Testing Strategy

We should add coverage for:

- preset API contract
- per-message preset transport
- request adapter behavior
- response parsing behavior
- persistence of preset metadata
- extraction preset resolution
- mixed-preset conversation flows

## Open Questions & Proposed Answers

### How should we handle Gemma reasoning controls?

**Question:** When Gemma presets are introduced, should we use Ollama-native reasoning
controls, prompt tokens, or both?

**Recommendation:** We should **prefer Ollama-native reasoning controls** (using the
`think` parameter) when they are supported by Ollama for the specific Gemma variant.

- **Why:** It provides a cleaner request structure and lets the backend handle
  model-specific token updates. Most importantly, it allows the reasoning trace to
  be returned in a separate field, simplifying the process of extracting clean
  content for persistence.
- **Fallback:** We should **fallback to prompt tokens** (manual tag injection) only if
  Ollama's native support for a specific model's reasoning mode is missing or
  inconsistent.

### Should reasoning traces be persisted?

**Question:** Should reasoning traces ever be persisted beyond transient UI metadata?

**Recommendation:** Yes, reasoning traces should be persisted as **structured metadata**
within the assistant message's `annotations` field, but kept separate from the
canonical `content`.

- **Why:** Persisting reasoning traces enables debugging, model evaluation, and
  features like "Show Thinking" for past messages in the UI.
- **Policy:** While persisted, these traces should **not** be included in the
  conversation history sent back to the LLM in future turns. This prevents
  "context contamination" and keeps the prompt focused on the actual dialogue.

### Global vs. Per-Preset Extraction

**Question:** Do we want one extraction preset globally, or per user-facing preset?

**Recommendation:** We should use a **global default extraction preset** with the
capability for **per-preset overrides** in the registry.

- **Why:** For most chat presets, a single stable model (like `qwen2.5:7b`) is the
  most reliable for memory extraction. However, specialized presets (e.g., for
  coding or structured data) may eventually require specialized extraction models
  or prompts.
- **Implementation:** The `ModelPresetRegistry` should include an optional
  `memory_extraction_preset` field. If omitted, the system falls back to the
  configured global default.

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
