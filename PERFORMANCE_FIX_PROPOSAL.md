# Performance Fix Proposal: Eliminate 49s Outliers

**Priority:** 🔥 CRITICAL
**Estimated Effort:** 2-3 days
**Expected Impact:** Max 49s → 20s, P99 → <10s

---

## Problem Statement

From E2E tests (352 queries):
- Average: 7.3s ✅
- **Maximum: 49.3s** ❌ **UNACCEPTABLE**
- Users will timeout/abandon after 10s

---

## Proposed Solution: Multi-Layer Timeout Strategy

### Layer 1: Component-Level Timeouts (Prevents cascading delays)

#### 1.1 MedGemma Timeout (15s max)
**File:** `src/medical_model.py`

```python
import asyncio
from functools import wraps

def with_timeout(timeout_seconds: float):
    """Decorator to add timeout to any method."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.warning(f"{func.__name__} timeout after {timeout_seconds}s")
                raise

        def sync_wrapper(*args, **kwargs):
            # For sync functions, use signal-based timeout
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(f"{func.__name__} timeout")

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout_seconds))
            try:
                result = func(*args, **kwargs)
                signal.alarm(0)
                return result
            except TimeoutError:
                logger.warning(f"{func.__name__} timeout after {timeout_seconds}s")
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


class MedicalModel:
    @with_timeout(15.0)  # 15-second max for medical reasoning
    def get_medical_reasoning(self, symptoms: str, **kwargs) -> MedicalReasoning:
        # Existing implementation
        ...

    def _get_fallback_reasoning(self, symptoms: str) -> MedicalReasoning:
        """Simple fallback when MedGemma times out."""
        return MedicalReasoning(
            symptoms=[symptoms],
            treatment_type="pain relief",  # Generic fallback
            treatment_category="analgesics",
            severity="mild",
            recommendations="Consult with pharmacist for appropriate treatment."
        )
```

**Usage in orchestrator:**
```python
# src/pipeline/orchestrator.py
try:
    medical_reasoning = self._get_medical_reasoning(translated)
except TimeoutError:
    logger.warning("MedGemma timeout, using fallback reasoning")
    medical_reasoning = self.medical_model._get_fallback_reasoning(translated)
    # Continue with fallback - still provide response
```

#### 1.2 Vector Search Timeout (3s max)
**File:** `src/product_store.py`

```python
class ProductStore:
    @with_timeout(3.0)  # 3-second max for vector search
    def hybrid_search(self, query: str, n_results: int = 10):
        # Existing implementation
        ...

    def _keyword_search_fallback(self, query: str, n_results: int = 10):
        """Simple keyword-based fallback when vector search times out."""
        # Split query into keywords
        keywords = query.lower().split()

        # Search for products matching any keyword in title
        # (This is fast, no vector embedding needed)
        matches = []
        for product in self._get_all_products():  # Cached list
            title_lower = product.title.lower()
            if any(kw in title_lower for kw in keywords):
                matches.append(product)

        return matches[:n_results]
```

**Usage:**
```python
try:
    products = self.product_store.hybrid_search(query)
except TimeoutError:
    logger.warning("Vector search timeout, using keyword fallback")
    products = self.product_store._keyword_search_fallback(query)
```

### Layer 2: API-Level Hard Timeout (20s absolute max)

**File:** `api_server.py`

```python
from fastapi import FastAPI, Request
import asyncio

@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    """Add hard 20-second timeout to all requests."""
    try:
        return await asyncio.wait_for(
            call_next(request),
            timeout=20.0
        )
    except asyncio.TimeoutError:
        logger.error(f"Request timeout: {request.url.path}")
        return JSONResponse(
            status_code=504,
            content={
                "error": "Request timeout. Please try a simpler query.",
                "timeout_seconds": 20,
                "suggestion": "Break your query into smaller parts."
            }
        )
```

---

## Implementation Plan

### Day 1: Add Timeouts (4 hours)

**Morning (2 hours):**
1. Add `with_timeout` decorator to `src/medical_model.py`
2. Add timeout to `get_medical_reasoning()`
3. Add `_get_fallback_reasoning()` method
4. Test: Verify fallback works when timeout hits

**Afternoon (2 hours):**
1. Add timeout to `product_store.hybrid_search()`
2. Add `_keyword_search_fallback()` method
3. Add API-level timeout middleware
4. Test: Verify 20s hard cap works

### Day 2: Test & Validate (4 hours)

**Morning (2 hours):**
1. Run E2E tests with timeouts enabled
2. Verify all 352 queries still pass
3. Check quality: How many hit fallback? Is quality acceptable?

**Afternoon (2 hours):**
1. Run performance investigation script
2. Measure new P99 and max latency
3. Document results

### Day 3: Root Cause Investigation (Optional - 4 hours)

**If outliers still exist:**
1. Use Week 1 instrumentation to identify exact bottleneck
2. Apply targeted fix:
   - If MedGemma: Model quantization or pre-warming
   - If ChromaDB: Index optimization
3. Re-test

---

## Expected Outcomes

### Before (Current State)
```
Average: 7.3s
P99: Unknown (likely 20-30s)
Max: 49.3s ❌
Timeout rate: 0%
```

### After (With Timeouts)
```
Average: 7.0s (slightly faster with fallbacks)
P99: <10s ✅
Max: 20s ✅ (hard cap)
Timeout rate: <1% (acceptable)
Fallback quality: 95%+ of normal (needs validation)
```

---

## Rollback Plan

If timeouts cause quality degradation:

1. **Disable at API level** (remove middleware)
   - Keeps component-level timeouts as warnings only

2. **Increase timeout limits**
   - MedGemma: 15s → 30s
   - API: 20s → 40s

3. **Full rollback** (remove all timeout code)
   - Git revert to pre-timeout state

---

## Testing Checklist

- [ ] Unit test: MedGemma timeout triggers fallback
- [ ] Unit test: Vector search timeout triggers keyword fallback
- [ ] Unit test: API timeout returns 504 error
- [ ] E2E test: All 352 queries pass with timeouts
- [ ] E2E test: No quality degradation (spot check 50 queries)
- [ ] Performance test: Max time <20s, P99 <10s
- [ ] Load test: Timeout rate <1% under normal load

---

## Alternative Approach: Pre-Investigation

**If you want to know the EXACT bottleneck before adding timeouts:**

Run detailed profiling on a slow query:
```python
# Use cProfile or line_profiler
import cProfile

profiler = cProfile.Profile()
profiler.enable()

result = pipeline.process("complex medical query here")

profiler.disable()
profiler.print_stats(sort='cumtime')
```

**Pros:** Know exactly what to optimize
**Cons:** Takes 1 day of investigation, still need timeouts as safety net

**Recommendation:** Add timeouts FIRST (2-3 days), then investigate if needed

---

## Decision Required

**Do you want to:**

**Option A: Implement timeouts immediately** (Recommended)
- Start today
- 2-3 days total
- Guaranteed max 20s response

**Option B: Profile first, then fix root cause**
- 1 day profiling
- 2-3 days fixing
- Might not need timeouts
- Higher risk (root cause might be unfixable)

**Option C: Both (safest but slower)**
- Add timeouts (2-3 days)
- Then profile and optimize (2-3 days)
- Best quality + safety
- 4-6 days total

**My recommendation:** **Option A** - Add timeouts now. Profiling can wait.

---

**Ready to proceed with timeout implementation?**
