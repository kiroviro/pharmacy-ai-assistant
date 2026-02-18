# Performance Outlier Investigation: 49s Max Response Time

**Status:** 🔴 CRITICAL - Must fix
**Date:** February 18, 2026

---

## Current Performance

From E2E tests (352 queries):
- **Average:** 7.3s ✅ (acceptable for AI chatbot)
- **Minimum:** 89ms ✅ (cached response)
- **Maximum:** 49.3s ❌ (UNACCEPTABLE - users will timeout)
- **P99:** Unknown (not measured yet)

**Target:** P99 < 10s, Max < 15s

---

## Week 1 Instrumentation Added

We added per-stage timing in `orchestrator.py`:

```python
timings = {
    'intent_ms': ...,           # Intent classification
    'translation_bg_to_en_ms': ...,  # Translation
    'medical_reasoning_ms': ...,     # MedGemma inference
    'safety_check_ms': ...,          # Safety validation
    'vector_search_ms': ...,         # ChromaDB search
    'product_refinement_ms': ...,    # LLM product selection
    'response_formatting_ms': ...,   # Template generation
    'total_ms': ...
}
```

**Next Step:** Run instrumented pipeline on slow queries to identify bottleneck

---

## Likely Bottlenecks (Hypothesis)

### 1. MedGemma Inference (Most Likely)
**Normal:** 2-3s
**Outlier:** Could spike to 30-40s

**Causes:**
- Cold start (model not in memory)
- Very long input query (>500 tokens)
- MLX memory pressure (garbage collection pause)
- Rare token sequences (slow tokenization)

**Evidence:**
- MedGemma is 4B parameter model
- Running on Apple Silicon (MLX)
- No batching (processes one query at a time)

**Fix Options:**

**Option A: Add MedGemma Timeout (Quick Fix - 2 hours)**
```python
# src/medical_model.py
def get_medical_reasoning(self, symptoms: str, timeout_seconds: float = 15.0):
    import signal

    def timeout_handler(signum, frame):
        raise TimeoutError("MedGemma inference timed out")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(int(timeout_seconds))

    try:
        result = self._generate_with_retry(...)
        signal.alarm(0)  # Cancel alarm
        return result
    except TimeoutError:
        logger.warning(f"MedGemma timeout after {timeout_seconds}s, using fallback")
        return self._get_fallback_reasoning(symptoms)
```

**Option B: Model Quantization (Medium Fix - 1-2 days)**
- Use 4-bit quantized MedGemma instead of bf16
- **Benefit:** 50% faster inference, 75% less VRAM
- **Trade-off:** Slight quality reduction (~2-3%)
- **Implementation:** Re-download quantized model

**Option C: Caching + Pre-warming (Medium Fix - 4-6 hours)**
- Aggressive caching for common queries
- Pre-warm model on startup with dummy query
- Keep model in memory (disable unloading)

### 2. ChromaDB Vector Search
**Normal:** 50ms
**Outlier:** Could spike to 5-10s

**Causes:**
- Large collection (~10K products)
- Slow embedding generation
- Disk I/O (database not in memory)

**Fix Options:**

**Option D: Vector Search Timeout (Quick Fix - 1 hour)**
```python
# src/product_store.py
def hybrid_search(self, query: str, timeout_ms: int = 3000):
    import signal

    def timeout_handler(signum, frame):
        raise TimeoutError("Vector search timeout")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_ms // 1000)

    try:
        results = self._collection.query(...)
        signal.alarm(0)
        return results
    except TimeoutError:
        logger.warning("Vector search timeout, using keyword fallback")
        return self._keyword_search_fallback(query)
```

**Option E: Index Optimization (Medium Fix - 2-3 hours)**
- Ensure ChromaDB index is built (not rebuilt every search)
- Use HNSW index parameters for speed vs accuracy trade-off
- Keep embeddings in RAM (mmap)

### 3. Translation (Less Likely)
**Normal:** 180ms
**Outlier:** Could spike to 2-3s

**Causes:**
- Very long text (>500 words)
- MarianMT model not in memory

**Fix:** Already cached (Week 1), unlikely culprit

---

## Recommended Action Plan

### Phase 1: Quick Wins (This Week - 4 hours)

1. **Add MedGemma Timeout** (Option A)
   - Effort: 2 hours
   - Impact: Prevents >15s queries
   - Trade-off: Some queries get fallback reasoning

2. **Add Vector Search Timeout** (Option D)
   - Effort: 1 hour
   - Impact: Prevents ChromaDB hangs
   - Trade-off: Falls back to keyword search

3. **Add Request-Level Timeout** (API Layer)
   - Effort: 1 hour
   - Impact: Hard cap at 20s for any query
   ```python
   # api_server.py
   @app.post("/v1/chat/completions")
   async def chat_completions(request: ChatCompletionRequest):
       import asyncio

       try:
           result = await asyncio.wait_for(
               process_query(request),
               timeout=20.0  # 20-second hard timeout
           )
           return result
       except asyncio.TimeoutError:
           return {
               "error": "Request timed out. Please try a simpler query.",
               "timeout": 20
           }
   ```

### Phase 2: Performance Optimization (Week 10 - 2 days)

1. **Profile Slow Queries**
   - Use line_profiler on actual slow queries
   - Identify exact bottleneck (MedGemma vs ChromaDB vs other)

2. **Implement Targeted Fix**
   - If MedGemma: Model quantization (Option B)
   - If ChromaDB: Index optimization (Option E)
   - If Both: Both fixes

3. **Add P99 Monitoring**
   - Track P50, P95, P99 latency in metrics
   - Alert if P99 > 10s

---

## Proposed Immediate Fix (Today)

**Implement Phase 1 Quick Wins (4 hours total):**

1. ✅ **Week 1 instrumentation already added** (per-stage timing)
2. 🔧 **Add MedGemma timeout (15s)**
3. 🔧 **Add Vector search timeout (3s)**
4. 🔧 **Add API-level timeout (20s)**

**Expected Results:**
- Max response time: 49s → 20s (hard cap)
- P99 response time: Unknown → <15s (with fallbacks)
- Failed requests: 0% → <1% (timeout fallbacks)

**Code Changes:**
- `src/medical_model.py` - Add timeout to `get_medical_reasoning()`
- `src/product_store.py` - Add timeout to `hybrid_search()`
- `api_server.py` - Add request-level timeout middleware

---

## Testing Plan

1. **Run performance investigation script**
   - `python scripts/investigate_performance.py`
   - Identifies slow queries with current implementation

2. **Apply Phase 1 fixes**
   - Implement timeouts

3. **Re-run performance test**
   - Verify max time reduced to <20s
   - Check fallback quality (does timeout harm responses?)

4. **Run E2E tests**
   - Ensure 352 queries still pass
   - Verify no regression in quality

---

## Success Criteria

- ✅ P99 latency < 10s
- ✅ Max latency < 20s (hard timeout)
- ✅ <1% queries hit timeout
- ✅ Quality maintained (no degradation from fallbacks)
- ✅ All E2E tests pass

---

## Alternative: Accept Slow Queries

**NOT RECOMMENDED** but possible:

- Add loading indicator in UI ("Analyzing... this may take 30 seconds")
- Increase frontend timeout to 60s
- Only for complex medical queries

**Why this is bad:**
- Users abandon after 10s (industry standard)
- Poor UX for medical application
- Indicates underlying architectural problem

**Conclusion:** Must fix, not workaround with UI.

---

**Next Steps:**
1. Wait for `scripts/investigate_performance.py` to complete
2. Analyze which stage causes 49s
3. Implement Phase 1 timeouts (4 hours)
4. Re-test and verify <20s max

**Status:** Investigation in progress...
