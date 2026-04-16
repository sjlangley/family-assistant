# Step 6 Continuation: ContextAssemblyService Improvements

## Overview

Upgraded ContextAssemblyService to reuse saved summaries and durable facts more effectively. Implemented relevance-based fact selection that prefers facts whose subjects appear in recent conversation turns over purely recency-based selection.

**Key principle:** Postgres remains canonical; Chroma is reserved for future retrieval-only use.

---

## Implementation Summary

### 1. Extended ContextAssemblyResult with Selection Metadata

**File:** `src/assistant/services/context_assembly.py`

Added three new optional fields to track and understand fact selection:

```python
@dataclass
class ContextAssemblyResult:
    messages: list[dict]  # Final prepared message list for LLM
    used_summary: bool  # Whether a saved summary was used
    summary_id: uuid.UUID | None  # ID of the summary if used
    fact_ids: list[uuid.UUID]  # IDs of durable facts included
    candidate_fact_ids: list[uuid.UUID] = None  # All candidate facts considered
    selection_method: str = 'recency'  # How facts were selected: 'relevance', 'recency', or 'chroma'
```

**Purpose:** Enables tests and debugging to verify exactly how facts were selected and from which pool of candidates.

---

### 2. Improved Fact Selection with Relevance Ranking

**File:** `src/assistant/services/context_assembly.py`

Replaced simple recency-based fact loading with intelligent ranking in `_load_active_facts()`:

#### Selection Strategy

1. **Load candidate pool** (first `MAX_FACT_CANDIDATES=15` active facts, ordered by recency)
   - Keeps memory usage bounded even with large fact databases
   - Maintains Postgres as canonical source (no Chroma involved)

2. **Rank candidates by relevance** (if recent turns exist)
   - Extract all words from each fact's subject (e.g., "George Langley" → ["george", "langley"])
   - Check if any subject word appears in recent message content
   - Separate facts into:
     - `relevant_facts`: subjects with matching words
     - `remaining_facts`: others (ordered by recency)

3. **Select top N facts**
   - Return: `relevant_facts + remaining_facts` limited to `MAX_DURABLE_FACTS=5`
   - If relevant facts found: return with `selection_method='relevance'`
   - Otherwise: return with `selection_method='recency'`

#### Key Properties

- **Case-insensitive matching**: "George Langley" matches "george" in recent content
- **Word-based not substring-based**: Prevents "George" requiring "George ..." as substring
- **Recency as tiebreaker**: Among relevant facts, newer ones appear first
- **Canonical resolution**: Selected facts always come from Postgres rows
- **Graceful degradation**: Falls back to recency when no relevant facts exist
- **Deterministic**: Same ordering given same input (sorted by updated_at DESC)

#### Example Flow

```
Recent turn: "Tell me about George and his family"
Facts in DB:
  - Mary Smith (recent, not relevant)
  - George Langley (old, relevant)
  - Alice Jones (very old, not relevant)

Selection Process:
  1. Load candidates (ordered by update): [Mary, George, Alice]
  2. Extract words: George→["george", "langley"], Mary→["mary", "smith"], Alice→["alice", "jones"]
  3. Check relevance: "george" or "langley" in content? YES
  4. Separate: relevant=[George], remaining=[Mary, Alice]
  5. Result: [George, Mary, Alice] but limited to 5 facts
  6. Return: [George, Mary, Alice], selection_method='relevance'
```

---

### 3. Updated assemble_context() to Support Ranking

**File:** `src/assistant/services/context_assembly.py`

Reordered operations in `assemble_context()` to enable relevance ranking:

```python
# OLD ORDER
1. Load summary
2. Load facts (no context)
3. Load recent turns
4. Build messages

# NEW ORDER
1. Load summary
2. Load recent turns FIRST (needed for ranking context)
3. Load facts WITH recent_turns parameter (for ranking)
4. Build messages
```

This allows fact selection to see the conversation context it's being selected for.

---

### 4. New Initialization Parameter for Future Chroma Support

**File:** `src/assistant/services/context_assembly.py`

Added optional `memory_storage` parameter to `ContextAssemblyService.__init__()`:

```python
def __init__(self, memory_storage: 'MemoryStorage | None' = None) -> None:
    """Initialize ContextAssemblyService.

    Args:
        memory_storage: Optional MemoryStorage for Chroma-assisted ranking
                       (reserved for future use, not used in current version)
    """
    self.memory_storage = memory_storage
```

**Purpose:** Creates a clean seam for adding Chroma-assisted ranking in the future without refactoring the service. Currently unused; ready for enhancement.

**File:** `src/assistant/services/__init__.py`

Updated dependency injection to pass MemoryStorage (reserved for future):

```python
@lru_cache(maxsize=1)
def get_context_assembly_service() -> ContextAssemblyService:
    """Return a lazily initialized singleton instance of ContextAssemblyService."""
    return ContextAssemblyService(memory_storage=get_memory_storage())
```

---

### 5. Comprehensive Test Coverage

**File:** `tests/services/test_context_assembly_service.py`

Added 7 new tests covering the improvement:

1. **test_fact_selection_prefers_relevant_over_recent**
   - Verifies relevant facts are preferred when space is constrained
   - Only includes relevant fact despite newer irrelevant facts existing

2. **test_fact_selection_fallback_to_recency**
   - Confirms fallback to recency when no relevant facts match
   - Ensures we don't break when subjects don't appear in recent turns

3. **test_fact_selection_uses_postgres_canonical_rows**
   - Validates selected facts come from Postgres (not Chroma or elsewhere)
   - Checks fact IDs correspond to actual database rows
   - Verifies fact content appears correctly in prompt

4. **test_fact_selection_prefers_multiple_relevant_facts**
   - When multiple facts are relevant, uses recency as tiebreaker
   - Confirms newest relevant facts appear first

5. **test_fact_selection_case_insensitive_matching**
   - Subject matching works with different case than recent content
   - "George Langley" matches "george" in "What about george?"

6. **test_fact_selection_new_conversation_uses_recency**
   - New conversations (no prior turns) use recency selection
   - Falls back gracefully when there's no context to rank against

7. **test_fact_selection_respects_max_candidates_limit**
   - Confirms we load bounded candidate pool (MAX_FACT_CANDIDATES=15)
   - Returns only MAX_DURABLE_FACTS (5) to the prompt

**Query constants updated in imports:**
- Added `MAX_FACT_CANDIDATES` to test imports for validation

---

## Budget Transparency

### Query Budget Constants

```python
MAX_RECENT_MESSAGES_WITH_SUMMARY = 4    # Recent turns when summary exists
MAX_RECENT_MESSAGES_NO_SUMMARY = 8      # Recent turns when no summary
MAX_DURABLE_FACTS = 5                   # Maximum facts in prompt
MAX_FACT_CANDIDATES = 15                # Candidate pool size for ranking
MAX_FACT_TEXT_LENGTH = 200              # Truncation limit per fact
MAX_SUMMARY_TEXT_LENGTH = 1000          # Truncation limit for summary
```

**Design rationale:**
- `MAX_FACT_CANDIDATES=15`: 3x the final count allows meaningful ranking
- `MAX_DURABLE_FACTS=5`: Keeps prompt compact while giving enough context
- Explicit constants make budget behavior testable and auditable

---

## Backward Compatibility

### API Changes

✅ **No breaking changes to external API:**
- `assemble_context()` signature unchanged
- `assemble_context_new_conversation()` signature unchanged
- Both methods continue returning `ContextAssemblyResult`
- Response messages format unchanged

✅ **Extended ContextAssemblyResult fields are optional:**
- `candidate_fact_ids` defaults to empty list
- `selection_method` defaults to 'recency'
- Existing code using `result.fact_ids` and `result.used_summary` works unchanged

---

## Scope Boundaries (Maintained)

✅ **Did not change:**
- Postgres schema (no migrations needed)
- Router endpoints
- Frontend code
- MemoryStorage indexing behavior
- Conversation model contract

✅ **Clean seams created for future work:**
- `memory_storage` parameter ready for Chroma-assisted ranking
- `selection_method` tracking ready for observability
- `candidate_fact_ids` ready for debugging/tracing

---

## Decision: Why Postgres-Only Relevance (Not Chroma Yet)

### What We Chose
Word-based relevance ranking on Postgres (no Chroma involvement)

### Why
1. **Simplicity**: Eliminates Chroma roundtrip, network latency, and potential mismatch failures
2. **Determinism**: Exact word matching is reproducible and testable
3. **Reliability**: Does not depend on Chroma availability or correctness
4. **Foundation**: Postgres-only relevance is solid baseline
5. **Clean seam**: `memory_storage` parameter ready when Chroma ranking is desired

### What Chroma Could Do Later
When added in a future step, Chroma could:
1. Use `memory_storage.query_memory(user_id, query)` to find semantic candidates
2. Match returned fact texts back to canonical Postgres rows
3. Use as input to ranking algorithm alongside word-based matching
4. Fall back to word-based ranking if Chroma results don't resolve cleanly

**Current state is honest:** It works with today's data, is fully testable, and doesn't overpromise on retrieval features.

---

## Test Results

```
197 passed, 11 warnings in 4.04s
Coverage: 91.65% (exceeds 90% requirement)
ContextAssemblyService coverage: 100%
All existing tests continue to pass
```

**New test file lines:** 18 tests (11 existing + 7 new)

---

## Files Modified

1. **src/assistant/services/context_assembly.py** (+123 lines)
   - Extended ContextAssemblyResult with selection metadata
   - Improved _load_active_facts() with relevance ranking
   - Reordered assemble_context() to support ranking
   - Added memory_storage parameter for seam

2. **src/assistant/services/__init__.py** (1 line changed)
   - Pass memory_storage to ContextAssemblyService constructor

3. **tests/services/test_context_assembly_service.py** (+200 lines)
   - 7 new comprehensive tests for relevance selection
   - Updated imports to include MAX_FACT_CANDIDATES

---

## Next Steps

### Step 7: API Contract Updates (Not in this commit)
- Return `annotations` on assistant messages
- Preserve backward compatibility
- Update frontend types

### Future Enhancement: Chroma-Assisted Ranking
When implementing, can reuse:
- `memory_storage` parameter already injected
- `selection_method` tracking in ContextAssemblyResult
- Existing test patterns and budget structure

---

## Summary

This improvement makes ContextAssemblyService a smarter context selector while maintaining full honesty about data sources. Relevance ranking now brings more targeted facts into conversation prompts, improving response quality. The implementation is thoroughly tested, transparent about its constraints, and ready for gradual enhancement.

**Core promises maintained:**
- ✅ Postgres remains canonical
- ✅ Chroma is retrieval support layer (ready to use, not using yet)
- ✅ No schema changes
- ✅ No API breakage
- ✅ Fully verifiable behavior
- ✅ Clear seams for future work
