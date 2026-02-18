# Pharmacy AI Assistant - Refactoring Master Plan

**Start Date:** February 18, 2026
**Target Completion:** April 2026 (8-10 weeks)
**Goal:** Production-ready codebase with 80%+ coverage, <10s P99 latency, maintainable architecture

---

## Priorities (Confirmed by User)

1. ✅ **E2E Tests First** - Reach 80% coverage to enable safe refactoring
2. ✅ **Fix 49s Outliers** - CRITICAL performance issue (target: P99 <10s)
3. ✅ **Enable Unified Processor** - Eliminate dual architecture (30% faster)
4. ✅ **God Object Extraction** - 5-week systematic refactor (3,224 LOC → ~800 LOC)
5. ✅ **Memory Leak Investigation** - Fix aggressive gc.collect() workaround
6. ❌ **Skip Redis** - Deferred to deployment platform decision
7. ❌ **Skip API Auth** - Shopify will handle authentication

---

## Week-by-Week Plan

### ✅ Week 1: Production Quality Fixes (COMPLETED)

**Status:** Done
**Changes:**
- Expanded treatment type mappings (14 → 38 types)
- Added per-stage performance instrumentation
- Temperature already optimized (0.1-0.3)

**Files Modified:**
- `src/pipeline/product_ingredients.py`
- `src/pipeline/orchestrator.py`

**Outcome:**
- Template compliance fix ready (38% → >95% expected)
- Performance bottleneck identification ready

---

### 🔧 Week 2: E2E Testing Foundation (IN PROGRESS - Priority)

**Goal:** Build comprehensive E2E test coverage for safe refactoring

**Tasks:**

#### 2.1: Expand E2E Test Suite (Priority: HIGH)
**Target:** 352 → 500+ test queries covering all edge cases

**Categories to add:**
1. **Complex multi-symptom queries** (50 queries)
   - "Имам главоболие, температура 38°C, болки в мускулите и кашлица"
   - "Детето ми има хрема, кашлица и леко повишена температура"

2. **Edge cases** (50 queries)
   - Very short queries ("болка", "главоболие")
   - Very long queries (>200 words)
   - Mixed language (Bulgarian + English)
   - Typos and misspellings

3. **Safety validation** (50 queries)
   - All emergency symptoms
   - All urgent symptoms
   - Borderline cases (heartburn vs chest pain)

4. **Product coverage** (50 queries)
   - Each treatment category (fever, pain, allergy, digestive, etc.)
   - Combination products
   - OTC vs prescription filtering

**Deliverable:**
- `tests/e2e/test_comprehensive_coverage.py` - 200+ new tests
- Organized by category (not monolithic)
- **Target:** 80% code coverage from E2E tests alone

#### 2.2: Split E2E Test Monolith (Priority: MEDIUM)
**Current:** `e2e_query_tests.py` (1,628 LOC monolith)
**Target:** 5 organized files

```
tests/e2e/
├── test_symptom_queries.py      (~400 LOC, 100+ tests)
├── test_medication_queries.py   (~400 LOC, 80+ tests)
├── test_safety_queries.py       (~300 LOC, 60+ tests)
├── test_catalog_queries.py      (~300 LOC, 50+ tests)
└── test_edge_cases.py           (~228 LOC, 50+ tests)
```

#### 2.3: Add Performance Benchmarks (Priority: HIGH)
**Track:**
- P50, P95, P99 latency
- Per-stage timing distribution
- Identify outlier causes

**Deliverable:**
- `tests/e2e/test_performance_benchmarks.py`
- Automated detection of >10s queries
- Failed test if P99 > 10s

**Effort:** 3-4 days
**Success Criteria:**
- 500+ E2E tests
- 80% coverage from E2E alone
- P99 latency measured and tracked

---

### 🔥 Week 2.5: Fix Performance Outliers (CRITICAL)

**Goal:** Reduce max response time from 49s → <20s, P99 → <10s

**Phase 1: Add Timeouts (Day 1 - 4 hours)**

1. **MedGemma Timeout** (15s max)
```python
# src/medical_model.py
async def get_medical_reasoning_with_timeout(self, symptoms: str, timeout: float = 15.0):
    try:
        return await asyncio.wait_for(
            self.get_medical_reasoning(symptoms),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning(f"MedGemma timeout, using fallback reasoning")
        return self._get_simple_fallback(symptoms)
```

2. **Vector Search Timeout** (3s max)
```python
# src/product_store.py
def hybrid_search_with_timeout(self, query: str, timeout: float = 3.0):
    try:
        return timeout_wrapper(self.hybrid_search, query, timeout=timeout)
    except TimeoutError:
        logger.warning("Vector search timeout, using keyword fallback")
        return self._keyword_search_fallback(query)
```

3. **API-Level Timeout** (20s hard limit)
```python
# api_server.py
@app.post("/v1/chat/completions")
async def chat_completions_with_timeout(request: ChatCompletionRequest):
    try:
        return await asyncio.wait_for(
            process_chat_completion(request),
            timeout=20.0
        )
    except asyncio.TimeoutError:
        return error_response("Query too complex. Try simplifying.", 504)
```

**Phase 2: Root Cause Fix (Day 2-3 - Based on Investigation)**

**If MedGemma is bottleneck:**
- Option A: Model quantization (4-bit) - 50% faster
- Option B: Aggressive caching for common queries
- Option C: Pre-warm model on startup (eliminate cold starts)

**If ChromaDB is bottleneck:**
- Option D: Optimize HNSW index parameters
- Option E: Keep embeddings in RAM (mmap)
- Option F: Reduce collection size (filter out rare products)

**Effort:** 2-3 days
**Success Criteria:**
- Max response time: 49s → 20s (hard cap)
- P99 response time: <10s
- <1% queries hit timeout fallback
- E2E tests still pass (no quality regression)

---

### ⚡ Week 3: Enable Unified Processor (Kill Dual Architecture)

**Goal:** Go all-in on unified processor, delete legacy intent classifier

**Why:**
- 30% faster (180ms vs 250ms)
- Single LLM call vs 3 separate steps
- Simpler architecture (removes 668 LOC)

**Day 1: Enable Feature Flag**
```python
# src/config.py
unified_processor_enabled: bool = Field(default=True)  # Changed from False
```

**Day 2-3: Monitor Accuracy**
- A/B test on 100 sample queries
- Compare accuracy vs legacy path
- **If accuracy < 95% of legacy → Rollback**

**Day 4-5: Delete Legacy Code (If Stable)**
```bash
git rm src/intent_classifier.py  # 668 LOC removed
```

Update orchestrator to remove legacy path:
```python
# src/pipeline/orchestrator.py
# Remove lines 679-824 (legacy processing path)
# Keep only unified processor path
```

**Effort:** 5 days
**Success Criteria:**
- Unified processor enabled and stable
- Legacy code deleted
- ~800 LOC removed from codebase
- E2E tests pass with unified processor

---

### 🔧 Week 4: Memory Leak Investigation

**Goal:** Fix aggressive gc.collect() workaround

**Investigation:**
```python
# tests/memory_profiling.py
import mlx.core as mx
from src.pipeline import get_pipeline

pipeline = get_pipeline()

for i in range(100):
    result = pipeline.process("тест заявка")
    stats = mx.metal.device_info()
    print(f"Request {i}: VRAM = {stats.get('memory_used_mb')} MB")
    # Don't clear cache - measure accumulation
```

**Likely Causes:**
1. MLX model tensors not freed
2. ChromaDB embeddings cached indefinitely
3. Translation model accumulating tensors

**Fix Options:**
- If MLX bug: Report upstream, keep workaround with detailed comment
- If our code: Fix leak (proper tensor cleanup)
- If unavoidable: Document with evidence

**Effort:** 4-8 hours investigation + fix time (varies)
**Success Criteria:**
- VRAM usage stable over 100 requests
- Can remove gc.collect() from middleware (or document why needed)

---

### 🏗️ Weeks 5-9: God Object Extraction (Strangler Fig Pattern)

**Goal:** Break 3,224-line orchestrator into testable components

**Current State:**
- `src/pipeline/orchestrator.py` - 3,224 LOC, 68 methods
- Test coverage: 9%
- Single class does everything

**Target State:**
- `src/pipeline/orchestrator.py` - ~800 LOC (core orchestration only)
- 5 new component files - each 80%+ tested
- Clear separation of concerns

#### Week 5: Extract QueryRouter

**Move:**
- `is_catalog_query()`
- `is_comparison_query()`
- `is_single_drug_name_query()`
- `is_help_clarification_query()`
- `_process_catalog_query()`
- `_process_comparison_query()`

**Create:**
- `src/pipeline/query_router.py` (~300 LOC)

**Tests:**
- `tests/test_query_router.py` (20+ tests)

**Pattern:**
```python
# src/pipeline/query_router.py
class QueryRouter:
    def route(self, query: str) -> QueryRoute:
        if self._is_catalog(query):
            return QueryRoute(type="catalog", handler=self._handle_catalog)
        elif self._is_comparison(query):
            return QueryRoute(type="comparison", handler=self._handle_comparison)
        else:
            return QueryRoute(type="medical", handler=None)
```

#### Week 6: Extract ResponseBuilder

**Move:**
- `_format_response()`
- `_format_response_from_unified()`
- `_build_product_list()`
- `_format_comparison_response()`
- All template formatting logic

**Create:**
- `src/pipeline/response_builder.py` (~400 LOC)

**Tests:**
- `tests/test_response_builder.py` (30+ tests)

**Pattern:**
```python
# src/pipeline/response_builder.py
class ResponseBuilder:
    def build_medical_response(
        self,
        reasoning: MedicalReasoning,
        products: list[Product],
        query: str
    ) -> str:
        # Template logic here
        pass

    def build_comparison_response(
        self,
        drugs: list[str],
        products_by_drug: dict
    ) -> str:
        # Comparison template
        pass
```

#### Week 7: Extract ProductMatcher

**Move:**
- `_retrieve_product_candidates()`
- `_refine_product_selection()`
- `_deduplicate_by_ingredient()`
- `_filter_by_age_appropriateness()`

**Create:**
- `src/pipeline/product_matcher.py` (~300 LOC)

**Tests:**
- `tests/test_product_matcher.py` (25+ tests)

#### Week 8: Extract SafetyValidator

**Move:**
- `_check_safety()`
- `_add_child_disclaimer()`
- `_add_chronic_disease_disclaimer()`
- `_add_contraindication_warning()`

**Create:**
- `src/pipeline/safety_validator.py` (~200 LOC)

**Tests:**
- `tests/test_safety_validator.py` (30+ tests)

#### Week 9: Extract IngredientAnalyzer

**Move:**
- `_get_recommended_ingredients()`
- Ingredient extraction logic from orchestrator
- Complete migration to `product_ingredients.py`

**Create:**
- Complete `src/pipeline/ingredient_analyzer.py` (~250 LOC)

**Tests:**
- `tests/test_ingredient_analyzer.py` (20+ tests)

---

## Success Metrics

### Code Quality
- [ ] Test coverage: 39% → 80%+ ✅
- [ ] E2E test count: 352 → 500+ ✅
- [ ] Orchestrator size: 3,224 LOC → <800 LOC ✅
- [ ] Dual architecture: 2 paths → 1 path ✅

### Performance
- [ ] P99 latency: Unknown → <10s ✅
- [ ] Max latency: 49s → <20s ✅
- [ ] Average latency: 7.3s → <7s ✅

### Architecture
- [ ] Component count: 1 god object → 6 focused components ✅
- [ ] Each component: <500 LOC, 80%+ coverage ✅
- [ ] Clear interfaces between components ✅

---

## Timeline Summary

| Week | Focus | Effort | Outcome |
|------|-------|--------|---------|
| 1 ✅ | Production quality fixes | 2 days | Template compliance, instrumentation |
| 2 🔧 | E2E test expansion | 4 days | 500+ tests, 80% coverage |
| 2.5 🔥 | Performance outliers | 3 days | P99 <10s, max <20s |
| 3 ⚡ | Unified processor | 5 days | Kill dual architecture |
| 4 🔍 | Memory leak | 2 days | Fix gc.collect() workaround |
| 5 🏗️ | QueryRouter extraction | 5 days | -300 LOC, +20 tests |
| 6 🏗️ | ResponseBuilder extraction | 5 days | -400 LOC, +30 tests |
| 7 🏗️ | ProductMatcher extraction | 5 days | -300 LOC, +25 tests |
| 8 🏗️ | SafetyValidator extraction | 5 days | -200 LOC, +30 tests |
| 9 🏗️ | IngredientAnalyzer extraction | 5 days | -250 LOC, +20 tests |

**Total:** 8-10 weeks

---

## Risk Mitigation

1. **Each extraction is a separate PR** - Easy to rollback
2. **Feature flags for new components** - Gradual rollout
3. **E2E tests run after every change** - Catch regressions immediately
4. **Old code stays until proven** - Strangler fig pattern
5. **80% E2E coverage first** - Safety net for refactoring

---

## Files to Track

### Created This Session
- ✅ `STAFF_ENGINEERING_REVIEW.md` - Initial assessment
- ✅ `WEEK1_FIXES_SUMMARY.md` - Week 1 changes
- ✅ `PERFORMANCE_OUTLIER_ANALYSIS.md` - Performance investigation
- ✅ `REFACTORING_MASTER_PLAN.md` - This document

### Modified This Session
- ✅ `src/pipeline/product_ingredients.py` - Expanded treatment mappings
- ✅ `src/pipeline/orchestrator.py` - Added performance instrumentation

### To Create
- `tests/e2e/test_comprehensive_coverage.py` - E2E expansion
- `tests/e2e/test_performance_benchmarks.py` - Performance tracking
- `src/pipeline/query_router.py` - Week 5
- `src/pipeline/response_builder.py` - Week 6
- `src/pipeline/product_matcher.py` - Week 7
- `src/pipeline/safety_validator.py` - Week 8
- `src/pipeline/ingredient_analyzer.py` - Week 9

---

**Next Immediate Steps:**
1. ✅ Complete Week 2 E2E test expansion (80% coverage)
2. 🔥 Fix 49s performance outliers (CRITICAL)
3. ⚡ Enable unified processor (kill dual architecture)
4. 🏗️ Begin god object extraction (Week 5)

**Status:** Plan confirmed by user. Ready to execute.
