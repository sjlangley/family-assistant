# Phase 1 Implementation Plan

## Goal

Ship the first trustworthy-assistant upgrade on top of the existing chat app:

- context compression
- durable fact memory
- one controlled research tool path, `web_search` + `web_fetch`
- message-level trust annotations in the chat UI

This plan is the implementation spec for phase 1.

It assumes the reviewed decisions are already locked:

- no streaming in phase 1
- one truthful pending placeholder in the UI while a request is in flight
- final assistant rows persist structured `annotations`
- backend failures persist a terminal assistant failure row
- Postgres is canonical for summaries and durable facts
- Chroma is retrieval/index support, not the source of truth
- `BackgroundTasks` handles post-response extraction
- model-native tool calling, no custom planner loop
- backend stays centered on `ConversationService` plus at most two focused collaborators
- test coverage is `pytest` + `Vitest`, not a new browser E2E stack

## Not In Scope

- true streamed stage-by-stage assistant updates
- post-response event delivery for live memory-save notices
- image generation
- Google Drive ingestion and genealogy-specific UI
- normalized evidence/source tables
- browser E2E

## Existing Foundations To Reuse

- [apps/assistant-backend/src/assistant/services/conversation_service.py](../apps/assistant-backend/src/assistant/services/conversation_service.py)
  Current request/response conversation orchestration.
- [apps/assistant-backend/src/assistant/models/conversation_sql.py](../apps/assistant-backend/src/assistant/models/conversation_sql.py)
  Current persisted conversation and message schema.
- [apps/assistant-backend/src/assistant/services/llm_service.py](../apps/assistant-backend/src/assistant/services/llm_service.py)
  Current LLM transport.
- [apps/assistant-backend/src/assistant/services/memory_storage.py](../apps/assistant-backend/src/assistant/services/memory_storage.py)
  Current Chroma integration.
- [apps/assistant-ui/src/components/ConversationsChat.tsx](../apps/assistant-ui/src/components/ConversationsChat.tsx)
  Current chat shell and message flow.
- [DESIGN.md](../DESIGN.md)
  Source of truth for the UI system.

## High-Level Delivery Order

```text
schema + contracts
    ->
shared LLM seam
    ->
context assembly
    ->
conversation orchestration + failure rows + annotations
    ->
background extraction + Postgres memory writes + Chroma indexing
    ->
frontend trust UI
    ->
full backend + frontend test coverage
```

## Architecture Shape

```text
user input
  ->
ConversationService
  ->
ContextAssemblyService
  ->  recent turns
  ->  latest conversation summary
  ->  durable facts
  ->  optional Chroma-ranked candidates
  ->
shared LLM completion helper
  ->
ToolService
  ->  BaseTool
  ->  ToolFactory
  ->  web_search
  ->  web_fetch
  ->  future tools, for example image generation
  ->
assistant result + tool outputs
  ->
AssistantAnnotationService
  ->  final persisted annotations
  ->  failure-row annotations
  ->  background summary/fact extraction
  ->
Postgres canonical writes
  +-> Chroma indexing support
  ->
API response
  ->
ConversationsChat trust UI
```

## Data Model Additions

### 1. Persisted assistant annotations

Add a nullable `annotations` field to assistant messages.

Use it as the canonical source for:

- trust row chips
- evidence panel content
- memory-hit notices
- memory-saved notices
- terminal failure metadata

Suggested shape:

```json
{
  "tools_used": [
    {
      "name": "web_search",
      "label": "Web search"
    },
    {
      "name": "web_fetch",
      "label": "Web fetch"
    }
  ],
  "sources": [
    {
      "title": "1911 England Census",
      "snippet": "George Langley, age 27...",
      "url": "https://...",
      "rationale": "Supports the birth-year match"
    }
  ],
  "memory": {
    "hits": [
      {
        "label": "Saved birth year for George Langley"
      }
    ],
    "saved": [
      {
        "label": "Saved census location",
        "confidence": "high"
      }
    ]
  },
  "status": {
    "kind": "success"
  }
}
```

For failure rows:

```json
{
  "tools_used": [],
  "sources": [],
  "memory": {
    "hits": [],
    "saved": []
  },
  "status": {
    "kind": "error",
    "label": "LLM request timed out"
  }
}
```

### 2. Canonical memory tables

Add SQLModel tables for:

- latest conversation summary per conversation
- durable facts per user

Keep them simple.

Suggested fields:

#### Conversation summary table

- `id`
- `conversation_id`
- `user_id`
- `summary_text`
- `source_message_id`
- `version`
- `created_at`
- `updated_at`

#### Durable fact table

- `id`
- `user_id`
- `subject`
- `fact_text`
- `confidence`
- `source_type`
- `source_conversation_id`
- `source_message_id`
- `source_excerpt`
- `active`
- `created_at`
- `updated_at`

### 3. Migration requirement

Do not rely on `SQLModel.metadata.create_all()` for these schema changes.

That call creates missing tables, but it does not safely evolve existing Postgres schemas.

Concrete implementation requirement:

- scaffold first Alembic migration support for the backend
- add one migration for the new message `annotations` column
- add one migration for summary and durable-fact tables
- keep `create_all()` for local empty-db convenience only if it does not conflict with Alembic

## Budget Rules

These are not optional.

They keep trust payloads useful instead of bloated.

- `sources`: max `3` per assistant row
- `source.snippet`: max `240` chars
- `memory.hits`: max `2`
- `memory.saved`: max `1`
- `tools_used`: max `2`, with phase 1 limited to `web_search` + `web_fetch`
- never persist raw full tool outputs in `annotations`
- never treat raw search snippets as final evidence
- never inject `annotations` back into model prompt assembly
- prompt assembly uses:
  - recent turns only
  - latest summary only
  - capped durable facts only
  - capped retrieval hits only

## Concrete Steps

### Step 1. Add backend schema and API contracts

**Status:** ✅ **COMPLETE**

**Files**

- ✅ update [apps/assistant-backend/src/assistant/models/conversation_sql.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/models/conversation_sql.py)
- ✅ update [apps/assistant-backend/src/assistant/models/conversation.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/models/conversation.py)
- ✅ add annotations models: [apps/assistant-backend/src/assistant/models/annotations.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/models/annotations.py)
- ✅ add memory SQLModel file, for example `apps/assistant-backend/src/assistant/models/memory_sql.py`
- ✅ add memory API model file, for example `apps/assistant-backend/src/assistant/models/memory.py`
- ✅ add Alembic scaffold and migrations under `apps/assistant-backend/`
- ✅ update [apps/assistant-ui/src/types/api.ts](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-ui/src/types/api.ts)

**Work**

- ✅ add `annotations` to persisted assistant messages
- ✅ add Pydantic models for annotation payloads (`AssistantAnnotations`, `SourceAnnotation`, `ToolAnnotation`, `MemoryHitAnnotation`, `MemorySavedAnnotation`, `FailureAnnotation`)
- ✅ add summary and durable-fact tables
- ✅ extend TypeScript `Message` shape to include `annotations`

**Acceptance criteria**

- ✅ backend can serialize assistant messages with `annotations: null | object`
- ✅ schema migration path exists for existing Postgres installs
- ✅ frontend type layer can represent all phase-1 trust payloads

**Completed work:**
- Added nullable `annotations` JSON field to `Message` table (conversation_sql.py)
- Created comprehensive annotation models with proper type enums and Pydantic validation
- Extended `MessageRead` API contract to include annotations
- Added matching TypeScript types for all annotation structures
- Updated frontend test mocks to handle nullable annotations
- Created conversation summary and durable fact SQLModel tables
- Created corresponding Pydantic API models for memory operations
- Scaffolded Alembic migration infrastructure:
  - Configured `alembic/env.py` with proper SQLModel metadata imports
  - Set up automatic driver conversion (asyncpg → psycopg for migrations)
  - Added `psycopg[binary]` dependency for synchronous migrations
  - Created initial migration (`57bad9ffdeea`) with:
    - `annotations` JSON column on `messages` table
    - `conversation_memory_summaries` table with constraints and indexes
    - `durable_facts` table with constraints and indexes
    - Proper upgrade/downgrade procedures
  - Updated `alembic/README` with usage instructions and troubleshooting


### Step 2. Extract the shared LLM completion seam

**Status:** ✅ **COMPLETE**

**Files**

- update [apps/assistant-backend/src/assistant/services/llm_service.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/services/llm_service.py)
- update [apps/assistant-backend/src/assistant/routers/chat.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/routers/chat.py)
- update [apps/assistant-backend/src/assistant/services/conversation_service.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/services/conversation_service.py)

**Work**

- move shared request construction, response validation, and error mapping into one backend helper
- keep `/api/v1/chat/completions` behavior unchanged
- make conversation flow use the same seam
- preserve first-response metadata needed for native tool calling, including `tool_calls` and `finish_reason`
- remove the deprecated raw completion bypass so new callers do not drift back to duplicated validation logic

**Acceptance criteria**

- both chat entry points share one request/response mapping path
- `/api/v1/chat/completions` remains a regression-protected route

**Completed work:**
- Added typed seam models for shared completion results and service-level error classification
- Refactored `LLMService` to own canonical request construction, transport, response validation, and first-choice extraction
- Updated the chat router and `ConversationService` to use the shared seam instead of duplicating response parsing
- Preserved `tool_calls` and `finish_reason` in the seam result so the upcoming research tool path can build on it cleanly
- Removed the deprecated public raw completion wrapper to keep one supported backend completion path
- Expanded backend regression coverage around seam parsing, error mapping, and both existing callers

### Step 3. Add `ContextAssemblyService`

**Status:** ✅ **COMPLETE**

**Purpose**

Bounded context assembly from canonical Postgres sources (summaries, facts, recent turns). Uses only authoritative data - no retrieval-backed hints yet.

**New collaborator 1**

- `apps/assistant-backend/src/assistant/services/context_assembly.py`

**Files**

- add `ContextAssemblyService`
- update [apps/assistant-backend/src/assistant/services/__init__.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/services/__init__.py)
- update [apps/assistant-backend/src/assistant/services/conversation_service.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/services/conversation_service.py)

**Work**

- load recent turns from Postgres
- load latest conversation summary from Postgres
- load durable facts for the user from Postgres
- enforce prompt budgets
- return the exact message list for the LLM helper

**Acceptance criteria**

- ✅ no raw full transcript resend once summary exists
- ✅ durable facts are per-user
- ✅ prompt assembly is deterministic under budget pressure

**Completed work:**
- Added `ContextAssemblyService` with a typed `ContextAssemblyResult` for prepared messages and debug metadata
- Load latest conversation summary, active per-user durable facts, and capped recent-turn window from canonical Postgres tables
- Enforced explicit prompt budgets: 4 recent turns with summary, 8 without; max 5 facts; text truncation at 200 chars/fact and 1000 chars/summary
- Updated `ConversationService` to use `ContextAssemblyService` for both new and existing conversation replies
- Added regression test preventing duplicate user messages in prompts
- All code and tests reflect Postgres-only implementation; Chroma retrieval support deferred to Step 6+

**Note on Chroma**

Chroma retrieval was deliberately excluded from the Step 3 shipped implementation in favor of keeping the code simple and honest. Canonical Postgres summaries + facts + recent turns provide a solid foundation. Once Step 5 has written full summary and fact text to Postgres, Step 6 will add retrieval-backed ranking and context augmentation for candidates.

### Step 4. Add the first research tool path: `web_search` + `web_fetch`

**Purpose**

Create a small reusable tool layer that supports the first research path now and future tools, such as image generation, soon after.

**Completed groundwork**

The initial Step 4 foundation has already landed:

- added a shared `ToolService` plus explicit `BaseTool` and `ToolFactory` seams
- added typed tool execution models so `ConversationService` and future annotation work can share one normalized result contract
- added a deterministic `get_current_time` validation tool to prove the tool path end to end without mixing in search/fetch complexity
- updated `ConversationService` and `LLMService` to support a bounded model-native tool loop with shared tool definitions

The remaining Step 4 work is the first real research path: `web_search` for discovery and `web_fetch` for grounded page reads.

**Files**

- add `apps/assistant-backend/src/assistant/services/tool_service.py`
- add `apps/assistant-backend/src/assistant/services/tools/base.py`
- add `apps/assistant-backend/src/assistant/services/tools/factory.py`
- add `apps/assistant-backend/src/assistant/services/tools/web_search.py`
- add `apps/assistant-backend/src/assistant/services/tools/web_fetch.py`
- update [apps/assistant-backend/src/assistant/settings.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/settings.py)
- update [apps/assistant-backend/src/assistant/services/conversation_service.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/services/conversation_service.py)
- update [apps/assistant-backend/src/assistant/services/context_assembly.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/services/context_assembly.py) only as needed for bounded retrieval support

**Work**

- support one configured research tool path composed of:
  - `web_search` to discover candidate sources
  - `web_fetch` to read selected pages
- add a small `BaseTool` contract that owns:
  - tool definition exposed to the model
  - tool execution
  - enabled/disabled checks
- add a `ToolFactory` that is the explicit allowlist and lookup point for supported tools
- add a `ToolService` that:
  - exposes the available tool definitions to the model
  - dispatches tool calls by name
  - returns normalized tool execution results
- keep the implementation explicit and hardcoded, not a dynamic plugin system or provider registry
- let the model use the search/fetch path natively through the shared tool layer
- require final answers to ground source annotations in fetched page content, not raw search snippets alone
- keep retrieval support, if used, separate from external web research:
  - retrieval is bounded prompt context
  - fetched web pages are external evidence
- convert fetched results into compact structured source inputs for the annotation step
- keep the tool layer small enough that future tools, such as image generation, can be added without reshaping `ConversationService`

**Acceptance criteria**

- the assistant can search for candidate sources and fetch the selected pages before answering
- search snippets alone are not treated as sufficient evidence for trust annotations
- one explicit tool allowlist exists through `ToolFactory`
- one shared tool execution/result path exists through `ToolService`
- fetched page content can produce:
  - source title
  - source URL
  - compact supporting snippet
  - rationale for why the source matters
- failures in search or fetch can still produce a clear terminal assistant failure row
- the implementation remains limited to one controlled research path in phase 1

### Step 5. Add `AssistantAnnotationService`

**New collaborator 2**

- `apps/assistant-backend/src/assistant/services/assistant_annotations.py`

**Files**

- add `AssistantAnnotationService`
- update [apps/assistant-backend/src/assistant/services/conversation_service.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/services/conversation_service.py)
- update [apps/assistant-backend/src/assistant/routers/conversations.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/routers/conversations.py)

**Work**

- build final assistant annotations for successful responses
- build failure annotations for terminal assistant error rows
- centralize annotation budgets
- keep `ConversationService` as orchestration only

**Acceptance criteria**

- success rows persist trust metadata
- failure rows persist clear assistant-side outcome
- annotations remain compact and reload-safe

### Step 6. Add background extraction with canonical Postgres writes

**Files**

- update [apps/assistant-backend/src/assistant/routers/conversations.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/routers/conversations.py)
- update [apps/assistant-backend/src/assistant/services/conversation_service.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/services/conversation_service.py)
- update `ContextAssemblyService`
- update `AssistantAnnotationService`
- update [apps/assistant-backend/src/assistant/services/memory_storage.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/services/memory_storage.py)

**Work**

- use `BackgroundTasks` after final response persistence
- extract refreshed conversation summary
- extract durable facts worth saving
- write canonical summary/fact rows to Postgres
- index summary/fact text into Chroma only as retrieval support
- on extraction failure:
  - log it
  - keep the successful transcript row untouched

**Acceptance criteria**

- user-visible chat success does not depend on extraction success
- summary/fact writes are idempotent enough for retries
- later requests can reuse saved facts and latest summary

### Step 7. Update the conversation API contract

**Files**

- update [apps/assistant-backend/src/assistant/models/conversation.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/models/conversation.py)
- update [apps/assistant-backend/src/assistant/routers/conversations.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/src/assistant/routers/conversations.py)
- update [apps/assistant-ui/src/lib/api.ts](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-ui/src/lib/api.ts)
- update [apps/assistant-ui/src/types/api.ts](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-ui/src/types/api.ts)

**Work**

- return `annotations` on assistant messages in create and reload paths
- preserve backward-compatible null handling where possible

**Acceptance criteria**

- conversation create, add-message, and reload paths all return the same assistant-message shape

### Step 8. Implement the trust UI in the existing chat shell

**Files**

- update [apps/assistant-ui/src/components/ConversationsChat.tsx](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-ui/src/components/ConversationsChat.tsx)
- update [apps/assistant-ui/src/index.css](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-ui/src/index.css)
- add small local UI helpers only if needed

**Work**

- apply `DESIGN.md`
- keep current left-rail + transcript structure
- show one pending placeholder while request is active
- replace placeholder with final persisted assistant row
- render trust row under assistant messages
- open an evidence panel from source interaction
- render assistant failure rows in transcript
- on mobile:
  - rail behind menu
  - trust row stays inline
  - evidence details open as bottom sheet or full-screen detail view
- use polite live-region announcements for meaningful pending-stage changes only

**Acceptance criteria**

- no fake streamed stage choreography
- trust data is driven by persisted annotations
- reload produces the same trust UI as the original response

### Step 9. Test everything added by the plan

**Backend tests**

- update [apps/assistant-backend/tests/services/test_conversation_service.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/tests/services/test_conversation_service.py)
- update [apps/assistant-backend/tests/routers/test_conversations.py](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-backend/tests/routers/test_conversations.py)
- add tests for the two new collaborators
- add regression tests for `/api/v1/chat/completions`

**Frontend tests**

- update [apps/assistant-ui/src/components/ConversationsChat.test.tsx](/Users/stuartlangley/src/sjlangley/family-assistant/apps/assistant-ui/src/components/ConversationsChat.test.tsx)

**Must-cover scenarios**

- success response with persisted annotations
- terminal failure row on LLM/tool/backend failure
- null and partial annotations
- evidence panel interaction
- pending placeholder lifecycle
- background extraction failure after visible chat success
- per-user fact isolation
- prompt-budget truncation behavior

**Acceptance criteria**

- all gaps from the eng-review test artifact are closed
- no new E2E tier introduced

## Implementation Checklist

```text
[x] schema migration support exists
[x] assistant messages persist annotations
[x] summary table exists
[x] durable fact table exists
[x] shared LLM completion helper exists
[x] ContextAssemblyService exists
[x] reusable backend tool layer exists
[x] deterministic validation tool exists
[ ] web_search + web_fetch tool path works
[ ] AssistantAnnotationService exists
[ ] terminal assistant failure rows persist on backend failure
[ ] BackgroundTasks extraction writes summaries/facts
[ ] chat reload returns persisted annotations
[ ] pending placeholder UI works
[ ] trust row renders from persisted annotations
[ ] evidence panel works on desktop and mobile
[x] backend tests updated
[ ] frontend tests updated
```

## Commands To Run During Delivery

### Backend

```bash
cd apps/assistant-backend
python3 -m pytest
```

### Frontend

```bash
cd apps/assistant-ui
npm test
```

### Full repo sanity

```bash
cd family-assistant
git diff --stat
```

## Ship Criteria

Phase 1 is ready when all of these are true:

- the transcript never silently drops assistant outcomes
- trust rows are persisted, reload-safe, and compact
- evidence panel content comes from stored annotations, not regenerated guesses
- summary and durable fact memory are canonical in Postgres
- Chroma is only retrieval support
- `web_search` + `web_fetch` are the only research tools in play
- tests cover success, failure, reload, and budget edges
- the UI matches [DESIGN.md](/Users/stuartlangley/src/sjlangley/family-assistant/DESIGN.md)

## After This Ships

Then, and only then:

- revisit true streaming/live stage updates
- revisit image generation as phase 1.5
- start phase 2 Google Drive genealogy ingestion and WikiTree photo workflows
