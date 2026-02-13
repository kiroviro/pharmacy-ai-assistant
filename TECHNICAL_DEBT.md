# Technical Debt & Issues Tracker

**Last Updated**: February 13, 2026
**Project Grade**: B- (75/100)
**Source**: Staff Engineering Review (Claude Sonnet 4.5)

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

### 3. ⚠️ ACTIVE: Single-Threaded Inference Bottleneck
**Status**: 🟡 Needs Investigation
**Priority**: P0 (Performance Critical)
**Effort**: 2-4 hours (testing) + 1 hour (fix if safe)

**Problem**:
- File: `api_server.py:42`
- Code: `ThreadPoolExecutor(max_workers=1)`
- Comment claims: "MLX doesn't handle concurrent inference well"
- **This claim is unvalidated**

**Impact**:
- At 10 req/min: average latency = 10x p50 (2-3s → 20-30s queue time)
- Prevents horizontal scaling benefits
- Users will experience increasing latency under load

**Investigation Plan**:
```python
# 1. Create load test (tests/load_test_concurrency.py)
import concurrent.futures
import time
import mlx.core as mx
from src.medical_model import get_medical_model

def test_concurrent_inference():
    model = get_medical_model()
    queries = ["имам главоболие"] * 10

    # Test 1: Sequential (current state)
    start = time.time()
    for q in queries:
        model.get_medical_reasoning(q)
    seq_time = time.time() - start

    # Test 2: Parallel (2 workers)
    start = time.time()
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(model.get_medical_reasoning, queries))
    parallel_2_time = time.time() - start

    # Test 3: Parallel (4 workers)
    start = time.time()
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(model.get_medical_reasoning, queries))
    parallel_4_time = time.time() - start

    print(f"Sequential: {seq_time:.2f}s")
    print(f"2 workers: {parallel_2_time:.2f}s (speedup: {seq_time/parallel_2_time:.2f}x)")
    print(f"4 workers: {parallel_4_time:.2f}s (speedup: {seq_time/parallel_4_time:.2f}x)")

    # Check for crashes or memory issues
    mx.metal.clear_cache()

# 2. Monitor VRAM usage during test
# 3. If safe, update api_server.py:42 to max_workers=2 or 4
```

**Expected Outcomes**:
- **If MLX crashes**: Keep max_workers=1, document limitation
- **If MLX works**: Increase to 2-4 workers, gain 2-4x throughput

**Files**:
- `api_server.py:42`
- Create: `tests/load_test_concurrency.py`

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

### 9. ⚠️ ACTIVE: Test Coverage Unknown
**Status**: 🟡 Partially Done
**Priority**: P2 (Quality Assurance)
**Effort**: 1 hour

**Problem**:
- 275 tests exist, but no coverage reporting
- README mentions `--cov=src` but no enforcement
- Unknown which code paths are untested

**Solution**:
```yaml
# .github/workflows/test.yml (if using GitHub Actions)
- name: Run tests with coverage
  run: |
    pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80

# pytest.ini (add)
[pytest]
addopts = --cov=src --cov-report=html --cov-report=term-missing
```

**Files**:
- Create: `.github/workflows/test.yml` (or update existing CI)
- Update: `pytest.ini`

**Deliverable**:
- Coverage badge in README: ![Coverage](https://img.shields.io/badge/coverage-XX%25-green)
- HTML report in `htmlcov/` (gitignored)
- CI fails if coverage drops below 80%

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

### This Week (8 hours)
1. **Test Coverage Enforcement** (1h) → Issue #9
   - Add pytest-cov to CI with 80% threshold

2. **MLX Concurrency Test** (2-4h) → Issue #3
   - Write load test
   - Validate single-thread claim
   - Increase workers if safe

3. **Split E2E Tests** (3-4h) → Issue #7
   - Organize into 5 category files
   - Improve test navigation

### Next Sprint (2 weeks)
4. **QueryRouter Extraction** (5 days) → Issue #2 (Week 1)
   - First strangler fig step
   - Reduces orchestrator by ~300 LOC

5. **Enable Unified Processor** (3 days) → Issue #4
   - Feature flag → True
   - Monitor for 1 week
   - Remove legacy if stable

### Future (4+ weeks)
6. **ResponseBuilder Extraction** (5 days) → Issue #2 (Week 2)
7. **Redis Rate Limiting** (1 day) → Issue #6
8. **Memory Leak Investigation** (1-2 days) → Issue #5

---

## Metrics Tracking

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Orchestrator Size | 2,676 LOC | <1,000 LOC | 🔴 |
| Test Coverage | Unknown | >80% | 🟡 |
| Security CVEs | 1 | 0 | 🟢 |
| Concurrent Workers | 1 | 2-4 | 🟡 |
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
