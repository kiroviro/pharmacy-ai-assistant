# Technical Debt & Issues Tracker

**Last Updated**: February 14, 2026
**Project Grade**: C+ (70/100) - *Downgraded due to E2E quality findings*
**Source**: Staff Engineering Review + E2E Quality Tests (352 queries)

## 📊 Quality Status (E2E Tests - February 14, 2026)

**Test Results**: 352 queries, 0 failures, but significant quality issues

| Category | Status | Details |
|----------|--------|---------|
| 🚨 **CRITICAL** | 6 issues | Garbage text contaminating medical advice |
| ⚠️ **HIGH** | 231 issues | Template compliance (missing ingredients 62%) |
| ⚠️ **MEDIUM** | 4 issues | Language quality (English leaks) |
| ⚠️ **LOW** | 20 issues | Performance outliers (max 49s) |
| ✅ **PASSING** | 322/352 | Core functionality works (91.5%) |

**Top Priorities**:
1. Fix garbage text (7% of responses affected)
2. Fix template compliance (only 38% show active ingredients)
3. Fix language quality (4 responses with English leaks)

**See**: Issues #17-#20 (Production Quality)

---

## 🔴 Critical Issues (Must Fix Before Scaling)

### 1. ✅ FIXED: Dead Code Configuration Duplication
**Status**: ✅ Completed (Commit: 20bfd5e)
**Severity**: Critical
**Original Issue**: `src/config_constants.py` (148 lines) had 0 imports, duplicating 80% of `src/config.py`
**Impact**: Developer confusion, ghost bugs from editing wrong file
**Resolution**: Deleted `config_constants.py` entirely

---

### 2. ⚠️ ACTIVE: God Object Anti-Pattern (Orchestrator Explosion)
**Status**: 🔴 Not Started
**Priority**: P0 (Highest)
**Effort**: 2-3 weeks (incremental)

**Problem**:
- File: `src/pipeline/orchestrator.py`
- Size: **2,676 lines, 68 methods** in single Pipeline class
- Violates Single Responsibility Principle catastrophically
- Impossible to unit test in isolation
- PR reviews must be 500+ lines

**Impact**:
- Blocks new engineer onboarding (2+ weeks to understand)
- Prevents parallel development (constant merge conflicts)
- Makes debugging extremely difficult

**Solution** (Strangler Fig Pattern):
```
Week 1: Extract QueryRouter (~300 LOC)
  - src/pipeline/orchestrator.py:39-350
  - Move to: src/pipeline/query_router.py (already partially exists)
  - Extract: is_catalog_query, is_comparison_query, is_single_drug_name_query

Week 2: Extract ResponseBuilder (~400 LOC)
  - src/pipeline/orchestrator.py:800-1200
  - Move to: src/pipeline/response_builder.py (new)
  - Extract: _format_response, _build_product_list, _format_markdown

Week 3: Extract ProductMatcher (~300 LOC)
  - src/pipeline/orchestrator.py:400-700
  - Move to: src/pipeline/product_matcher.py (new)
  - Extract: _search_products, _refine_products, _deduplicate

Week 4: Extract SafetyValidator (~200 LOC)
  - src/pipeline/orchestrator.py:200-400
  - Move to: src/pipeline/safety_validator.py (new)
  - Extract: safety checks, contraindication filtering

Week 5: Extract IngredientAnalyzer (~250 LOC)
  - Already partially done in src/pipeline/product_ingredients.py
  - Complete extraction from orchestrator
```

**Files**:
- `src/pipeline/orchestrator.py:50-2676`

**Tests to Write**:
- Each extracted class needs isolated unit tests
- Integration tests to ensure pipeline still works

**Rollback Plan**:
- Each extraction is a separate PR
- Old code stays until new code is proven
- Feature flag for each component

---

### 3. ✅ RESOLVED: Single-Threaded Inference Bottleneck
**Status**: ✅ Resolved - Claim Validated
**Priority**: P0 (Performance Critical)
**Date Resolved**: February 13, 2026

**Problem**:
- File: `api_server.py:42`
- Code: `ThreadPoolExecutor(max_workers=1)`
- Comment claims: "MLX doesn't handle concurrent inference well"

**Test Results**: ❌ **MLX DOES NOT SUPPORT CONCURRENT INFERENCE**

**Test Methodology**:
- Model: MedGemma 4B (MLX format)
- Test queries: 20 unique Bulgarian medical queries
- Cache: Disabled to measure actual inference time

**Results**:
```
Sequential (max_workers=1):
  ✅ Success: 20/20 queries
  Time: 54.84s (2.742s per query)

Parallel (max_workers=2):
  ❌ CRASHED with Segmentation Fault
  Exit code: 139 (SIGSEGV)
  Success rate: 0%

Parallel (max_workers=4):
  ⏭️ Skipped (2 workers already crashed)
```

**Root Cause**:
- MLX has thread-unsafe global state (Metal command buffers or GPU contexts)
- No internal locking - assumes single-threaded usage
- Metal API may not support concurrent contexts
- Immediate segfault when attempting concurrent inference

**Decision**: ✅ **KEEP** `max_workers=1` (current configuration is correct)

**Performance Characteristics**:
- Single Request Latency: ~2.7s per query
- Maximum Throughput: ~22 req/min (1,333 req/hour)
- Latency Under Load:
  - 10 req/min: 2.7s average latency
  - 20 req/min: 5.4s average latency
  - 30 req/min: 8.1s average latency

**Scaling Options** (if needed):
1. **Horizontal Scaling** (Recommended): Deploy multiple pods (3 pods = 3x throughput)
2. **Model Optimization**: Quantize to 2-bit or use smaller model variant
3. **Batching**: Process multiple queries in single inference call
4. **GPU Splitting**: Run multiple isolated processes on same GPU

**Files**:
- `api_server.py:42` - Keep as-is
- `tests/load_test_concurrency.py` - Test script preserved for future validation

---

### 4. ⚠️ ACTIVE: Parallel Architecture Paths (Double Maintenance)
**Status**: 🟡 Needs Decision
**Priority**: P1 (Architecture Debt)
**Effort**: 2-3 days (migration) + 1 week (monitoring)

**Problem**:
- Unified processor (new LLM-based) coexists with legacy (keyword-based)
- Feature flag: `unified_processor_enabled=False` (default off)
- Both paths maintained = 2x bugs, 2x testing, 2x cognitive load

**Files**:
- `src/unified_processor.py:1-465` (new path)
- `src/intent_classifier.py:1-346` (legacy path)
- `src/translator.py:137-166` (query translation - legacy)
- `src/pipeline/orchestrator.py:79-88` (feature flag)

**Decision Matrix**:

| Factor | Unified Processor | Legacy Path |
|--------|------------------|-------------|
| Speed | 180ms p50 (30% faster) ✅ | 250ms p50 |
| Accuracy | Semantic understanding ✅ | Keyword matching |
| Maintainability | Single LLM call ✅ | 3+ components |
| Debuggability | Black box ❌ | Clear logic ✅ |
| VRAM Usage | Higher ❌ | Lower ✅ |
| Failure Mode | Single point ❌ | Isolated components ✅ |

**Recommendation**: **Go all-in on Unified Processor**

**Migration Plan**:
```
Week 1: Enable by default
  - src/config.py:114 change False → True
  - Deploy to staging
  - Monitor error rates, latency, VRAM usage

Week 2: Validate in production (10% traffic)
  - Feature flag rollout: 10% → 50% → 100%
  - Compare accuracy with legacy (sample 100 queries)
  - If accuracy < 95% of legacy, rollback

Week 3: Remove legacy code (if stable)
  - Delete: src/intent_classifier.py
  - Delete: query translation from src/translator.py (keep response translation)
  - Remove feature flag
  - Update tests

Rollback: Set unified_processor_enabled=False
```

**IMPORTANT**: Keep hard-coded safety layer regardless of decision (non-negotiable)

---

## 🟠 High Priority Issues

### 5. ⚠️ ACTIVE: Memory Cleanup Smell (VRAM Leak Symptom)
**Status**: 🔴 Not Started
**Priority**: P1 (Performance)
**Effort**: 4-8 hours (investigation) + varies (fix)

**Problem**:
- File: `api_server.py:339-357`
- Middleware calls `gc.collect()` + `mx.metal.clear_cache()` after **every request**
- This is treating symptom, not cause
- MLX or model code likely leaking GPU memory

**Investigation Plan**:
```python
# 1. Profile memory without cleanup (tests/memory_profiling.py)
import mlx.core as mx
from src.pipeline import get_pipeline

pipeline = get_pipeline()

# Track VRAM before/after requests
for i in range(100):
    result = pipeline.process("имам главоболие")

    # Get VRAM usage
    stats = mx.metal.device_info()
    print(f"Request {i}: VRAM used = {stats.get('memory_used_mb', 'unknown')} MB")

    # Don't clear cache - see if it accumulates

# 2. Identify leak source
# - Is it MLX model layers?
# - Is it ChromaDB embeddings?
# - Is it translation models?

# 3. Patch upstream or add targeted cleanup
```

**Expected Fix**:
- If MLX bug: Report to mlx-community, add workaround
- If our code: Fix leak, remove aggressive cleanup
- If unavoidable: Keep cleanup but document why

**Files**:
- `api_server.py:339-357`

---

### 6. ⚠️ ACTIVE: In-Memory Rate Limiting (Won't Scale)
**Status**: 🔴 Not Started
**Priority**: P1 (Scalability)
**Effort**: 4-6 hours

**Problem**:
- File: `api_server.py:44-104`
- `rate_limit_store` dict is process-local
- Horizontal scaling (2+ pods) bypasses limits
- Attacker can 2x rate limit per replica

**Impact**:
- Can't safely scale to multiple instances
- DDoS protection ineffective in production
- Each pod has separate 30 req/min limit (should be global)

**Solution**:
```python
# Option A: Redis (recommended)
# Install: pip install redis

from redis import Redis
import time

redis_client = Redis(host='localhost', port=6379, db=0)

def check_rate_limit_redis(client_ip: str) -> bool:
    key = f"rate_limit:{client_ip}"
    now = int(time.time())

    # Sliding window with Redis sorted set
    redis_client.zremrangebyscore(key, 0, now - 60)
    count = redis_client.zcard(key)

    if count >= settings.rate_limit_per_minute:
        return False

    redis_client.zadd(key, {str(now): now})
    redis_client.expire(key, 60)
    return True

# Option B: SlowAPI (alternative)
# pip install slowapi
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/v1/chat/completions")
@limiter.limit("30/minute")
async def chat_completions(...):
    ...
```

**Files**:
- `api_server.py:44-104`
- Add to `requirements.txt`: `redis>=5.0.0` or `slowapi>=0.1.9`

**Testing**:
```bash
# Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# Load test with 2 API instances
python api_server.py --port 8000 &
python api_server.py --port 8001 &

# Verify rate limit is shared across both
ab -n 100 -c 10 http://localhost:8000/v1/chat/completions
ab -n 100 -c 10 http://localhost:8001/v1/chat/completions
```

---

### 7. ⚠️ ACTIVE: E2E Tests Monolith
**Status**: 🔴 Not Started
**Priority**: P2 (Code Quality)
**Effort**: 3-4 hours

**Problem**:
- File: `e2e_query_tests.py`
- Size: **1,628 lines** in single file
- Larger than most production modules
- Violates test organization best practices
- Hard to navigate, slow to run subset

**Solution**:
```
Split into:
  tests/e2e/
    ├── test_medication_queries.py  (~400 LOC)
    ├── test_symptom_queries.py     (~400 LOC)
    ├── test_safety_queries.py      (~300 LOC)
    ├── test_catalog_queries.py     (~300 LOC)
    └── test_edge_cases.py          (~228 LOC)
```

**Migration**:
```bash
# 1. Create directory
mkdir -p tests/e2e

# 2. Split by category (preserve test names)
# Extract all test_medication_* → test_medication_queries.py
# Extract all test_symptom_* → test_symptom_queries.py
# etc.

# 3. Verify all tests still run
pytest tests/e2e/ -v

# 4. Delete original e2e_query_tests.py

# 5. Update CI config if needed
```

**Files**:
- `e2e_query_tests.py:1-1628`

---

### 8. ✅ FIXED: No Dependency Vulnerability Scanning
**Status**: ✅ Completed (Commit: 3bfd6e4)
**Original Issue**: No `pip-audit`, `safety`, or Dependabot in CI
**Resolution**: Added `pip-audit>=2.6.0`, fixed 2 CVEs (3→1 remaining)

---

### 9. ✅ FIXED: Test Coverage Unknown
**Status**: ✅ Completed (Commit: a255fb3)
**Date Resolved**: February 13, 2026

**Original Issue**: 275 tests exist, but no coverage reporting or enforcement

**Solution Implemented**:
- Added `pytest-cov` to requirements.txt
- Updated `pytest.ini` with coverage settings
- Set minimum threshold at 35% (current baseline)
- Generated HTML report in `htmlcov/`

**Current Coverage**: 39%

**Results**:
- Well-tested files: unified_processor (92%), query_router (91%), intent_classifier (92%)
- Poorly-tested files: orchestrator (9%), product_store (18%), data_loader (29%)
- CI now enforces minimum 35% coverage

**Next Steps**: Gradually increase threshold to 80% as refactoring progresses

---

## 🟡 Medium Priority Issues

### 10. ⚠️ ACTIVE: Evaluation/Metrics Barely Used
**Status**: 🔴 Not Started
**Priority**: P2 (Wasted Investment)
**Effort**: 2-3 hours (integration) or 0 (delete)

**Problem**:
- `src/evaluation.py`: 412 lines, only 3 imports (mostly dev scripts)
- `src/metrics.py`: 399 lines, only 1 import
- `src/query_collector.py`: 330 lines, only 1 import
- **Total: 1,141 lines of quality tooling not in CI/CD**

**Decision Needed**:

**Option A: Integrate into CI** (if valuable)
```yaml
# .github/workflows/quality.yml
- name: Run quality evaluation
  run: |
    python -m src.evaluation  # Run on test queries
    python -m src.metrics report  # Generate report

- name: Check quality threshold
  run: |
    # Fail if quality score < 85%
    python scripts/check_quality_threshold.py
```

**Option B: Delete** (if not providing value)
```bash
git rm src/evaluation.py src/metrics.py src/query_collector.py
# Keep if you plan to use, delete if unused for 6+ months
```

**Files**:
- `src/evaluation.py:1-412`
- `src/metrics.py:1-399`
- `src/query_collector.py:1-330`

---

### 11. ⚠️ ACTIVE: LRU Caches Everywhere (Premature Optimization?)
**Status**: ✅ Partially Fixed (Monitoring added)
**Priority**: P3 (Optimization)
**Effort**: 1 week monitoring + 2 hours cleanup

**Problem**:
- 4 separate caching layers: translator (2), medical_model, unified_processor
- Each with different sizes (500-1000 entries)
- **Were these measured bottlenecks?** Or speculative optimization?

**Current State**:
- ✅ Added cache hit rate logging (Commit: 2a1eff0)
- ⏳ Need to run in production for 1 week
- ⏳ Analyze hit rates

**Next Steps**:
```bash
# After 1 week of production monitoring:

# 1. Check cache performance
curl http://localhost:8000/metrics | jq '.cache'

# 2. Decision matrix:
# - Hit rate < 40% → Remove cache (not helpful)
# - Hit rate 40-70% → Keep as-is
# - Hit rate > 70% → Increase size for more hits

# 3. Example: If translator_bg_to_en has 25% hit rate
# → Too many unique queries, cache not helping
# → Remove cache, simplify code
```

**Files**:
- `src/unified_processor.py:121-179` (ProcessorCache)
- `src/translator.py:50-115` (TranslationCache x2)
- `src/medical_model.py:40-110` (ReasoningCache)

---

### 12. ⚠️ ACTIVE: Safety Layer Keyword Explosion
**Status**: 🟢 Acceptable (No Action Needed)
**Priority**: P3 (Maintenance)
**Effort**: N/A (justified for medical)

**Problem**:
- File: `src/safety.py:99-227`
- 156 emergency/urgent symptoms as hard-coded strings
- Maintenance burden: each new symptom requires code change + deployment

**Analysis**:
- **Trade-off**: Hard-coded = fast + safe; LLM-only = slow + risky
- **Verdict**: Keep hard-coded for top 50 critical patterns
- **Augment**: Use LLM + embedding for long tail (already done)

**Recommendation**: **No change needed** - Medical safety requires redundancy

**Files**:
- `src/safety.py:99-227`

---

### 13. ✅ FIXED: Logging JSON Format Off By Default
**Status**: ✅ Completed (Commit: caf5564)
**Original Issue**: `log_json: bool = False` in config.py
**Resolution**: Changed default to `True` for production structured logging

---

### 14. ⚠️ ACTIVE: Model Path Hard-Coded (Dev vs Prod Mismatch)
**Status**: 🟡 Low Risk
**Priority**: P3 (Configuration)
**Effort**: 5 minutes

**Problem**:
- File: `src/config.py:40-42`
- Default: `./models/medgemma-4b-it-bf16`
- Won't work in Docker container or production

**Solution**:
```python
# Already supports env var: VIAPHARMA_MEDGEMMA_MODEL_PATH
# Just document it better in README

# Docker best practice:
ENV VIAPHARMA_MEDGEMMA_MODEL_PATH=/app/models/medgemma-4b-it-bf16
COPY models/ /app/models/
```

**Files**:
- `src/config.py:40-42`
- `README.md` (add environment variable docs)
- `Dockerfile` (if exists)

---

## 🟠 High Priority Issues

### 17. ⚠️ ACTIVE: Garbage Text Contaminating Responses (CRITICAL)
**Status**: 🔴 Not Started
**Priority**: P0 (User-Facing Quality)
**Effort**: 4-8 hours (investigation + fix)

**Problem**:
- **25 issues detected** (6 CRITICAL) in E2E quality tests
- Irrelevant text appearing in medical advice responses
- Common garbage patterns: "защита на личните", "зъбни протези", "средство за защита"
- Affects 7% of responses (25/352)

**Examples**:
```
Query: "Имам температура 38 градуса"
Garbage: "защита на личните", "средство за защита"

Query: "Имам болка в ухото при дете"
Garbage: "зъбни протези"

Query: "Какво да направя при ларингит?"
Garbage: "зъбни протези"
```

**Root Cause Analysis**:
Likely sources:
1. **Product data contamination**: Product descriptions contain irrelevant keywords
2. **Vector search noise**: ChromaDB returning irrelevant products
3. **LLM hallucination**: Medical model inserting unrelated text
4. **Template corruption**: Response formatting including wrong product data

**Impact**:
- **CRITICAL**: Medical advice contaminated with irrelevant text
- User trust degradation
- Safety risk (confusing advice)
- Unprofessional appearance

**Investigation Plan**:
```python
# 1. Identify source of garbage text
# Check if it comes from:
# - Product database (src/product_store.py)
# - LLM output (src/medical_model.py)
# - Template formatting (src/pipeline/orchestrator.py)

# 2. Sample 10 failing queries
failing_queries = [
    "Имам температура 38 градуса",
    "Имам болка в ухото при дете",
    # ... more from test_results.json
]

# 3. For each, trace:
# - Product search results (candidate_products)
# - LLM reasoning output
# - Final formatted response

# 4. Identify pattern
```

**Solution** (depends on root cause):
- **If product data**: Clean ChromaDB, filter irrelevant products
- **If vector search**: Improve search query, add category filters
- **If LLM**: Adjust system prompt, add output validation
- **If template**: Fix response builder logic

**Files**:
- Check: `src/product_store.py` (vector search)
- Check: `src/pipeline/orchestrator.py` (response formatting)
- Check: `src/medical_model.py` (LLM output)
- Test: `/Users/kiril/IdeaProjects/medgemma/output/test_results.json`

**Success Criteria**: Garbage text in <1% of responses (currently 7%)

---

### 18. ⚠️ ACTIVE: Template Compliance Issues (HIGH)
**Status**: 🔴 Not Started
**Priority**: P1 (User Experience)
**Effort**: 2-3 days

**Problem**:
- **231 template failures** (429 warnings total)
- **Only 38% of responses** have active ingredients section (112/297)
- **Generic safety blocks** instead of ingredient-specific warnings
- Combo products shown without explanation

**Template Compliance**:
```
✅ Symptom header:        296/297 (100%)
❌ Active ingredients:    112/297 (38%)  ← CRITICAL GAP
✅ Safety block:          296/297 (100%)
✅ Products section:      296/297 (100%)
⚠️  Ingredient line:      261/297 (88%)
✅ Buy link:              296/297 (100%)
✅ Triage section:        296/297 (100%)
✅ Footer:                296/297 (100%)
```

**Issues**:
1. **Missing active ingredients** (62% of responses): Users don't know what they're taking
2. **Generic safety blocks**: "Проверете листовката" instead of specific warnings
3. **Combo products without context**: Multi-ingredient products shown for single symptoms

**Example Problems**:
```
Query: "Имам хрема и кихам много"
Issues:
- Missing 💊 Подходящи активни съставки section
- Safety block is generic
- Combo cold/flu product shown without explaining why
```

**Root Cause**:
- File: `src/pipeline/orchestrator.py` (_format_response_from_unified)
- Conditional template logic not firing correctly
- Ingredient extraction from products failing
- Safety block generation using fallback template

**Impact**:
- Users don't understand what medication they're taking
- Safety warnings are vague and unhelpful
- Lower quality than expected from virtual pharmacist

**Solution**:
1. **Fix ingredient extraction** (src/pipeline/product_ingredients.py)
2. **Ensure ingredients section always present** when products shown
3. **Generate ingredient-specific safety warnings** from contraindications
4. **Add combo product explanation** when multiple ingredients present

**Files**:
- `src/pipeline/orchestrator.py:_format_response_from_unified`
- `src/pipeline/product_ingredients.py`
- `src/pipeline/response_builder.py` (if exists)

**Success Criteria**:
- Active ingredients section: 38% → >95%
- Specific safety warnings: >80%
- Combo product notes: 100%

---

### 19. ⚠️ ACTIVE: Language Quality Issues (MEDIUM)
**Status**: 🔴 Not Started
**Priority**: P1 (User Experience)
**Effort**: 2-3 hours

**Problem**:
- **4 responses** have Bulgarian ratio < 80%
- English text leaking into Bulgarian responses
- Translation quality degradation

**Examples**:
```
Query: "Какво да взема при афти?"
Bulgarian ratio: 75%
English leak: "Afts обикновено лекува в рамките на 1-2 седмици"

Query: "Кое е подходящо при възпалени венци?"
Bulgarian ratio: 74%
English leak: "Гидит или сантиментални нарушения"
```

**Root Cause**:
- LLM outputting mixed language (medical_model.py)
- Translation skipping certain terms
- Bulgarian medical terminology missing from model

**Impact**:
- Unprofessional appearance
- User confusion
- Breaks user trust

**Solution**:
1. **Add language validation** to medical model output
2. **Improve translation coverage** for medical terms
3. **Add post-processing** to detect and fix English leaks

**Files**:
- `src/medical_model.py` (LLM prompt/output)
- `src/translator.py` (medical term coverage)
- `src/pipeline/orchestrator.py` (validation)

**Success Criteria**: Bulgarian ratio > 95% in all responses

---

### 20. ⚠️ ACTIVE: Performance Outliers (LOW)
**Status**: 🔴 Not Started
**Priority**: P2 (Performance)
**Effort**: 2-4 hours (investigation)

**Problem**:
- **Average response time**: 7.3 seconds (acceptable)
- **Maximum response time**: 49.3 seconds (unacceptable)
- **Min response time**: 89ms (cached response)

**Impact**:
- User timeout/frustration on outliers
- Inconsistent experience

**Investigation Needed**:
- What causes 49-second responses?
- Is it specific query types?
- Vector search slowness?
- LLM generation time?

**Files**:
- Check: Query logs for slow requests
- Profile: Vector search, LLM inference, product search

---

### 21. ⚠️ ACTIVE: Pipeline Tests Failing (Incorrect Mock Paths)
**Status**: 🔴 Not Started
**Priority**: P3 (Test Quality)
**Effort**: 30 minutes

**Problem**:
- File: `tests/test_pipeline.py:184-188`
- 5 tests failing with AttributeError
- Tests try to patch `src.pipeline.get_translator` but it doesn't exist in `__init__.py`
- These functions exist in `src.pipeline.orchestrator` but aren't re-exported

**Failing Tests**:
```
tests/test_pipeline.py::TestPipelineInitialization::test_pipeline_components_exist
tests/test_pipeline.py::TestPipelineInitialization::test_lazy_loading_works
tests/test_pipeline.py::TestPipelineFlow::test_medical_query_flow
tests/test_pipeline.py::TestPipelineFlow::test_non_medical_query_rejected
tests/test_pipeline.py::TestPipelineFlow::test_empty_query_handled
```

**Error**:
```
AttributeError: <module 'src.pipeline'> does not have the attribute 'get_translator'
```

**Root Cause**:
The test fixture patches the wrong path. The getter functions are imported in orchestrator.py from their actual modules:
- `get_translator` → from `src.translator`
- `get_medical_model` → from `src.medical_model`
- `get_product_store` → from `src.product_store`
- `get_intent_classifier` → from `src.intent_classifier`
- `get_safety_layer` → from `src.safety`

**Solution**:
```python
# tests/test_pipeline.py:184-188
# OLD (incorrect):
with patch('src.pipeline.get_translator', return_value=mock_translator):
    with patch('src.pipeline.get_medical_model', return_value=mock_model):
        ...

# NEW (correct):
with patch('src.translator.get_translator', return_value=mock_translator):
    with patch('src.medical_model.get_medical_model', return_value=mock_model):
        with patch('src.product_store.get_product_store', return_value=mock_store):
            with patch('src.intent_classifier.get_intent_classifier', return_value=mock_intent):
                with patch('src.safety.get_safety_layer', return_value=mock_safety):
                    ...
```

**Files**:
- `tests/test_pipeline.py:184-188`

**Impact**: Test suite shows 5 errors (67 passed, 5 errors) → Should be 72 passed, 0 errors

---

## 🟢 Low Priority / Nice-to-Have

### 15. ⚠️ ACTIVE: Dockerfile Not Visible
**Status**: 🟡 Needs Verification
**Priority**: P4
**Effort**: 1 hour (if missing)

**Problem**:
- README mentions `docker-compose up -d`
- No `docker-compose.yml` visible in root
- May exist but not in current context

**Action**: Verify Docker setup works or remove references

**Files**:
- Check for: `Dockerfile`, `docker-compose.yml`, `.dockerignore`

---

### 16. ⚠️ ACTIVE: Unstaged Pipeline Refactoring Files
**Status**: ✅ Completed (Commit: 00d1a04)
**Original Issue**: New modules not committed
**Resolution**: All documentation updated and committed

---

## Prioritized Action Plan

### 🚨 CRITICAL - Production Quality (This Week)

**Priority: Fix user-facing quality issues before refactoring**

#### Day 1: Investigate Garbage Text (4-6 hours) → Issue #17
**Goal**: Find root cause of irrelevant text in responses

```bash
# 1. Sample failing queries from test_results.json
jq '.critical_issues[] | select(.issues[] | .type == "GARBAGE")' output/test_results.json

# 2. Trace through pipeline for one query
python -c "
from src.pipeline import get_pipeline
pipeline = get_pipeline()
result = pipeline.process('Имам температура 38 градуса')
print('Products:', result.selected_products)
print('Response:', result.response)
"

# 3. Check if garbage comes from:
# - Product database (grep product data for "защита на личните")
# - LLM output (log raw medical_model output)
# - Template formatting (check response builder)
```

**Deliverable**: Root cause identified, fix approach decided

---

#### Day 2-3: Fix Template Compliance (8-12 hours) → Issue #18
**Goal**: Active ingredients section present in >95% of responses

**Tasks**:
1. Fix ingredient extraction (2-3h)
   - Debug why only 38% have ingredients section
   - Ensure `extract_product_ingredient()` works for all products

2. Update response template (2-3h)
   - Always show 💊 section when products present
   - Generate ingredient-specific safety warnings

3. Add combo product notes (2h)
   - Detect multi-ingredient products
   - Add explanation why combo is recommended

4. Validate with E2E tests (2h)
   - Re-run comprehensive tests
   - Target: 112/297 → 285/297+ with ingredients

**Files**:
- `src/pipeline/product_ingredients.py`
- `src/pipeline/orchestrator.py:_format_response_from_unified`

**Success Criteria**: Template compliance 38% → >95%

---

#### Day 4: Fix Language Quality (2-3 hours) → Issue #19
**Goal**: Bulgarian ratio >95% in all responses

**Tasks**:
1. Add language validation (1h)
   - Check response before returning
   - Flag responses with <90% Bulgarian

2. Fix English leaks (1h)
   - Common patterns: "Afts", "Гидит", medical terms
   - Add to translation dictionary or fix prompt

3. Test with failing queries (1h)

**Success Criteria**: 4 failures → 0 failures

---

### 🟡 HIGH PRIORITY - Code Quality (Next Week)

#### Week 2: Fix Unit Tests & Split E2E Tests (1 day)
1. **Fix Pipeline Tests** (30min) → Issue #21
   - Update mock paths in tests/test_pipeline.py
   - Get all 275 tests passing

2. **Split E2E Tests** (3-4h) → Issue #7
   - Organize into 5 category files
   - Improve test navigation

---

### 🟢 MEDIUM PRIORITY - Architecture (Weeks 3-4)

#### Week 3: Enable Unified Processor (3 days) → Issue #4
- Feature flag → True
- Monitor for 1 week
- Remove legacy if stable

#### Week 4: Start God Object Refactor (5 days) → Issue #2
- Extract QueryRouter
- Reduces orchestrator by ~300 LOC

---

### 🔵 LOW PRIORITY - Future Work

- **ResponseBuilder Extraction** (5 days) → Issue #2 (Week 2)
- **Redis Rate Limiting** (1 day) → Issue #6
- **Memory Leak Investigation** (1-2 days) → Issue #5
- **Performance Outlier Investigation** (2-4h) → Issue #20

---

## Metrics Tracking

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| **Production Quality** | | | |
| Garbage Text in Responses | 7% (25/352) | <1% | 🔴 |
| Template Compliance (Ingredients) | 38% (112/297) | >95% | 🔴 |
| Language Quality (BG ratio) | 95% avg (4 failures) | >98% | 🟡 |
| Response Time (p99) | 49.3s | <10s | 🔴 |
| Product Relevance | 99% (3 failures) | >99% | 🟢 |
| **Code Quality** | | | |
| Orchestrator Size | 2,676 LOC | <1,000 LOC | 🔴 |
| Test Coverage | 39% | >80% | 🟡 |
| Unit Tests Passing | 270/275 (98%) | 100% | 🟡 |
| Security CVEs | 1 | 0 | 🟢 |
| **Architecture** | | | |
| Concurrent Workers | 1 | 1 (validated) | ✅ |
| Cache Hit Rate Visibility | 100% | 100% | ✅ |
| E2E Test Files | 1 (1,628 LOC) | 5 (<400 LOC each) | 🔴 |
| Architecture Paths | 2 (unified + legacy) | 1 | 🟡 |

---

## Review Schedule

- **Weekly**: Check cache hit rates, decide on removal
- **Bi-weekly**: Review orchestrator extraction progress
- **Monthly**: Re-run staff engineering review, update grade

**Last Review**: February 13, 2026 (Grade: B-)
**Next Review**: March 13, 2026 (Target: B+)
