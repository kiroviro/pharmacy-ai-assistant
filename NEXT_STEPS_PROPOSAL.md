# Strategic Next Steps - Technical Debt Resolution

**Created**: February 13, 2026
**Context**: Review of TECHNICAL_DEBT.md (16 issues, 6 fixed, 10 remaining)
**Goal**: Maximize impact while building momentum

---

## 📊 Issue Analysis by ROI

| Issue | Priority | Effort | Impact | ROI Score | Blocks |
|-------|----------|--------|--------|-----------|--------|
| #9 Coverage | P2 | 1h | High | ⭐⭐⭐⭐⭐ | Nothing, enables all |
| #3 Concurrency | P0 | 2-4h | Critical | ⭐⭐⭐⭐⭐ | Scaling |
| #7 E2E Split | P2 | 3-4h | Medium | ⭐⭐⭐⭐ | Test speed |
| #4 Unified Proc | P1 | 3 days | High | ⭐⭐⭐⭐ | Issue #2 |
| #2 God Object | P0 | 5 days | Critical | ⭐⭐⭐ | Future dev |
| #6 Redis Rate | P1 | 4-6h | Medium | ⭐⭐⭐ | Multi-instance |
| #5 Memory Leak | P1 | 4-8h | Medium | ⭐⭐ | Performance |
| #10 Quality Tools | P2 | 2-3h | Low | ⭐ | None |

---

## 🎯 Recommended Roadmap

### Phase 1: Foundation & Data (Today - 4-5 hours)

**Goal**: Build confidence, gather critical data, prevent regressions

#### ✅ Step 1: Test Coverage Enforcement (1 hour)
**Why first?**
- Provides safety net for ALL future changes
- Immediate visibility into untested code
- Prevents coverage regressions
- Zero risk, high value

**Action**:
```bash
# 1. Add coverage configuration
cat >> pytest.ini << 'EOF'

[pytest]
addopts = --cov=src --cov-report=html --cov-report=term-missing
testpaths = tests
EOF

# 2. Run baseline coverage
pytest tests/ --cov=src --cov-report=term-missing

# 3. Set threshold based on current coverage (likely 60-70%)
# Start conservative, increase over time
pytest tests/ --cov=src --cov-fail-under=65

# 4. Document in README
echo "Current coverage: XX%" >> README.md
```

**Expected Outcome**: Know exactly what's tested, baseline established

**Deliverable**: Coverage report + badge in README

---

#### ✅ Step 2: MLX Concurrency Investigation (2-3 hours)
**Why second?**
- **Critical performance bottleneck** - could be 2-4x throughput gain
- Quick test reveals if claim is valid
- If it works: immediate production win
- If it fails: document limitation, move on

**Action**:
```bash
# Create load test
cat > tests/load_test_concurrency.py << 'EOF'
"""
Load test to validate MLX concurrent inference capability.

Tests whether ThreadPoolExecutor with max_workers>1 causes:
- Crashes
- Memory leaks
- Accuracy degradation
- Performance improvement

Run: python tests/load_test_concurrency.py
"""
import concurrent.futures
import time
from concurrent.futures import ThreadPoolExecutor

import mlx.core as mx

from src.medical_model import get_medical_model

def test_concurrent_inference():
    """Test concurrent vs sequential inference."""
    model = get_medical_model()
    model.load()  # Pre-load

    test_queries = [
        "имам главоболие",
        "боли ме гърлото",
        "имам температура",
        "кашлям от два дни",
        "имам алергия",
    ] * 4  # 20 queries total

    print("=" * 60)
    print("MLX CONCURRENCY LOAD TEST")
    print("=" * 60)

    # Baseline: Sequential (current state)
    print("\n1. Sequential (max_workers=1)...")
    start = time.time()
    results_seq = []
    for q in test_queries:
        try:
            result = model.get_medical_reasoning(q)
            results_seq.append(result)
        except Exception as e:
            print(f"ERROR in sequential: {e}")
            return False
    seq_time = time.time() - start
    print(f"   Time: {seq_time:.2f}s")
    print(f"   Success rate: {len(results_seq)}/{len(test_queries)}")

    # Clear cache before parallel test
    mx.metal.clear_cache()

    # Test: Parallel with 2 workers
    print("\n2. Parallel (max_workers=2)...")
    start = time.time()
    results_2 = []
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(model.get_medical_reasoning, q) for q in test_queries]
            for f in concurrent.futures.as_completed(futures):
                try:
                    results_2.append(f.result())
                except Exception as e:
                    print(f"   ERROR in parallel-2: {e}")
                    return False
        parallel_2_time = time.time() - start
        print(f"   Time: {parallel_2_time:.2f}s")
        print(f"   Success rate: {len(results_2)}/{len(test_queries)}")
        print(f"   Speedup: {seq_time/parallel_2_time:.2f}x")
    except Exception as e:
        print(f"   FAILED: {e}")
        return False

    # Clear cache before next test
    mx.metal.clear_cache()

    # Test: Parallel with 4 workers
    print("\n3. Parallel (max_workers=4)...")
    start = time.time()
    results_4 = []
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(model.get_medical_reasoning, q) for q in test_queries]
            for f in concurrent.futures.as_completed(futures):
                try:
                    results_4.append(f.result())
                except Exception as e:
                    print(f"   ERROR in parallel-4: {e}")
                    return False
        parallel_4_time = time.time() - start
        print(f"   Time: {parallel_4_time:.2f}s")
        print(f"   Success rate: {len(results_4)}/{len(test_queries)}")
        print(f"   Speedup: {seq_time/parallel_4_time:.2f}x")
    except Exception as e:
        print(f"   FAILED: {e}")
        return False

    # Results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Sequential:        {seq_time:.2f}s (baseline)")
    print(f"Parallel (2 work): {parallel_2_time:.2f}s ({seq_time/parallel_2_time:.2f}x speedup)")
    print(f"Parallel (4 work): {parallel_4_time:.2f}s ({seq_time/parallel_4_time:.2f}x speedup)")

    # Recommendation
    print("\n" + "=" * 60)
    print("RECOMMENDATION")
    print("=" * 60)

    if parallel_2_time < seq_time * 0.8:  # 20%+ improvement
        print("✅ MLX handles concurrency well!")
        print(f"   Recommend: Update api_server.py:42 to max_workers=2")
        print(f"   Expected throughput gain: {seq_time/parallel_2_time:.1f}x")
        return True
    else:
        print("❌ MLX concurrency provides no benefit")
        print("   Recommend: Keep max_workers=1, document limitation")
        return False

if __name__ == "__main__":
    success = test_concurrent_inference()
    exit(0 if success else 1)
EOF

# Run the test
python tests/load_test_concurrency.py

# If it succeeds and shows speedup, update api_server.py
```

**Expected Outcomes**:
- **Scenario A** (Best): 2x speedup → Update to max_workers=2, massive win
- **Scenario B** (Worst): Crashes → Keep max_workers=1, document why
- **Scenario C** (Neutral): Works but no speedup → Keep max_workers=1

**Decision Tree**:
```
Test Results?
├─ Speedup > 1.5x? → Change to max_workers=2 ✅
├─ Speedup 1.1-1.5x? → Change to max_workers=2 (marginal) ✅
├─ Speedup < 1.1x? → Keep max_workers=1 (no benefit) ⏸️
└─ Crashes? → Keep max_workers=1, add comment ❌
```

---

### Phase 2: Architecture Simplification (This Week - 1 day)

#### ✅ Step 3: Enable Unified Processor (3 hours + 1 week monitoring)
**Why third?**
- Simplifies architecture (removes parallel paths)
- 30% faster inference
- Makes future refactoring easier (less code to extract)
- Can rollback if issues

**Action**:
```bash
# Day 1: Enable and deploy to staging
# 1. Change default
sed -i '' 's/unified_processor_enabled: bool = Field(default=False/unified_processor_enabled: bool = Field(default=True/' src/config.py

# 2. Run full test suite
pytest tests/ -v

# 3. Test with sample queries
python -c "
from src.pipeline import get_pipeline
pipeline = get_pipeline()
result = pipeline.process('имам главоболие')
print('Unified processor test:', 'PASS' if result.response else 'FAIL')
"

# 4. Deploy to staging, monitor for 24 hours
#    - Error rate
#    - Latency (expect 30% improvement)
#    - VRAM usage (expect slight increase)

# Week 1: Gradual rollout
# - Day 1-2: 10% traffic
# - Day 3-4: 50% traffic
# - Day 5-7: 100% traffic
# - Compare accuracy: sample 100 queries, manual review

# Week 2: If stable, remove legacy code
# - Delete src/intent_classifier.py
# - Remove query translation from src/translator.py
# - Update tests
```

**Risk Mitigation**:
- Feature flag allows instant rollback
- Gradual rollout catches issues early
- Keep hard-coded safety layer (non-negotiable)

**Expected Outcome**: Simpler codebase, faster inference, easier to maintain

---

#### ✅ Step 4: Split E2E Test File (3-4 hours)
**Why fourth?**
- Better test organization before big refactor
- Enables parallel test execution
- Easier to navigate (400 LOC vs 1,628 LOC)
- Low risk, high developer experience value

**Action**:
```bash
# 1. Create test directory structure
mkdir -p tests/e2e

# 2. Split by category (use grep to extract)
# Medication queries
grep -A 20 "def test_medication_" e2e_query_tests.py > tests/e2e/test_medication_queries.py

# Symptom queries
grep -A 20 "def test_symptom_" e2e_query_tests.py > tests/e2e/test_symptom_queries.py

# Safety queries
grep -A 20 "def test_safety_" e2e_query_tests.py > tests/e2e/test_safety_queries.py

# Catalog queries
grep -A 20 "def test_catalog_" e2e_query_tests.py > tests/e2e/test_catalog_queries.py

# Edge cases
grep -A 20 "def test_edge_" e2e_query_tests.py > tests/e2e/test_edge_cases.py

# 3. Add imports and fixtures to each file
# 4. Verify all tests still pass
pytest tests/e2e/ -v

# 5. Delete original e2e_query_tests.py
git rm e2e_query_tests.py

# 6. Update CI if needed
```

**Expected Outcome**: 5 focused test files (~300-400 LOC each)

---

### Phase 3: The Big Refactor (Next 2-3 weeks)

#### ✅ Step 5: Extract QueryRouter (Week 1 of Strangler Fig)
**Why fifth?**
- Highest impact on maintainability
- Unlocks parallel development
- Reduces orchestrator by ~300 LOC (11%)
- Foundation for further extractions

**Prerequisites**:
- Test coverage in place (Phase 1, Step 1)
- Unified processor enabled (Phase 2, Step 3)
- E2E tests organized (Phase 2, Step 4)

**Action** (5 days):
```
Day 1-2: Extract methods
  - Create src/pipeline/query_router.py (expand existing file)
  - Move is_catalog_query, is_comparison_query, is_single_drug_name_query
  - Move is_help_clarification_query, get_help_clarification_message
  - Add comprehensive unit tests

Day 3: Integration
  - Update orchestrator to use QueryRouter class
  - Keep old methods as fallback (feature flag)
  - Run full test suite

Day 4: Validation
  - Deploy to staging
  - Run E2E tests
  - Compare behavior with baseline

Day 5: Cleanup
  - Remove old methods from orchestrator
  - Update documentation
  - Commit and deploy
```

**Expected Outcome**: orchestrator.py: 2,676 → 2,376 LOC (-300)

---

## 🚫 What NOT to Do (Yet)

### ❌ Don't start with God Object (Issue #2) directly
**Why?**
- It's the hardest problem
- Requires other issues fixed first
- Need test coverage before major refactor
- Need unified processor to reduce complexity

### ❌ Don't tackle Memory Leak (Issue #5) yet
**Why?**
- Requires deep profiling (4-8 hours)
- May be MLX limitation (can't fix)
- Not blocking other work
- Can defer until performance becomes critical

### ❌ Don't rush Redis Rate Limiting (Issue #6)
**Why?**
- Only needed for multi-instance deployment
- Not blocking current development
- Can add when scaling becomes necessary

---

## 📅 Timeline Summary

```
TODAY (4-5 hours):
  ✅ Test coverage enforcement (1h)
  ✅ MLX concurrency test (2-3h)
  Result: Foundation + critical data

THIS WEEK (1 day):
  ✅ Enable unified processor (3h + monitoring)
  ✅ Split E2E tests (3-4h)
  Result: Simpler architecture, better tests

NEXT WEEK (5 days):
  ✅ Extract QueryRouter from orchestrator
  Result: -300 LOC, better structure

WEEK AFTER (5 days):
  ✅ Extract ResponseBuilder from orchestrator
  Result: -400 LOC, clearer separation

FUTURE:
  - Extract ProductMatcher
  - Extract SafetyValidator
  - Redis rate limiting (when scaling)
  - Memory leak investigation (if needed)
```

---

## 🎯 Success Metrics

After Phase 1 (Today):
- ✅ Test coverage visible and enforced
- ✅ Know if concurrency is viable
- ✅ Have data for scaling decisions

After Phase 2 (This Week):
- ✅ Single architecture path (unified processor)
- ✅ Organized test suite
- ✅ 30% faster inference

After Phase 3 (Next 2-3 weeks):
- ✅ Orchestrator reduced from 2,676 → <2,000 LOC
- ✅ Parallel development unlocked
- ✅ Clearer code boundaries

---

## 🤔 Decision Points

**After Step 2 (Concurrency Test)**:
```
IF speedup > 1.5x:
  → Update api_server.py:42 to max_workers=2
  → Massive throughput win
ELSE:
  → Document limitation
  → Keep max_workers=1
```

**After Step 3 (Unified Processor - Week 1)**:
```
IF error rate < 1% AND accuracy >= 95%:
  → Continue to 100% rollout
  → Remove legacy code Week 2
ELSE:
  → Rollback to legacy
  → Investigate issues
  → Fix and retry
```

**After Step 4 (E2E Split)**:
```
IF all tests pass:
  → Delete original e2e_query_tests.py
ELSE:
  → Fix split, retry
```

---

## 💡 Key Insights from Review

1. **The document is well-structured** - Clear prioritization, good detail
2. **Suggested timeline is aggressive but achievable** - 8 hours this week
3. **God Object is correctly identified as P0** - But needs foundation first
4. **Quick wins are front-loaded** - Good strategy for momentum
5. **Missing**: Coverage should be first (provides safety net)

**Recommended Adjustment**:
- Original: #9 → #3 → #7 (coverage last)
- **Revised: #9 → #3 → #4 → #7 → #2** (coverage first, simplify architecture before big refactor)

---

## 🏁 Start Here

When you're ready to begin:

```bash
# 1. Read this document
# 2. Start with Phase 1, Step 1 (Test Coverage)
# 3. Take a break, review results
# 4. Continue to Step 2 (Concurrency Test)
# 5. Evaluate results, decide next steps
```

**Time Estimate**: 4-5 hours for Phase 1 (can be done in one session)

**Risk Level**: 🟢 Low (all changes are reversible, tests validate)

**Impact Level**: 🔴 High (foundation for all future work)

---

Good luck! 🚀
