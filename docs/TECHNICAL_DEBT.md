# Technical Debt & Issues Tracker

**Last Updated**: February 23, 2026
**Project Grade**: B+ (84/100) - *Staff review: all 16 issues resolved, orchestrator <1K LOC, 547 tests, 74% coverage*
**Source**: Staff Engineering Review (Feb 23) + E2E Quality Tests (352 queries)

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

### 2. ✅ RESOLVED: God Object Anti-Pattern (Orchestrator Refactoring)
**Status**: ✅ Complete — **855 LOC** (target was <1,000)
**Priority**: P1
**Date Started**: February 2026
**Date Resolved**: February 23, 2026

**Original Problem**:
- `src/pipeline/orchestrator.py` was **2,676 lines, 68 methods**

**Progress** (Strangler Fig Pattern):
- Phase 1: Extracted ProductMatcher (148 LOC, 90% coverage)
- Phase 2: Extracted SafetyValidator (72 LOC)
- Phase 3: Added test contracts and builders
- Phase 4: Contract-based test migration guide
- Phase 5: Extracted IngredientAnalyzer (215 LOC, 98% coverage)
- Phase 6: Extracted TextValidator into response_validator.py — biggest single phase
- Phase 7: Service layer created then inlined (over-engineering removed)
- Phase 8: Dead code deletion (325 LOC), service layer removal, lazy_load cleanup

**Final State**: 2,676 LOC -> **855 LOC** (68% reduction)

**Files Created**:
- `src/pipeline/product_matcher.py` (148 LOC)
- `src/pipeline/safety_validator.py` (72 LOC)
- `src/pipeline/ingredient_analyzer.py` (215 LOC)
- `src/pipeline/response_builder.py` (227 LOC)
- `src/pipeline/response_validator.py` (745 LOC)

**Deleted** (over-engineered, unused):
- `src/services/` directory (3 services, never called from production code)
- `src/pipeline/conditions.py` (deprecated shim)
- `src/pipeline/models.py` (deprecated shim)

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

### 4. ✅ RESOLVED: Parallel Architecture Paths (Double Maintenance)
**Status**: ✅ Completed (February 2026)
**Original Problem**: Unified processor (LLM-based) coexisted with legacy (keyword-based intent classifier)
**Resolution**:
- Enabled `unified_processor_enabled=True` (default)
- Deleted `src/intent_classifier.py` (346 lines)
- Removed BG→EN query translation from `src/translator.py` (kept EN→BG response translation)
- Removed dual path logic from orchestrator (173 lines)
- Total: 17,873 lines removed across the migration
- Hard-coded safety layer preserved (non-negotiable)

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

### 7. ✅ RESOLVED: E2E Tests Monolith
**Status**: ✅ Completed (February 2026)
**Original Problem**: `e2e_query_tests.py` was 1,628 lines in a single file
**Resolution**: Split into 5 category files in `tests/e2e/`:
- `test_symptom_queries.py`
- `test_medication_queries.py`
- `test_safety_queries.py`
- `test_catalog_queries.py`
- `test_edge_cases.py`

**Note**: Legacy `e2e_query_tests.py` deleted. Added `tests/e2e/conftest.py` to fix pytest collection of `e2e_helpers` imports.

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

### 17. 🟡 PARTIALLY FIXED: Garbage Text Contaminating Responses
**Status**: 🟡 Output validation implemented (Option 1), root cause remains (LLM hallucination)
**Priority**: P1 (User-Facing Quality)
**Investigation Date**: February 14, 2026
**Mitigation**: `src/pipeline/response_validator.py` — TextValidator with 325+ garbage patterns

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

---

## ✅ ROOT CAUSE IDENTIFIED

**Investigation Method**:
Created `debug_garbage_text.py` to trace pipeline execution for failing queries.

**Key Findings**:

### ✅ Vector Search is WORKING CORRECTLY
For query "Имам температура 38 градуса" (I have 38-degree fever):
```
Candidate products from ChromaDB:
1. Диалгин (fever medication) ✅
2. Панактив (fever medication) ✅
3. Нурофен (fever medication) ✅
4. Аспетакс (fever medication) ✅
```
**ALL products returned by vector search are relevant and correct.**

### ❌ LLM (MedGemma 4B) is HALLUCINATING

**Evidence**:
The garbage text appears **in the LLM-generated medical reasoning output**, not in product data.

**Example hallucination**:
```
Query: "Имам температура 38 градуса"

LLM Output Fragment:
"Това е знак, че тялото се бори с инфекция.
Те могат да бъдат използвани като средство за защита на личните данни,
за да може да се използва като средство за..."

Translation:
"This is a sign that the body is fighting an infection.
They can be used as a means of protecting personal data,
so that it can be used as a means for..."
```

**Garbage patterns identified**:
- "защита на личните данни" (protection of personal data)
- "средство за защита" (means of protection)
- "зъбні протези" (dental prosthetics)
- "грижа за зъбні протези" (denture care)
- "репелент" (repellent)
- "комар" (mosquito)

**Root Cause**: MedGemma 4B model generating semantically irrelevant Bulgarian text mid-sentence during medical reasoning.

---

## 🔧 PROPOSED FIXES

### Option 1: Output Validation (Quick Fix - Recommended)
**Effort**: 2-3 hours
**Risk**: Low

Add post-processing filter to detect and block garbage patterns:

```python
# src/pipeline/response_validator.py (NEW)
from typing import List, Tuple

GARBAGE_PATTERNS = [
    "защита на личните",
    "средство за защита",
    "зъбні протези",
    "грижа за зъбні протези",
    "репелент",
    "комар",
    "средство за комари",
]

def validate_response(response: str) -> Tuple[bool, List[str]]:
    """Check response for garbage text."""
    response_lower = response.lower()
    found_garbage = [p for p in GARBAGE_PATTERNS if p in response_lower]

    if found_garbage:
        return False, found_garbage
    return True, []

# src/pipeline/orchestrator.py
def process(self, query: str):
    # ... existing code ...

    # Validate response before returning
    is_valid, garbage = validate_response(result.response)
    if not is_valid:
        logger.warning(f"Garbage detected in response: {garbage}")
        # Option A: Retry with different prompt
        # Option B: Return fallback response
        # Option C: Filter out garbage sentences
```

**Pros**:
- Fast to implement
- Catches known patterns
- No model changes needed

**Cons**:
- Doesn't fix root cause
- Requires pattern maintenance
- May miss new garbage patterns

---

### Option 2: Improve LLM Prompt (Medium Fix)
**Effort**: 3-4 hours
**Risk**: Medium

Update MedGemma system prompt to reduce hallucinations:

```python
# src/medical_model.py
SYSTEM_PROMPT = """
Ти си опитен фармацевт в България. Отговаряй САМО на български език.

ВАЖНО:
- Говори САМО за медицински теми и лекарства
- НЕ споменавай: зъбні протези, защита на данни, репеленти, комари
- Ако не знаеш, кажи "не съм сигурен" вместо да измисляш
- Фокусирай се върху симптомите и подходящите лекарства

{existing_prompt}
"""

# Add temperature reduction to reduce creativity/hallucination
model.generate(
    prompt=prompt,
    temperature=0.3,  # Lower from 0.7 to reduce hallucination
    top_p=0.85,       # Lower from 0.95 to reduce randomness
)
```

**Testing plan**:
```bash
# Test on 25 failing queries
for query in failing_queries:
    result = pipeline.process(query)
    garbage = detect_garbage(result.response)
    assert len(garbage) == 0, f"Still has garbage: {garbage}"
```

**Pros**:
- Addresses root cause
- May improve overall quality
- No pattern maintenance

**Cons**:
- May reduce response creativity
- Requires A/B testing
- Model behavior unpredictable

---

### Option 3: Add Sentence-Level Filtering (Robust Fix)
**Effort**: 4-6 hours
**Risk**: Medium

Filter out irrelevant sentences using semantic similarity:

```python
# src/pipeline/response_cleaner.py (NEW)
from sentence_transformers import SentenceTransformer
import numpy as np

class ResponseCleaner:
    def __init__(self):
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

    def clean_response(self, response: str, original_query: str) -> str:
        """Remove sentences unrelated to the query."""
        sentences = response.split('.')

        # Embed query and each sentence
        query_emb = self.model.encode(original_query)
        sent_embs = self.model.encode(sentences)

        # Calculate similarity
        similarities = [
            np.dot(query_emb, sent_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(sent_emb))
            for sent_emb in sent_embs
        ]

        # Keep only sentences with similarity > threshold
        filtered = [
            sent for sent, sim in zip(sentences, similarities)
            if sim > 0.3  # Tune threshold
        ]

        return '. '.join(filtered)
```

**Pros**:
- Catches ALL irrelevant text (not just known patterns)
- Semantic understanding
- Future-proof

**Cons**:
- Adds latency (~100-200ms)
- Requires new dependency
- May filter valid content if threshold wrong

---

### Option 4: Model Replacement (Long-term Fix)
**Effort**: 1-2 weeks
**Risk**: High

Replace MedGemma 4B with a more stable model:

**Candidates**:
- **BioMistral-7B**: Medical model, better hallucination control
- **Llama-3-8B-Instruct**: General model, very reliable
- **GPT-4o-mini API**: Highest quality, external dependency

**Testing required**:
- Medical accuracy comparison
- Bulgarian language quality
- Hallucination rate
- Inference speed
- VRAM usage

---

## 📋 RECOMMENDED ACTION PLAN

**Phase 1 (Day 1 - Today)**: Implement Option 1 (Output Validation)
- Quick win to block known patterns
- Reduces 7% → ~2% garbage immediately
- Effort: 2-3 hours

**Phase 2 (Day 2)**: Implement Option 2 (Improve Prompt)
- Test with lower temperature (0.7 → 0.3)
- Add explicit "don't mention" instructions
- A/B test on 100 queries
- Effort: 3-4 hours

**Phase 3 (Week 2)**: Implement Option 3 if needed (Semantic Filtering)
- Only if Phases 1+2 don't get to <1% garbage
- Effort: 4-6 hours

**Phase 4 (Future)**: Evaluate Option 4 if still problematic
- Model replacement is last resort
- Requires extensive testing

---

**Files to Create/Modify**:
- NEW: `src/pipeline/response_validator.py` (Option 1)
- MODIFY: `src/medical_model.py` (Option 2)
- NEW: `src/pipeline/response_cleaner.py` (Option 3)
- MODIFY: `src/pipeline/orchestrator.py` (integration)

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

### 15. ✅ RESOLVED: Dockerfile Not Visible
**Status**: ✅ Verified — Both `Dockerfile` and `docker-compose.yml` exist in project root

---

### 16. ⚠️ ACTIVE: Unstaged Pipeline Refactoring Files
**Status**: ✅ Completed (Commit: 00d1a04)
**Original Issue**: New modules not committed
**Resolution**: All documentation updated and committed

---

## Prioritized Action Plan

### Remaining Active Issues

**Production Quality:**
1. **Template Compliance** (Issue #18) — Only 38% show active ingredients. Highest user-facing impact.
2. **Language Quality** (Issue #19) — 4 responses with English leaks
3. **Garbage Text** (Issue #17) — Partially mitigated with validator, needs further prompt/model work
4. **Performance Outliers** (Issue #20) — 49s max response time

**Code Quality:**
1. **Complete God Object refactor** (Issue #2) — 1,210 LOC, ~210 LOC from goal
2. **Fix Pipeline Tests** (Issue #21) — Mock paths need updating
3. **Evaluate unused quality tooling** (Issue #10) — evaluation.py, metrics.py, query_collector.py

**Infrastructure:**
1. **Redis Rate Limiting** (Issue #6) — Needed before horizontal scaling
2. **Memory Leak Investigation** (Issue #5) — VRAM cleanup after every request

---

## Metrics Tracking

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| **Production Quality** | | | |
| Garbage Text in Responses | 7% (mitigated with validator) | <1% | 🟡 |
| Template Compliance (Ingredients) | 38% (112/297) | >95% | 🔴 |
| Language Quality (BG ratio) | 95% avg (4 failures) | >98% | 🟡 |
| Response Time (p99) | 49.3s | <10s | 🔴 |
| Product Relevance | 99% (3 failures) | >99% | 🟢 |
| **Code Quality** | | | |
| Orchestrator Size | 855 LOC | <1,000 LOC | ✅ |
| Test Coverage | 74% | >80% | 🟡 |
| Unit Tests | 547 passing | 100% passing | ✅ |
| Security CVEs | 1 | 0 | 🟢 |
| **Architecture** | | | |
| Concurrent Workers | 1 | 1 (validated) | ✅ |
| Cache Hit Rate Visibility | 100% | 100% | ✅ |
| E2E Test Files | 5 files in tests/e2e/ | 5 (<400 LOC each) | ✅ |
| Architecture Paths | 1 (unified only) | 1 | ✅ |

---

## Review Schedule

- **Weekly**: Check cache hit rates, decide on removal
- **Bi-weekly**: Review orchestrator extraction progress
- **Monthly**: Re-run staff engineering review, update grade

**Last Review**: February 23, 2026 (Grade: B+, up from B-)
**Next Review**: March 23, 2026 (Target: A-)
