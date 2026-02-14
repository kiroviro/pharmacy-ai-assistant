# MLX Concurrency Test Results

**Date**: February 13, 2026
**Test**: `tests/load_test_concurrency.py`
**Objective**: Validate if MLX can handle concurrent inference with ThreadPoolExecutor

---

## Executive Summary

**Result**: ❌ **MLX DOES NOT SUPPORT CONCURRENT INFERENCE**

The claim in `api_server.py:42` that "MLX doesn't handle concurrent inference well" is **VALIDATED**.

**Recommendation**: ✅ **KEEP** `max_workers=1`

---

## Test Methodology

### Test Setup
- **Model**: MedGemma 4B (MLX format)
- **Hardware**: Apple Silicon Mac (M-series)
- **Test queries**: 20 unique Bulgarian medical queries
- **Cache**: Disabled (`use_cache=False`) to measure actual inference time

### Test Sequence
1. **Sequential baseline** (max_workers=1): Process 20 queries one at a time
2. **Parallel test** (max_workers=2): Process 20 queries with 2 concurrent workers
3. **Parallel test** (max_workers=4): Process 20 queries with 4 concurrent workers

---

## Results

### Run 1: Cache Artifact (Invalid)
**Issue**: Initial test used duplicate queries + cache enabled
**Result**: Parallel tests returned cached results instantly (astronomical "speedups")
**Conclusion**: Test was flawed, results invalid

### Run 2: Actual Inference (Valid)
**Setup**: 20 unique queries, cache disabled (`use_cache=False`)

**Sequential Test**:
- ✅ Completed successfully
- Time: 54.84s for 20 queries
- Average: 2.742s per query
- Success rate: 100% (20/20)

**Parallel Test (2 workers)**:
- ❌ **CRASHED with Segmentation Fault**
- Exit code: 139 (SIGSEGV)
- Error: Process terminated abnormally
- Success rate: 0%

**Parallel Test (4 workers)**:
- ⏭️ Skipped (2 workers already crashed)

---

## Technical Analysis

### Why MLX Doesn't Support Concurrency

**Root Cause**: MLX (Metal acceleration framework) likely has:
1. **Thread-unsafe global state** - Metal command buffers or GPU contexts
2. **No internal locking** - Assumes single-threaded usage
3. **Metal API limitations** - Apple's Metal framework may not support concurrent contexts

**Evidence**:
- Immediate segfault when attempting concurrent inference
- No graceful degradation (crash, not slow performance)
- Exit code 139 = memory access violation

**Similar Issues in Other Frameworks**:
- Early versions of TensorFlow had similar GPU concurrency issues
- CUDA requires explicit stream management for concurrency
- Many ML frameworks default to single-threaded inference

---

## Implications

### Current Architecture (Correct)
```python
# api_server.py:42
executor = ThreadPoolExecutor(max_workers=1)  # ✅ CORRECT
```

**Why this is optimal**:
- Prevents crashes/segfaults
- Ensures stable inference
- Graceful degradation under load (queuing vs crashing)

### Performance Characteristics

**Single Request Latency**: 2.7s per query (acceptable)

**Maximum Throughput** (current):
- Requests/minute: ~22 (60s / 2.7s per query)
- Requests/hour: ~1,333

**Latency Under Load**:
| Requests/min | Average Latency | Queue Time |
|--------------|-----------------|------------|
| 10 req/min   | 2.7s           | 0s         |
| 20 req/min   | 5.4s           | 2.7s       |
| 30 req/min   | 8.1s           | 5.4s       |

---

## Recommendations

### 1. ✅ Keep Current Configuration
```python
# api_server.py:42
executor = ThreadPoolExecutor(max_workers=1)
# VALIDATED: MLX does not support concurrent inference (segfault with max_workers>1)
# See: MLX_CONCURRENCY_TEST_RESULTS.md
```

### 2. 📝 Update Documentation
- Add reference to this test in the comment
- Document performance characteristics
- Explain why single-threaded is necessary

### 3. 🔄 Alternative Scaling Strategies

If you need more throughput:

**Option A: Horizontal Scaling (Recommended)**
```yaml
# Deploy multiple pods/containers
replicas: 3  # 3x throughput = ~66 req/min total
```
- Each pod runs max_workers=1
- Load balancer distributes requests
- Linear scaling (3 pods = 3x throughput)
- No code changes needed

**Option B: Model Optimization**
- Quantize model (4-bit → 2-bit)
- Use smaller model variant
- Trade accuracy for speed
- Could reduce latency by 30-50%

**Option C: Batching**
- Process multiple queries in single inference call
- MLX might support batch inference
- Requires code changes
- May reduce latency per query

**Option D: GPU Splitting** (Advanced)
- Run multiple isolated processes on same GPU
- Each process has own Metal context
- Requires process pool, not thread pool
- More complex but potentially viable

### 4. ⚠️ Monitor for Future MLX Updates
- Check MLX changelog for concurrency support
- Re-run this test after major MLX upgrades
- Apple may add thread-safe APIs in future

---

## Conclusion

**The claim in api_server.py:42 is CORRECT and VALIDATED.**

MLX does not support concurrent inference. Attempting to use `max_workers>1` causes:
- Immediate segmentation fault (exit code 139)
- Process crash (no graceful degradation)
- 0% success rate

**Current configuration is optimal for stability.**

For scaling beyond ~22 req/min, use **horizontal pod scaling** rather than threading.

---

## Test Artifacts

**Test Script**: `tests/load_test_concurrency.py`
**Run Command**: `PYTHONPATH=. python tests/load_test_concurrency.py`
**Expected Result**: Segfault with exit code 139

**To reproduce**:
```bash
cd /Users/kiril/IdeaProjects/medgemma
PYTHONPATH=. python tests/load_test_concurrency.py
# Expected: Crash with exit code 139
```

---

## Next Actions

- [x] Validate MLX concurrency (DONE - crashes)
- [ ] Update api_server.py comment with test reference
- [ ] Document in TECHNICAL_DEBT.md (Issue #3 resolved)
- [ ] Consider horizontal scaling for production
- [ ] Monitor MLX releases for future concurrency support

**Issue #3 Status**: ✅ RESOLVED (keep max_workers=1, claim validated)
