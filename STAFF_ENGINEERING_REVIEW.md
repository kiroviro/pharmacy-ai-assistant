# Staff Engineering Review
**Project:** Pharmacy AI Assistant
**Date:** February 18, 2026
**Reviewer:** Claude Code (Staff Engineering Review Skill)
**Codebase Size:** 10,579 lines of Python
**Test Count:** 263 tests (196 test functions)
**Test Coverage:** 39% (enforced minimum: 35%)

---

## Executive Summary

**Overall Grade: C+ (70/100)**

The Pharmacy AI Assistant is a **safety-critical medical chatbot** with solid architecture at the pipeline stage level but severe implementation issues at the component level. The codebase shows awareness of good practices (comprehensive docs, test coverage enforcement, security scanning) but suffers from classic mid-stage startup problems: a 3,224-line god object, dual architecture paths doubling maintenance burden, and production quality issues affecting 7% of responses.

**Critical Production Issues:**
- 🚨 **Garbage text in 7% of medical responses** (LLM hallucinations)
- 🚨 **Only 38% of responses include active ingredients** (template compliance failure)
- 🚨 **God object orchestrator** (3,224 LOC, 30% of codebase in one file)

**Strengths:**
- ✅ Strong safety-first design (emergency detection, OTC filtering)
- ✅ Well-documented architecture and technical debt tracking
- ✅ Evidence-based decisions (MLX concurrency validated)
- ✅ Comprehensive E2E testing (352 real queries)

**Top 3 Priorities:**
1. **Fix garbage text hallucinations** (output validation + prompt engineering)
2. **Fix template compliance** (ingredient extraction broken)
3. **Extract god object** (5-week strangler fig pattern)

---

## 🏗️ 1. ARCHITECTURE REVIEW

**Evaluated:**
- System design and component boundaries (7-stage pipeline)
- Dependency graph and coupling (21 modules)
- Data flow patterns (Intent → Translation → MedGemma → RAG → Response)
- Scaling characteristics (single-threaded MLX, 22 req/min max)
- Security architecture (safety layer, rate limiting, input validation)

---

### **Issue #1: God Object Anti-Pattern (Orchestrator Explosion)**

**File:** `src/pipeline/orchestrator.py` — **3,224 lines, 68 methods** in single Pipeline class

The orchestrator is a textbook "god object" that violates Single Responsibility Principle catastrophically. It handles:
- Query routing (comparison vs catalog vs symptom queries)
- Translation coordination
- Medical reasoning orchestration
- Product matching (vector search + LLM refinement)
- Safety checking and contraindication filtering
- Response formatting and template generation
- Ingredient analysis and duplication warnings
- Garbage text filtering

**Impact:**
- **30% of entire codebase** in one file
- New engineer onboarding takes 2+ weeks
- Parallel development blocked (constant merge conflicts)
- PR reviews require reading 500+ line diffs
- Unit testing impossible (can only integration test)
- Debugging extremely difficult (68 methods to trace)
- Test coverage only 9% (orchestrator is hardest to test)

**Option A: Strangler Fig Extraction (Recommended)**
- **Effort:** 5 weeks (incremental, 1 component/week)
- **Risk:** Low (each extraction is separate PR with feature flags)
- **Impact:** Reduces orchestrator from 3,224 → ~800 LOC
- **Maintenance:** Each component independently testable

**Extraction Plan:**
```
Week 1: QueryRouter (~300 LOC) → src/pipeline/query_router.py (already partially exists)
  - Extract: is_catalog_query, is_comparison_query, is_single_drug_query
  - Add unit tests for routing logic

Week 2: ResponseBuilder (~400 LOC) → src/pipeline/response_builder.py (new)
  - Extract: _format_response, _build_product_list, _format_markdown
  - Extract all template formatting logic
  - Add tests for each template section

Week 3: ProductMatcher (~300 LOC) → src/pipeline/product_matcher.py (new)
  - Extract: _search_products, _refine_products, _deduplicate_by_ingredient
  - Add tests for matching algorithms

Week 4: SafetyValidator (~200 LOC) → src/pipeline/safety_validator.py (new)
  - Extract: contraindication filtering, safety message generation
  - Add tests for edge cases

Week 5: IngredientAnalyzer (~250 LOC) → Complete extraction
  - Already partially done in product_ingredients.py
  - Move remaining logic from orchestrator
  - Add comprehensive ingredient parsing tests
```

**Option B: Big Bang Rewrite**
- **Effort:** 3-4 weeks (all at once)
- **Risk:** Very High (everything breaks until done)
- **Impact:** Same as Option A
- **Maintenance:** Risky deployment, hard to rollback

**Option C: Do Nothing**
- **Effort:** None
- **Risk:** Technical debt compounds (will grow beyond 3,500 LOC)
- **Impact:** Continued slow development velocity
- **Maintenance:** Increasingly difficult over time

→ **Recommendation: Option A** — Incremental extraction is safest for production medical system. Each week delivers testable value with rollback capability. Aligns with "engineered enough" preference.

---

### **Issue #2: Parallel Architecture Paths (Double Maintenance)**

**Files:**
- `src/unified_processor.py:1-487` (new LLM-based path, 7 classes)
- `src/intent_classifier.py:1-668` (legacy keyword-based, marked DEPRECATED)
- `src/translator.py:137-166` (query translation - legacy only)
- `src/pipeline/orchestrator.py:79-88` (feature flag: `unified_processor_enabled=False`)

You're maintaining **two complete execution paths**:

**Legacy Path (Current Default):**
1. Intent classifier (keyword matching) →
2. BG→EN translation →
3. MedGemma medical reasoning →
4. Product search

**Unified Path (Disabled):**
1. Single LLM call (intent + translation + reasoning in one shot)

The unified processor is **30% faster** (180ms vs 250ms) but **disabled by default**, meaning you're paying maintenance cost for both but only using one.

**Impact:**
- Every bug fixed twice (once per path)
- Every test covers both paths
- Code reviewers must understand both architectures
- ~1,155 LOC of dual-path overhead

**Option A: Go All-In on Unified Processor (Recommended)**
- **Effort:** 3 days (enable → monitor → remove legacy)
- **Risk:** Medium (30% faster but less debuggable)
- **Impact:** Removes ~800 LOC of legacy code
- **Maintenance:** Single path, simpler codebase

**Migration Plan:**
```
Day 1: Change unified_processor_enabled=True in config.py
       Deploy to staging
       Monitor error rates, latency, VRAM for 24h

Day 2: A/B test accuracy (sample 100 queries)
       Compare with legacy path
       If accuracy < 95% of legacy → rollback

Day 3: Delete intent_classifier.py
       Remove query translation from translator.py (keep response translation)
       Update all tests to unified path
       Remove feature flag
```

**Option B: Delete Unified Processor**
- **Effort:** 2 hours (delete unified_processor.py + refs)
- **Risk:** Low (not used in production)
- **Impact:** Removes ~487 LOC of unused code
- **Maintenance:** Keep proven legacy path

**Option C: Keep Both Indefinitely**
- **Effort:** None now, high ongoing
- **Risk:** Low immediate, high long-term
- **Impact:** Status quo (2x maintenance)
- **Maintenance:** Permanent double work

→ **Recommendation: Option A** — Unified processor is 30% faster with semantic understanding. You built it for a reason. Your TECHNICAL_DEBT.md already recommends this. Either use it or delete it; don't maintain both.

---

### **Issue #3: In-Memory Rate Limiting Won't Scale**

**File:** `api_server.py:44-104` — `rate_limit_store` dict is process-local

Current implementation stores client request timestamps in Python dict. This **breaks horizontal scaling**.

**Attack Scenario:**
```
Rate limit: 30 req/min per IP
Deploy 3 pods → Attacker sends 90 req/min (30 to each pod)
DDoS protection bypassed
```

**Impact:**
- Can't safely scale to multiple instances
- Each pod has separate 30 req/min limit instead of shared global limit
- DDoS protection ineffective in production

**Option A: Redis-Based Rate Limiting (Recommended)**
- **Effort:** 4-6 hours (implementation + testing)
- **Risk:** Low (standard pattern)
- **Impact:** All pods share rate limit state
- **Maintenance:** Requires Redis instance (standard infrastructure)

**Implementation:**
```python
from redis import Redis

redis_client = Redis(host='redis', port=6379, db=0)

def check_rate_limit_redis(client_ip: str) -> bool:
    key = f"rate_limit:{client_ip}"
    now = int(time.time())

    # Sliding window using sorted set
    redis_client.zremrangebyscore(key, 0, now - 60)
    count = redis_client.zcard(key)

    if count >= settings.rate_limit_per_minute:
        return False

    redis_client.zadd(key, {str(now): now})
    redis_client.expire(key, 60)
    return True
```

**Option B: SlowAPI Library**
- **Effort:** 2-3 hours (add dependency + configure)
- **Risk:** Low (battle-tested)
- **Impact:** Automatic distributed rate limiting
- **Maintenance:** Library handles complexity

```python
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

@app.post("/v1/chat/completions")
@limiter.limit("30/minute")
async def chat_completions(...): ...
```

**Option C: Defer Until Scaling**
- **Effort:** None
- **Risk:** Medium (works with 1 instance, blocks scaling)
- **Impact:** Technical debt when multi-pod deployment needed
- **Maintenance:** Will need to do this eventually

→ **Recommendation: Option A** — Redis is standard infrastructure you'll need anyway (caching, sessions). 4-6 hours well spent for a medical app security control. Option B also good but adds abstraction.

---

### **Issue #4: Memory Cleanup Smell (Treating Symptom)**

**File:** `api_server.py:339-357` — Aggressive cleanup after **every request**

Middleware calls `gc.collect()` + `mx.metal.clear_cache()` after each request. This is a **code smell** suggesting VRAM leak somewhere (MLX model, ChromaDB embeddings, or translation models).

**Impact:**
- Wastes CPU on unnecessary garbage collection
- Masks underlying leak instead of fixing root cause
- May hurt performance (GC pauses)
- Unclear if actually necessary or cargo-culted

**Option A: Investigate Root Cause (Recommended)**
- **Effort:** 4-8 hours (memory profiling)
- **Risk:** Medium (may find unfixable MLX issue)
- **Impact:** Remove cleanup if leak fixed, or document why needed
- **Maintenance:** Proper fix vs workaround

**Investigation Plan:**
```python
# tests/memory_profiling.py
import mlx.core as mx
pipeline = get_pipeline()

for i in range(100):
    result = pipeline.process("имам главоболие")
    stats = mx.metal.device_info()
    print(f"Request {i}: VRAM = {stats.get('memory_used_mb')} MB")
    # Don't clear cache - measure accumulation

# Identify leak source:
# - MLX model layers?
# - ChromaDB embeddings?
# - Translation models?
# - Tensor allocations?
```

**Then:**
- If MLX bug: Report upstream, keep workaround with detailed comment
- If our code: Fix leak, remove aggressive cleanup
- If unavoidable: Document with evidence

**Option B: Document and Keep**
- **Effort:** 15 minutes (add detailed comment)
- **Risk:** None
- **Impact:** Status quo with explanation
- **Maintenance:** Future engineers know it's intentional

**Option C: Remove and Monitor**
- **Effort:** 5 minutes (delete + deploy)
- **Risk:** High (may cause OOM crash)
- **Impact:** Cleaner code or production incident
- **Maintenance:** Risky production experiment

→ **Recommendation: Option A** — Medical system needs 24/7 uptime. 4-8 hours to understand memory profile is worth it. You "err on handling edge cases," so investigate properly before deciding.

---

### Architecture Summary

**Strengths:**
✅ Well-documented (ARCHITECTURE.md comprehensive)
✅ Safety-first design (emergency detection, OTC filtering)
✅ Evidence-based decisions (MLX concurrency validated)
✅ Clear pipeline stage separation
✅ Technical debt tracked (TECHNICAL_DEBT.md)

**Weaknesses:**
❌ God object catastrophe (3,224 LOC orchestrator)
❌ Dual architecture paths (double maintenance)
❌ Scaling blockers (in-memory rate limiting)
❌ Memory management unclear (aggressive cleanup smell)

**Health Grade:** **C+** (70/100) — Matches existing TECHNICAL_DEBT.md assessment

---

## 🔧 2. CODE QUALITY REVIEW

**Evaluated:**
- Code organization and module structure
- DRY violations (your top priority)
- Error handling and edge cases
- Technical debt hotspots
- Over/under-engineering patterns

---

### **Issue #5: 21 Print Statements in Production Code**

**Files:** Found across `src/` directory

Production code contains **21 print() statements** instead of proper logging. This violates structured logging best practices.

**Impact:**
- Logs lost in production (stdout not captured)
- No structured log analysis (can't query/filter)
- Missing context (request ID, timestamps)
- Debug prints left by accident

**Examples:**
```bash
$ grep -r "print(" src/ --include="*.py" | wc -l
21
```

**Option A: Convert All to logger.debug() (Recommended)**
- **Effort:** 1 hour (find-replace + test)
- **Risk:** None
- **Impact:** All output goes through structured logging
- **Maintenance:** Consistent logging pattern

```python
# BEFORE
print(f"Processing query: {query}")

# AFTER
logger.debug("Processing query", extra={"query": query})
```

**Option B: Delete Debug Prints**
- **Effort:** 30 minutes
- **Risk:** Low (if they're just debug prints)
- **Impact:** Cleaner code
- **Maintenance:** None needed

**Option C: Keep Status Quo**
- **Effort:** None
- **Risk:** Low immediate, high in production
- **Impact:** Continued ad-hoc logging
- **Maintenance:** Technical debt accumulates

→ **Recommendation: Option A** — You have excellent structured logging (`logging_config.py`). Use it consistently. 1 hour to convert all prints is worth it.

---

### **Issue #6: DRY Violation - Duplicate LLM Generation Code**

**Files:**
- `src/medical_model.py:454-490` (generate method)
- `src/unified_processor.py:250-290` (generate method)

Both medical_model and unified_processor have **nearly identical LLM generation logic**:

```python
# DUPLICATED PATTERN (appears twice):
generate(
    model=self.model,
    tokenizer=self.tokenizer,
    prompt=prompt,
    max_tokens=max_tokens,
    sampler=sampler,
    # ... same error handling, logging, timing
)
```

**Impact:**
- Bug fixes must be applied twice
- Feature additions (streaming, retries) duplicated
- ~50 LOC duplicated
- Violates DRY aggressively (your top priority)

**Option A: Extract Shared LLM Wrapper (Recommended)**
- **Effort:** 2-3 hours (extract + refactor + test)
- **Risk:** Low (well-defined interface)
- **Impact:** Single source of truth for LLM calls
- **Maintenance:** Fix bugs once, add features once

```python
# src/llm_wrapper.py (NEW)
class MLXGenerator:
    def __init__(self, model_path: str):
        self.model, self.tokenizer = load(model_path)

    def generate(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
        operation_name: str = "generation"
    ) -> str:
        # Single implementation of:
        # - Sampler creation
        # - Generation call
        # - Error handling
        # - Timing/logging
        # - Response cleanup
        pass

# USAGE:
# medical_model.py
self.generator = MLXGenerator(model_path)
response = self.generator.generate(prompt, max_tokens=500)

# unified_processor.py
self.generator = MLXGenerator(model_path)
response = self.generator.generate(prompt, max_tokens=1200)
```

**Option B: Keep Duplicated**
- **Effort:** None
- **Risk:** Medium (bugs/features need double implementation)
- **Impact:** Status quo
- **Maintenance:** Ongoing duplication cost

→ **Recommendation: Option A** — This is a textbook DRY violation. You flagged DRY as top priority. Extract shared wrapper.

---

### **Issue #7: 7 Classes in unified_processor.py**

**File:** `src/unified_processor.py` — 7 classes in 487-line file

File contains: `IntentResult`, `SafetyResult`, `ExtractionResult`, `ReasoningResult`, `UnifiedProcessorResult`, `ProcessorCache`, `UnifiedProcessor`

**Impact:**
- Violates Single Responsibility at file level
- Hard to find specific dataclass definitions
- Mixes data models with business logic
- Import pollution (`from unified_processor import ...` unclear what's available)

**Option A: Split into models.py + processor.py (Recommended)**
- **Effort:** 1 hour (move + update imports)
- **Risk:** None (mechanical refactor)
- **Impact:** Clear separation of data models vs logic
- **Maintenance:** Easier to find/modify dataclasses

```python
# src/unified_processor/models.py (NEW)
@dataclass
class IntentResult: ...
@dataclass
class SafetyResult: ...
@dataclass
class ExtractionResult: ...
@dataclass
class ReasoningResult: ...
@dataclass
class UnifiedProcessorResult: ...

# src/unified_processor/processor.py
class ProcessorCache: ...
class UnifiedProcessor: ...

# src/unified_processor/__init__.py
from .models import UnifiedProcessorResult
from .processor import UnifiedProcessor, get_unified_processor
```

**Option B: Extract Just Data Models**
- **Effort:** 30 minutes
- **Risk:** None
- **Impact:** Partial improvement
- **Maintenance:** Better than status quo

**Option C: Keep As-Is**
- **Effort:** None
- **Risk:** Low (works fine)
- **Impact:** Continued mild confusion
- **Maintenance:** None needed

→ **Recommendation: Option A** — 1 hour to properly organize. Aligns with "bias toward explicit over clever."

---

### **Issue #8: No Docstrings in Orchestrator God Object**

**File:** `src/pipeline/orchestrator.py` — 68 methods, minimal documentation

The 3,224-line orchestrator has **68 methods** but sparse docstrings. Many complex methods lack documentation:

```python
def _refine_product_selection(self, ...):
    # NO DOCSTRING - what does this do?
    # How does deduplication work?
    # What's the algorithm?
    selected = self.medical_model.refine_product_selection(...)
    deduplicated = self._deduplicate_by_ingredient(selected, max_products)
    ...

def _deduplicate_by_ingredient(self, ...):
    # NO DOCSTRING - dedup algorithm unclear
    # Why two passes?
    # What's the priority order?
    ...
```

**Impact:**
- New engineers can't understand code without reading implementation
- No clear contracts for methods
- Debugging requires tracing through code
- Refactoring risky (unclear what methods guarantee)

**Option A: Add Docstrings During God Object Extraction (Recommended)**
- **Effort:** Included in 5-week extraction plan
- **Risk:** None (natural part of refactoring)
- **Impact:** Each extracted component gets proper docs
- **Maintenance:** Documentation debt paid during refactor

**Option B: Add Docstrings Now**
- **Effort:** 8-12 hours (68 methods × 10 min each)
- **Risk:** Low (pure documentation)
- **Impact:** Better immediate understanding
- **Maintenance:** Still have god object

**Option C: Leave Undocumented**
- **Effort:** None
- **Risk:** High (tribal knowledge)
- **Impact:** Continued confusion
- **Maintenance:** Onboarding stays slow

→ **Recommendation: Option A** — Don't document the god object; refactor it. Add docs to extracted components as you go. More efficient use of time.

---

### Code Quality Summary

**Strengths:**
✅ Ruff linting enabled with security checks
✅ Consistent naming conventions
✅ Type hints used in many places
✅ Error handling generally present

**Weaknesses:**
❌ God object dominates codebase
❌ DRY violations (duplicate LLM generation)
❌ 21 print statements in production code
❌ 7 classes in single unified_processor.py file
❌ Sparse documentation in complex code

**Health Grade:** **C** (65/100) — Decent foundation but major violations

---

## 🧪 3. TEST REVIEW

**Evaluated:**
- Test coverage gaps (currently 39%)
- Test quality and assertion strength
- Missing edge case coverage
- Untested failure modes

---

### **Issue #9: Orchestrator God Object Barely Tested (9% Coverage)**

**File:** `src/pipeline/orchestrator.py` — **9% test coverage** for 3,224-line file

The largest, most complex file has the **lowest test coverage**:

```
Coverage by component:
✅ Unified Processor: 92%
✅ Query Router: 91%
✅ Intent Classifier: 92%
✅ Safety Layer: 77%
⚠️ Medical Model: 59%
🔴 Orchestrator: 9%  ← CRITICAL GAP
🔴 Product Store: 18%
```

**Impact:**
- Critical business logic untested
- Refactoring extremely risky (no safety net)
- Bugs caught in production, not CI
- 68 methods × minimal testing = high regression risk

**Why So Low?**
- God object hard to unit test (requires mocking 10+ dependencies)
- Only integration tests exist (slow, brittle)
- Developers avoid writing tests for complex code

**Option A: Fix Via God Object Extraction (Recommended)**
- **Effort:** Included in 5-week extraction plan
- **Risk:** None (part of refactoring)
- **Impact:** Each extracted component gets 80%+ coverage
- **Maintenance:** Natural outcome of good architecture

**Example:**
```python
# BEFORE: Can't test in isolation (requires entire pipeline)
def test_orchestrator():
    pipeline = Pipeline()  # Loads 5 models, ChromaDB, etc.
    result = pipeline.process("query")
    assert ...  # Integration test only

# AFTER: Easy to unit test
def test_product_matcher():
    matcher = ProductMatcher()
    candidates = [mock_product1, mock_product2]
    result = matcher.refine(candidates, query="headache")
    assert result[0].title == "Aspirin"
    assert len(result) == 3
```

**Option B: Write Tests for Orchestrator As-Is**
- **Effort:** 2-3 weeks (test 68 methods)
- **Risk:** High (mocking complexity, brittle tests)
- **Impact:** Better coverage but still have god object
- **Maintenance:** Tests break often due to coupling

**Option C: Accept Low Coverage**
- **Effort:** None
- **Risk:** Very High (production bugs)
- **Impact:** Status quo
- **Maintenance:** Rely on E2E tests only

→ **Recommendation: Option A** — Don't test the god object; refactor it. Write tests for extracted components. Much easier and higher value.

---

### **Issue #10: Product Store Barely Tested (18% Coverage)**

**File:** `src/product_store.py` — **18% coverage** for 700-line file

Critical RAG component with ChromaDB integration has minimal tests:

**Untested Areas:**
- Hybrid search algorithm (keyword boosting + vector similarity)
- Homeopathy filtering (important for medical safety)
- Category-aware search
- Async wrappers
- Error handling (ChromaDB failures)

**Impact:**
- Changes to search algorithm untested
- Can't confidently refactor
- Vector search bugs caught by users, not CI

**Option A: Add Comprehensive Product Store Tests (Recommended)**
- **Effort:** 4-6 hours (test suite)
- **Risk:** None
- **Impact:** Coverage 18% → 75%+
- **Maintenance:** Safe to modify search algorithms

**Test Plan:**
```python
# tests/test_product_store.py (expand existing)

def test_hybrid_search_keyword_boost():
    """Exact keyword match should boost similarity score."""
    store = ProductStore()
    results = store.hybrid_search("парацетамол", n_results=10)

    # Products with "парацетамол" in title should rank higher
    assert "парацетамол" in results[0]["title"].lower()
    assert results[0]["distance"] < results[-1]["distance"]

def test_homeopathy_filtering():
    """Homeopathic products should be filtered out."""
    # Add test homeopathic product to store
    # Search should exclude it
    ...

def test_category_aware_search():
    """Treatment category should narrow search."""
    # Fever query should prioritize antipyretics
    ...

def test_async_search():
    """Async wrapper should work correctly."""
    ...
```

**Option B: Defer Until Refactoring**
- **Effort:** None now
- **Risk:** Medium (works in production)
- **Impact:** Technical debt
- **Maintenance:** Eventual need

**Option C: Keep Minimal Coverage**
- **Effort:** None
- **Risk:** High (critical RAG component)
- **Impact:** Status quo
- **Maintenance:** E2E tests only

→ **Recommendation: Option A** — Product search is core functionality. 4-6 hours to test thoroughly is worth it. You prefer "too many tests than too few."

---

### **Issue #11: No Edge Case Tests for Safety Layer**

**File:** `src/safety.py` — 77% coverage, but **missing critical edge cases**

Safety layer has good coverage but lacks edge case tests:

**Missing Tests:**
```python
# Edge case: Multiple emergency symptoms
def test_multiple_emergency_symptoms():
    """Should detect highest severity when multiple present."""
    query = "гръдна болка и припадък"  # chest pain + fainting
    result = safety_layer.check(query)
    assert result.severity == "emergency"
    assert len(result.matched_symptoms) == 2

# Edge case: Misspelled emergency symptoms
def test_misspelled_emergency_symptom():
    """Should detect common misspellings of 'гръдна болка'."""
    result = safety_layer.check("гръднаболка")  # no space
    assert result.severity == "emergency"

# Edge case: Emergency symptom in longer query
def test_emergency_buried_in_text():
    """Emergency symptom should be detected even with extra context."""
    query = "Имам силна гръдна болка от тази сутрин и ме боли много"
    result = safety_layer.check(query)
    assert result.severity == "emergency"

# Edge case: False positive check
def test_no_false_positive_on_heartburn():
    """'Парене в гърдите' (heartburn) should NOT trigger chest pain."""
    result = safety_layer.check("парене в гърдите")
    assert result.severity != "emergency"
```

**Impact:**
- Edge cases caught in production (E2E tests found some)
- Medical safety relies on comprehensive testing
- Misspellings or variations might miss detection

**Option A: Add Safety Edge Case Suite (Recommended)**
- **Effort:** 3-4 hours (20-30 edge case tests)
- **Risk:** None
- **Impact:** Coverage 77% → 90%+, better safety guarantees
- **Maintenance:** Explicit documentation of safety behavior

**Option B: Rely on E2E Tests**
- **Effort:** None
- **Risk:** Medium (E2E tests don't cover all variations)
- **Impact:** Status quo
- **Maintenance:** Slower test feedback

→ **Recommendation: Option A** — Safety-critical medical app. You "err on side of handling more edge cases." 3-4 hours for comprehensive safety tests is mandatory.

---

### **Issue #12: E2E Test Monolith (1,628 Lines)**

**File:** `e2e_query_tests.py` — 1,628 lines in single file

E2E test file is **larger than most production modules**:

```
Codebase size comparison:
- medical_model.py: 959 LOC
- translator.py: 784 LOC
- e2e_query_tests.py: 1,628 LOC ← LARGER THAN CORE MODULES
```

**Impact:**
- Hard to navigate (which tests cover what?)
- Slow to run subset (must run all or none)
- Difficult to organize test data
- Merge conflicts frequent

**Option A: Split by Category (Recommended)**
- **Effort:** 3-4 hours (mechanical split)
- **Risk:** None (preserve all test names)
- **Impact:** 5 organized files vs 1 monolith
- **Maintenance:** Easier to find/modify tests

```bash
# BEFORE
e2e_query_tests.py (1,628 LOC)

# AFTER
tests/e2e/
  ├── test_medication_queries.py   (~400 LOC)
  ├── test_symptom_queries.py      (~400 LOC)
  ├── test_safety_queries.py       (~300 LOC)
  ├── test_catalog_queries.py      (~300 LOC)
  └── test_edge_cases.py           (~228 LOC)
```

**Option B: Keep Monolith**
- **Effort:** None
- **Risk:** Low (works fine)
- **Impact:** Continued navigation difficulty
- **Maintenance:** Status quo

→ **Recommendation: Option A** — Already flagged in TECHNICAL_DEBT.md as Issue #7. 3-4 hours for better organization.

---

### Test Review Summary

**Strengths:**
✅ 263 tests (196 test functions) — good quantity
✅ Coverage enforcement (35% minimum in CI)
✅ E2E quality tests with 352 real queries
✅ Well-tested components: unified_processor (92%), query_router (91%), intent_classifier (92%)

**Weaknesses:**
❌ Orchestrator barely tested (9% coverage)
❌ Product store undertested (18% coverage)
❌ Missing safety edge cases
❌ E2E test monolith (1,628 LOC)
❌ Overall coverage only 39% (target: 80%)

**Health Grade:** **C+** (72/100) — Quantity good, quality mixed, coverage gaps critical

---

## ⚡ 4. PERFORMANCE REVIEW

**Evaluated:**
- Response time characteristics (avg 7.3s, max 49s)
- N+1 query patterns (no SQL, but ChromaDB)
- Memory usage patterns
- Caching effectiveness

---

### **Issue #13: Performance Outliers (49-Second Responses)**

**Source:** E2E quality tests (352 queries)

**Performance Metrics:**
- **Average:** 7.3 seconds (acceptable for AI chatbot)
- **Minimum:** 89ms (cached response)
- **Maximum:** 49.3 seconds ⚠️ (unacceptable)
- **P99:** Unknown (not measured)

**Impact:**
- Users experience timeout frustration on outliers
- Inconsistent user experience
- May hit frontend/load balancer timeouts (typically 30s)

**Investigation Needed:**
```python
# What causes 49-second responses?
# Questions to answer:
# 1. Which query types are slow? (long queries? complex symptoms?)
# 2. Is it vector search? (ChromaDB query time)
# 3. Is it LLM generation? (MedGemma inference time)
# 4. Is it product refinement? (LLM selecting from candidates)
# 5. Is it translation? (BG↔EN translation time)
```

**Option A: Add Detailed Performance Instrumentation (Recommended)**
- **Effort:** 2-3 hours (add timing logs per pipeline stage)
- **Risk:** None
- **Impact:** Understand which stage causes outliers
- **Maintenance:** Data-driven optimization

```python
# src/pipeline/orchestrator.py
def process(self, query: str):
    timings = {}

    start = time.perf_counter()
    intent = self.intent_classifier.classify(query)
    timings['intent_ms'] = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    translated = self.translator.translate_bg_to_en(query)
    timings['translation_ms'] = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    reasoning = self.medical_model.reason(translated)
    timings['medical_ms'] = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    products = self.product_store.hybrid_search(reasoning)
    timings['search_ms'] = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    refined = self.medical_model.refine_product_selection(products)
    timings['refinement_ms'] = (time.perf_counter() - start) * 1000

    logger.info("Pipeline timing breakdown", extra=timings)
```

**Then analyze logs:**
```bash
# Which stage dominates 49s responses?
jq 'select(.duration_ms > 30000) | .timings' logs/*.jsonl
```

**Option B: Add Timeout After 30 Seconds**
- **Effort:** 1 hour (add timeout middleware)
- **Risk:** Medium (kills long-running requests)
- **Impact:** Prevents outliers, may anger users with timeout errors
- **Maintenance:** Doesn't fix root cause

**Option C: Ignore Outliers**
- **Effort:** None
- **Risk:** Medium (users hit timeouts)
- **Impact:** Status quo
- **Maintenance:** None

→ **Recommendation: Option A** — Measure before optimizing. 2-3 hours to instrument pipeline stages. Then you can fix the actual bottleneck.

---

### **Issue #14: LRU Cache Effectiveness Unknown**

**Files:**
- `src/unified_processor.py:121-179` (ProcessorCache)
- `src/translator.py:50-115` (TranslationCache × 2)
- `src/medical_model.py:40-110` (ReasoningCache)

You have **4 separate caching layers** with different sizes (500-1000 entries). But:

**Questions:**
- What's the cache hit rate?
- Are 500 entries enough? Too many?
- Is caching even helping?
- Were these premature optimizations?

**Current State:**
- ✅ Cache hit rate logging added (TECHNICAL_DEBT.md mentions monitoring)
- ⏳ Need production data to evaluate effectiveness
- ⏳ No decision made yet on keeping/removing caches

**Option A: Monitor for 1 Week, Then Decide (Recommended)**
- **Effort:** 1 week wait + 1 hour analysis
- **Risk:** None
- **Impact:** Data-driven cache decisions
- **Maintenance:** Remove unhelpful caches, optimize helpful ones

```bash
# After 1 week in production:
curl http://localhost:8000/metrics | jq '.cache'

# Decision matrix:
# Hit rate < 40% → Remove cache (not helping)
# Hit rate 40-70% → Keep as-is
# Hit rate > 70% → Increase size for more hits
```

**Option B: Remove All Caches**
- **Effort:** 2 hours (delete cache code)
- **Risk:** Medium (may hurt performance)
- **Impact:** Simpler code, possibly slower
- **Maintenance:** No cache management

**Option C: Keep All Caches**
- **Effort:** None
- **Risk:** Low (works today)
- **Impact:** Status quo
- **Maintenance:** Ongoing complexity

→ **Recommendation: Option A** — Cache hit rate logging already added. Wait 1 week for data, then decide. Evidence-based optimization.

---

### Performance Summary

**Strengths:**
✅ Average response time acceptable (7.3s)
✅ Single-threaded decision validated (MLX constraint)
✅ Caching implemented (effectiveness TBD)
✅ No obvious N+1 patterns (ChromaDB optimized)

**Weaknesses:**
⚠️ Performance outliers (49s max)
⚠️ Cache effectiveness unknown
⚠️ No per-stage timing instrumentation
⚠️ P99/P95 latency not measured

**Health Grade:** **B-** (80/100) — Generally good, outliers concerning

---

## 🔒 5. SECURITY POSTURE

**Evaluated:**
- OWASP Top 10 vulnerabilities
- Secrets management
- Input validation
- Dependency vulnerabilities

---

### **Issue #15: 1 Known CVE (DiskCache Pickle Vulnerability)**

**Source:** `SECURITY.md` — Last scanned February 17, 2026

**Vulnerability:**
- **Package:** diskcache 5.6.3 (transitive from ChromaDB)
- **CVE:** CVE-2025-69872
- **Severity:** Medium
- **Description:** Uses Python pickle for serialization (code execution if attacker has filesystem write access)
- **Fix Available:** No (upstream issue)

**Risk Assessment:**
- **Exploitability:** Low (requires write access to `/data/chromadb/`)
- **Impact:** High (arbitrary code execution if exploited)
- **Likelihood:** Low (would need to compromise host filesystem first)

**Current Mitigation:**
- Filesystem permissions (owner-only write on `/data/chromadb/`)
- Docker container isolation
- No user-writable paths to cache directory

**Option A: Accept Risk with Enhanced Monitoring (Recommended)**
- **Effort:** 2 hours (add file integrity monitoring)
- **Risk:** Low (already mitigated by permissions)
- **Impact:** Detect unauthorized cache writes
- **Maintenance:** Monitor for upstream fix

```python
# Add to health check:
import os
import stat

def check_cache_permissions():
    cache_dir = "data/chromadb/"
    st = os.stat(cache_dir)
    mode = st.st_mode

    # Ensure only owner can write
    if mode & stat.S_IWGRP or mode & stat.S_IWOTH:
        logger.critical("ChromaDB cache has insecure permissions!")
        return False
    return True
```

**Option B: Switch to Alternative ChromaDB Backend**
- **Effort:** 1-2 days (research + migrate + test)
- **Risk:** High (may break product search)
- **Impact:** Eliminate pickle vulnerability
- **Maintenance:** Significant migration work

**Option C: Accept Risk, Do Nothing**
- **Effort:** None
- **Risk:** Low (filesystem already protected)
- **Impact:** Status quo
- **Maintenance:** Monitor upstream

→ **Recommendation: Option A** — Risk is already low with filesystem permissions. Add monitoring to detect tampering. Upstream fix monitoring ongoing.

---

### **Issue #16: No API Authentication**

**File:** `api_server.py` — OpenAI-compatible API has **no authentication**

Current API endpoints have:
- ✅ Rate limiting (30 req/min per IP)
- ✅ Input validation (message length, sanitization)
- ✅ CORS middleware
- ❌ **No authentication/authorization**

**Impact:**
- Anyone with network access can use API
- No user attribution (can't track who made which query)
- Rate limiting per IP only (easily bypassed with proxies)
- No quota management per user

**When Is This a Problem?**
- ✅ **Development:** Not a problem (local testing)
- ✅ **Internal deployment:** Low risk (trusted network)
- ❌ **Public internet:** High risk (abuse, cost, privacy)

**Option A: Add API Key Authentication (Recommended for Production)**
- **Effort:** 4-6 hours (implement + test)
- **Risk:** Low (standard pattern)
- **Impact:** Controlled access, user attribution
- **Maintenance:** API key management

```python
# api_server.py
from fastapi import Header, HTTPException

VALID_API_KEYS = set(os.getenv("API_KEYS", "").split(","))

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    api_key: str = Depends(verify_api_key)
):
    ...
```

**Option B: Deploy Behind Auth Gateway**
- **Effort:** 2-3 hours (nginx + basic auth)
- **Risk:** Low (standard practice)
- **Impact:** Network-level protection
- **Maintenance:** Infrastructure dependency

**Option C: No Authentication (Keep Open)**
- **Effort:** None
- **Risk:** Depends on deployment (high if public)
- **Impact:** Status quo
- **Maintenance:** Rely on rate limiting only

→ **Recommendation:** Depends on deployment:
- **If internal/dev:** Option C acceptable
- **If production/public:** Option A required

Document intended deployment model and add authentication before public launch.

---

### Security Summary

**Strengths:**
✅ Security scanning enabled (pip-audit in CI)
✅ Input validation (length limits, sanitization)
✅ Rate limiting implemented
✅ Documented accepted risks (SECURITY.md)
✅ Ruff security checks enabled (Bandit rules)
✅ No hardcoded secrets in code

**Weaknesses:**
⚠️ 1 known CVE (low exploitability)
⚠️ No API authentication (deployment-dependent risk)
⚠️ In-memory rate limiting (multi-pod bypass)

**Health Grade:** **B+** (85/100) — Strong security posture for current stage

---

## 🗑️ 6. DEAD CODE & ORPHANS

**Evaluated:**
- Unused imports, variables, functions
- Orphaned files
- Commented-out code
- Deprecated patterns

---

### **Issue #17: Intent Classifier Marked DEPRECATED**

**File:** `src/intent_classifier.py:9` — Contains deprecation notice

```python
"""
Intent Classifier for Medical Query Detection

Status: DEPRECATED - Scheduled for removal
    Replaced by: src/unified_processor.py (UnifiedProcessor)
    Migration: In progress (feature flag: unified_processor_enabled)
"""
```

**Status:**
- File: 668 lines
- Still actively used (unified_processor disabled by default)
- Marked deprecated but not deleted
- Part of Issue #2 (Parallel Architecture Paths)

**Option:** Already covered in Issue #2 (Architecture). No separate action needed here.

---

### **Issue #18: Single-Line __init__.py**

**File:** `src/__init__.py` — Only 1 line (empty package marker)

This is **not a problem**. Empty `__init__.py` is Python best practice for namespace packages.

**No action needed.**

---

### **Issue #19: No Commented-Out Code Found**

**Search:** Looked for large commented blocks, found none.

✅ **Clean codebase** — no dead commented code.

---

### **Issue #20: .DS_Store Committed (Minor)**

**File:** `./.DS_Store` found in root

macOS metadata file shouldn't be in repo. Already in `.gitignore` but one slipped through.

**Option A: Remove from Git**
- **Effort:** 1 minute
- **Risk:** None
- **Impact:** Cleaner repo
- **Maintenance:** None

```bash
git rm .DS_Store
git commit -m "chore: Remove macOS metadata file"
```

**Option B: Ignore**
- **Effort:** None
- **Risk:** None (cosmetic issue)
- **Impact:** Stays in repo
- **Maintenance:** None

→ **Recommendation: Option A** — 1 minute to clean up.

---

### Dead Code Summary

**Strengths:**
✅ No commented-out code blocks
✅ No obvious orphaned files
✅ Clean .gitignore (comprehensive)

**Weaknesses:**
⚠️ Deprecated intent_classifier still in use (668 LOC)
⚠️ .DS_Store in repo

**Health Grade:** **B** (83/100) — Very clean, deprecated code handled via migration plan

---

## 📋 FINAL SUMMARY

### Overall Project Health: **C+ (70/100)**

**Grade Breakdown:**
- Architecture: C+ (70/100) — God object catastrophe, dual paths
- Code Quality: C (65/100) — DRY violations, print statements
- Testing: C+ (72/100) — Good quantity, coverage gaps in critical areas
- Performance: B- (80/100) — Generally acceptable, outliers concerning
- Security: B+ (85/100) — Strong for current stage
- Dead Code: B (83/100) — Very clean, managed deprecation

---

### Critical Issues (Fix First)

**Production Quality (This Week):**

1. **Garbage Text in Responses (7% affected)**
   - Root cause: LLM hallucinations inserting irrelevant Bulgarian text
   - Fix: Output validation + prompt engineering + lower temperature
   - Effort: 2-3 days
   - Priority: P0 (user-facing quality)

2. **Template Compliance (38% missing ingredients)**
   - Root cause: Ingredient extraction failing
   - Fix: Debug extraction logic, ensure template always shows ingredients
   - Effort: 2-3 days
   - Priority: P0 (user-facing quality)

3. **Performance Outliers (49s max response time)**
   - Root cause: Unknown (no instrumentation)
   - Fix: Add per-stage timing, identify bottleneck
   - Effort: 2-3 hours investigation
   - Priority: P1 (user experience)

**Architecture Debt (Next 2 Months):**

4. **God Object Orchestrator (3,224 LOC)**
   - Fix: 5-week strangler fig extraction
   - Reduces to ~800 LOC, improves testability
   - Priority: P0 (development velocity)

5. **Parallel Architecture Paths**
   - Fix: Enable unified_processor or delete it (3 days)
   - Removes ~800 LOC maintenance burden
   - Priority: P1 (code complexity)

6. **In-Memory Rate Limiting**
   - Fix: Redis-based distributed rate limiting (4-6 hours)
   - Enables horizontal scaling
   - Priority: P1 (scalability)

---

### Quick Wins (Do This Week)

1. **Convert 21 print() to logger calls** (1 hour)
2. **Remove .DS_Store from repo** (1 minute)
3. **Split E2E test monolith** (3-4 hours)
4. **Add safety edge case tests** (3-4 hours)
5. **Extract duplicate LLM generation code** (2-3 hours)

**Total:** ~10 hours for 5 improvements

---

### Recommended 8-Week Plan

**Week 1: Production Quality**
- Fix garbage text (output validation)
- Fix template compliance (ingredient extraction)
- Add performance instrumentation

**Week 2: Testing**
- Product store tests (18% → 75%)
- Safety edge cases
- Split E2E monolith

**Week 3-4: Enable Unified Processor**
- Feature flag → True
- Monitor accuracy/performance
- Delete legacy intent_classifier if stable

**Weeks 5-9: God Object Extraction**
- Week 5: QueryRouter
- Week 6: ResponseBuilder
- Week 7: ProductMatcher
- Week 8: SafetyValidator
- Week 9: IngredientAnalyzer

**Week 10: Scaling Prep**
- Redis rate limiting
- Memory leak investigation
- API authentication (if going public)

---

### Trade-Off Analysis

**Architecture Decision: Unified Processor vs Legacy Path**

You built the unified processor (487 LOC, 30% faster) but disabled it by default. This creates double maintenance.

**Recommendation:** Go all-in on unified processor.

**Why?**
- 30% faster (180ms vs 250ms)
- Semantic understanding vs keyword matching
- Single LLM call vs multi-stage pipeline
- Already built and tested

**Risk:**
- Less debuggable (black box)
- Higher VRAM usage
- Single point of failure

**Mitigation:**
- 3-day phased rollout (10% → 50% → 100%)
- A/B test accuracy before full migration
- Keep feature flag for quick rollback

**Alternative:** If you don't trust it, delete it. Don't maintain both.

---

**Architecture Decision: God Object Extraction**

3,224 lines in one class is catastrophic for maintainability.

**Recommendation:** 5-week strangler fig extraction.

**Why?**
- Test coverage 9% → Each extracted component gets 80%+
- PRs 500 lines → 100 lines
- New engineer onboarding 2 weeks → 3 days
- Parallel development possible

**Risk:**
- 5 weeks of refactoring effort
- Temporary dual code paths during migration

**Mitigation:**
- One extraction per week (small PRs)
- Feature flags for each component
- Existing code stays until proven replacement

**Alternative:** Live with god object, focus on new features. But velocity will continue declining.

---

### Strengths to Preserve

1. **Safety-First Design** — Emergency detection, OTC filtering, comprehensive symptom coverage
2. **Evidence-Based Decisions** — MLX concurrency validated with tests, not assumptions
3. **Comprehensive Documentation** — ARCHITECTURE.md, TECHNICAL_DEBT.md, SECURITY.md all excellent
4. **E2E Quality Testing** — 352 real queries, catches production issues
5. **Security Awareness** — Vulnerability scanning, accepted risks documented

Don't lose these during refactoring.

---

### Questions for You

1. **Unified Processor:** Enable and go all-in, or delete it? (Don't maintain both)

2. **God Object:** Ready to commit 5 weeks to extraction? Or prioritize new features?

3. **Public Deployment:** Is this going public internet or staying internal?
   - If public → Need API authentication
   - If internal → Current security acceptable

4. **Performance Outliers:** Are 49-second responses acceptable, or must fix?

5. **Test Coverage:** Committed to reaching 80%? Or keep at 40%?

---

## Agreed Action Items

*(Fill in after your review)*

- [ ] Issue #__: _____ (Option _)
- [ ] Issue #__: _____ (Option _)
- [ ] ...

---

## Deferred Items

*(Fill in after your review)*

- Issue #__: _____ (Reason: _____)
- ...

---

**End of Review**

*Generated by Claude Code Staff Engineering Review*
*Next review recommended: April 18, 2026*
