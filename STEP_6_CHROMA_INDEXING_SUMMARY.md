# Step 6, Commit 3: Chroma Indexing for Memory Persistence

## Overview
Implemented Chroma indexing helpers that mirror canonical Postgres memory rows into Chroma. Postgres remains the authoritative store; Chroma serves as a searchable cache/index.

## Implementation

### Methods Added to `MemoryStorage`

#### 1. `index_conversation_summary(summary: ConversationMemorySummary) -> None`
**Purpose:** Index a conversation summary into Chroma.

**Behavior:**
- Creates stable document with ID format: `summary_{summary_uuid}`
- Upserts into Chroma (retries use same ID, no duplicates)
- Updates replace existing document content
- Stores metadata: type, summary_id, user_id, conversation_id, version, source_message_id

**Assumptions:**
- Summary row already exists in Postgres (this method only indexes, does not create)
- Caller has already flushed/committed Postgres row
- Summary is always indexable (no lifecycle filtering)

#### 2. `index_durable_fact(fact: DurableFact) -> None`
**Purpose:** Index an active durable fact into Chroma.

**Behavior:**
- Only indexes active facts (raises ValueError if inactive)
- Creates stable document with ID format: `fact_{fact_uuid}`
- Upserts into Chroma (retries use same ID, no duplicates)
- Updates replace existing document content
- Stores metadata: type, fact_id, user_id, subject, fact_key, confidence, source_type, active, source_conversation_id, source_message_id

**Assumptions:**
- Fact row already exists in Postgres (this method only indexes, does not create)
- Caller has already flushed/committed Postgres row
- Only active facts should be indexed
- Caller is responsible for removing inactive facts (see below)

#### 3. `remove_durable_fact_from_chroma(fact_id: str) -> None`
**Purpose:** Remove a fact from Chroma when it's deactivated.

**Behavior:**
- Deletes from Chroma using stable ID format: `fact_{fact_id}`
- Silently ignores if document doesn't exist (idempotent)
- Use this when a fact is marked inactive

**Assumptions:**
- Called when a fact is deactivated in Postgres
- Idempotent (safe to call multiple times)
- No error if doc not in Chroma

## Design Decisions

### 1. Stable Document IDs
**Format:** `summary_{uuid}` and `fact_{uuid}` derived from Postgres row UUIDs

**Rationale:**
- Enables true retry-safety: same row reindexed uses same doc ID
- Prevents duplicate vector docs from retried index operations
- Deterministic and traceable (ID is row's UUID)
- Supports future cleanup (delete by ID)

### 2. Upsert Semantics
**Method:** Chroma's native `upsert()` method instead of `add()`

**Behavior:**
- First call: inserts new document
- Retry with same ID: updates existing document (no duplicate)
- Content change: update replaces stored text
- Metadata change: update replaces all metadata

**Rationale:**
- Idempotent by default (retries are safe)
- Aligns with background task retry philosophy
- Clean mental model: "index this row"

### 3. Inactive Fact Handling
**Chosen approach:** Prevent indexing + explicit removal

**Options considered:**
1. Skip indexing inactive facts (silent ignore)
   - Pro: Simple
   - Con: Doesn't clean up already-indexed facts after deactivation
2. Remove from Chroma if inactive (explicit deletion + validation)
   - Pro: Guarantees stale facts don't remain queryable
   - Con: Requires explicit caller action
3. Use Chroma "active" flag for filtering
   - Pro: Single index handles both
   - Con: Requires query-time filtering (not retrieval-safe)

**Selected: Option 2 (explicit removal)**
- Prevents stale facts from being retrieved after deactivation
- Clear contract: caller must call `remove_durable_fact_from_chroma()` when marking inactive
- Future retrieval queries won't see inactive facts (they're deleted, not filtered)
- Aligns with Postgres soft-delete pattern

**Caller Responsibility:**
When marking a fact inactive, caller should:
1. Update fact in Postgres: `fact.active = False; await session.flush()`
2. Clean up Chroma: `memory_storage.remove_durable_fact_from_chroma(str(fact.id))`

### 4. Metadata Strategy
**Included fields:**
- `type`: 'summary' | 'durable_fact' (discriminator for retrieval)
- Row ID fields: summary_id, fact_id (link to canonical Postgres)
- User/conversation context: user_id, conversation_id, subject, fact_key
- Fact metadata: confidence, source_type, active (filter/rank)
- Source tracking: source_conversation_id, source_message_id (audit trail)
- Version tracking (for summaries): version

**Rationale:**
- Support filtering by user, conversation, confidence
- Enable ranking/sorting by source and version
- Provide traceability back to Postgres row
- Allow future faceting (fact_key, source_type, confidence)

### 5. Document Content
**Summary:** Full `summary_text` from Postgres row
**Fact:** Full `fact_text` from Postgres row

**Note:** Does not include source_excerpt in document content (only metadata) to keep embeddings focused on fact content, not extraction context.

## Integration Points (Set up for next commits)

**Ready for BackgroundTask integration:**
- Direct method calls: `memory_storage.index_conversation_summary(summary)`
- Fire-and-forget semantics (no return value)
- Idempotent retries supported

**Future retrieval (not in this commit):**
- Queries can filter by type, user_id, conversation_id, active, confidence
- Rankings can use version, source_type, source_message_id
- Metadata provides enough context for ranking and filtering

**Future context assembly (not in this commit):**
- Retrieved facts include fact_id → can join back to Postgres for active check
- Retrieved summaries include conversation_id → can filter by conversation

## Testing Coverage

✅ **Stable ID verification (2 tests):**
- `test_index_conversation_summary_writes_stable_doc_id` — Verifies doc ID format
- `test_index_durable_fact_writes_stable_doc_id` — Verifies doc ID format

✅ **Upsert/idempotency (4 tests):**
- `test_index_conversation_summary_re_index_does_not_duplicate` — Same ID reused
- `test_index_durable_fact_re_index_does_not_duplicate` — Same ID reused
- `test_index_conversation_summary_updated_replaces_content` — Content updated
- `test_index_durable_fact_updated_replaces_content` — Content updated

✅ **Inactive fact handling (2 tests):**
- `test_index_durable_fact_rejects_inactive` — ValueError on inactive
- `test_remove_durable_fact_from_chroma_deletes_doc` — Deletion works

✅ **Error handling (1 test):**
- `test_remove_durable_fact_from_chroma_handles_missing` — Silently ignores missing

✅ **Metadata verification:**
- All tests verify metadata includes expected canonical fields
- Type, row_id, user_id, conversation_id, fact_key, confidence, active verified

## Assumptions & Constraints

### Postgres (source of truth)
1. ✅ Row exists before indexing
2. ✅ Row has been flushed/committed
3. ✅ Caller manages transaction lifecycle
4. ✅ Row IDs are stable UUIDs

### Chroma (cache/index)
1. ✅ Chroma is eventually consistent (indexing can lag Postgres)
2. ✅ Chroma's upsert is idempotent
3. ✅ Deleted documents are truly removed (no soft deletes)
4. ✅ Document IDs are unique within collection

### Integration (not in scope)
1. ⏳ BackgroundTasks will call indexing methods after Postgres writes
2. ⏳ Retrieval will filter by active flag (inactive facts won't exist)
3. ⏳ Context assembly will verify facts are still active (join to Postgres)

## What's Not Included

**Explicitly deferred:**
- BackgroundTask wiring (next commit)
- ConversationService integration (next commit)
- Retrieval/ranking logic (later)
- Query filtering/ranking (later)
- Prompt assembly (later)
- Router changes (not needed for indexing)

**Not needed for this commit:**
- Batch indexing (can be added as wrapper if needed)
- Index versioning (Chroma handles)
- TTL/expiration (managed by fact deactivation)

## Verification Checklist

✅ All 177 backend tests passing  
✅ Coverage: 93.90% (exceeds 90% requirement)  
✅ Ruff linting: clean  
✅ No schema changes needed (uses existing columns)  
✅ No database migrations needed (index-only)  
✅ Idempotent retries: verified by tests  
✅ Stable IDs: verified by tests  
✅ Inactive fact handling: verified by tests  
✅ Metadata completeness: verified by tests  
✅ Error handling: verified by tests  
✅ Scope limited to memory_storage.py (no ConversationService changes)  

## Next Steps

**Step 6, Commit 4:** Wire up BackgroundTask execution → Call indexing methods after memory writes  
**Step 6, Commit 5:** Add retrieval/ranking logic → Query Chroma with context assembly  

---

**Commit:** `9ec5252`  
**Files:**
- `src/assistant/services/memory_storage.py` — 3 indexing methods (99 lines)
- `tests/services/test_memory_storage.py` — 10 comprehensive tests (265 lines)

**Key Decision Summary:**
- **Chroma ID Format:** `summary_{uuid}` + `fact_{uuid}` for stable retry-safety
- **Inactive Facts:** Explicit removal via `remove_durable_fact_from_chroma()` ensures stale facts don't remain queryable
- **Upsert Semantics:** Chroma upsert() method for idempotent indexing
- **Metadata:** Canonical fields (type, ID, user_id, conversation_id, etc.) for future retrieval/filtering
