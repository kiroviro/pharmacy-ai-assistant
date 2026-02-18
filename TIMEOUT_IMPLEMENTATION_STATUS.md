# Timeout Implementation Status

**Date:** February 18, 2026 (Updated: concurrent.futures implementation)
**Goal:** Eliminate 49s outliers → Max 20s, P99 <10s

---

## ✅ Completed

### 1. MedGemma Timeout (15s) - DONE
**File:** `src/medical_model.py`

**Implementation:** concurrent.futures with ThreadPoolExecutor (async-safe)

**Changes:**
- ✅ Added `concurrent.futures.ThreadPoolExecutor` for timeout protection
- ✅ Added `MEDICAL_REASONING_TIMEOUT_SECONDS = 15.0` constant
- ✅ Created `_run_inference()` method (runs in thread pool)
- ✅ Added `_get_fallback_reasoning()` method for timeout fallback
- ✅ Modified `get_medical_reasoning()` to use `future.result(timeout=...)`
- ✅ Catches `FuturesTimeoutError` and returns fallback reasoning
- ✅ Tested imports successfully
- ✅ **Thread-safe and compatible with FastAPI async**

**Why concurrent.futures instead of signal:**
- Signal-based timeout (`signal.SIGALRM`) conflicts with async event loops
- Causes server crashes in FastAPI context
- concurrent.futures is async-safe and works in thread pools

**Fallback Logic:**
- Analyzes keywords in query (fever, pain, cough, allergy)
- Returns basic MedicalReasoning with generic treatment type
- Provides safe recommendations: "Rest, hydrate, consult pharmacist"

---

### 2. Vector Search Timeout (3s) - DONE
**File:** `src/product_store.py`

**Implementation:** concurrent.futures with ThreadPoolExecutor (async-safe)

**Changes:**
- ✅ Added `concurrent.futures.ThreadPoolExecutor` for timeout protection
- ✅ Added `VECTOR_SEARCH_TIMEOUT_SECONDS = 3.0` constant
- ✅ Created `_run_hybrid_search()` method (runs in thread pool)
- ✅ Modified `hybrid_search()` to use `future.result(timeout=...)`
- ✅ Added `_keyword_search_fallback()` method (~80 LOC)
- ✅ Catches `FuturesTimeoutError` and returns keyword fallback
- ✅ Tested imports successfully
- ✅ **Thread-safe and compatible with FastAPI async**

**Why concurrent.futures instead of signal:**
- Signal-based timeout conflicts with async server
- concurrent.futures works safely in thread pools
- No interference with FastAPI event loop

**Fallback Logic:**
- Performs simple keyword matching without embeddings
- Counts matches in title, brand, description
- Applies ingredient boost if specified
- Applies homeopathy penalty
- Much faster than vector search (no ML inference)

---

### 3. API-Level Timeout (20s) - DONE
**File:** `src/config.py`

**Changes:**
- ✅ API timeout mechanism already exists in `api_server.py` (_process_with_timeout)
- ✅ Updated default timeout from 60s → 20s in config
- ✅ Returns 504 error with Bulgarian message on timeout
- ✅ Applies to both streaming and non-streaming endpoints

**Implementation:**
- Uses asyncio.wait_for() to wrap pipeline execution
- Catches asyncio.TimeoutError and returns HTTPException 504
- Message: "Заявката отне твърде дълго. Моля, опитайте отново."

---

## ✅ All Timeouts Complete!

**Summary:**
1. ✅ MedGemma timeout (15s) with keyword-based fallback
2. ✅ Vector search timeout (3s) with keyword search fallback
3. ✅ API-level timeout (20s) with 504 error response

**Total implementation time:** ~2 hours

---

## Next Steps

1. **Run E2E tests** (1 hour)
   - Verify all 352 queries pass with new timeouts
   - Check timeout rate (<1%)
   - Verify fallback quality
   - Measure actual max and P99 latency

2. **Measure performance improvement** (30 min)
   - Run performance investigation script
   - Verify max response time <20s
   - Document results

---

## Code Ready to Test

### MedGemma with timeout:
```python
from src.medical_model import get_medical_model

model = get_medical_model()
try:
    # This will timeout after 15s and return fallback
    result = model.get_medical_reasoning("very complex query that might be slow")
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")
```

### Test fallback:
```python
# Force timeout by setting to 0.1s
result = model.get_medical_reasoning("test", timeout_seconds=0.1)
print(f"Fallback result: {result.treatment_type}")
# Should print generic fallback
```

---

## Files Modified

1. ✅ `src/medical_model.py`
   - +50 LOC (timeout context manager + fallback)
   - Modified `get_medical_reasoning()` signature

2. ⏳ `src/product_store.py`
   - +40 LOC (partial - timeout context added)
   - Need to finish hybrid_search wrapper

3. ⏳ `api_server.py`
   - Not started

---

**Status:** 50% complete, continuing...
