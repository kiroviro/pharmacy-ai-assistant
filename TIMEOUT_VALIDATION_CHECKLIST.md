# Timeout Implementation Validation Checklist

**Date:** February 18, 2026
**Test Suite:** E2E Query Tests (352 queries)
**Status:** ⏳ RUNNING

---

## Validation Criteria

### 1. Response Time Targets ✅
**Requirement:** Max response time <20s (hard cap)

**Before implementation:**
- Max: 49.3s ❌
- P99: Unknown (likely 20-30s)
- Average: 7.3s

**Expected after:**
- Max: **≤20s** ✅
- P99: **<10s** ✅
- Average: **~7s** (unchanged or slightly faster)

**Measurement:**
- [ ] Max response time across all 352 queries
- [ ] P99 latency (99th percentile)
- [ ] Average response time
- [ ] Distribution histogram

---

### 2. Timeout Rate ✅
**Requirement:** <1% of requests hit timeout

**What to measure:**
- [ ] Number of requests that hit MedGemma timeout (15s)
- [ ] Number of requests that hit vector search timeout (3s)
- [ ] Number of requests that hit API timeout (20s)
- [ ] Total timeout rate: (timeouts / total requests) × 100%

**Acceptable:**
- Total timeout rate <1% ✅
- API timeouts = 0 (should be caught by component timeouts) ✅

---

### 3. Fallback Quality ✅
**Requirement:** Fallback responses maintain >90% quality

**What to check:**
- [ ] When MedGemma times out, keyword fallback provides reasonable treatment type
- [ ] When vector search times out, keyword fallback returns relevant products
- [ ] Product relevance rate unchanged (or within 5% of baseline)
- [ ] Template compliance unchanged

**Spot check:**
- [ ] Review 10-20 responses that used fallbacks
- [ ] Verify they're still medically safe
- [ ] Verify products are still relevant

---

### 4. Regression Testing ✅
**Requirement:** No degradation in existing metrics

**Baseline (before timeouts):**
- Success rate: ~100%
- Product relevance: varies by category
- Template compliance: 38% → ~95% (after ingredient mapping fix)
- Safety: 100% (no red flags missed)

**After timeouts:**
- [ ] Success rate: still ~100%
- [ ] Product relevance: no significant drop
- [ ] Template compliance: maintained at ~95%
- [ ] Safety: still 100%

---

### 5. Performance Logging ✅
**Requirement:** Per-stage timing captured

**Check logs for:**
- [ ] `intent_ms` - Intent classification timing
- [ ] `translation_bg_to_en_ms` - Translation timing
- [ ] `medical_reasoning_ms` - MedGemma inference timing
- [ ] `safety_check_ms` - Safety validation timing
- [ ] `vector_search_ms` - ChromaDB search timing
- [ ] `product_refinement_ms` - LLM product selection timing
- [ ] `response_formatting_ms` - Template generation timing
- [ ] `total_ms` - Total pipeline time

**Analysis:**
- [ ] Identify which stage causes the slowest queries
- [ ] Verify timeouts trigger on the right stages
- [ ] Check if fallbacks are actually faster

---

## Test Execution

### Command
```bash
python3 e2e_query_tests.py
```

### Expected Duration
- 352 queries
- ~7s average per query
- Total: **~40 minutes**

### Output Files
- `test_results.json` - Detailed results
- `e2e_test_output.log` - Console output
- Server logs - Per-stage timing metrics

---

## Success Criteria Summary

✅ **PASS** if:
1. Max response time ≤20s
2. P99 latency <10s
3. Timeout rate <1%
4. Fallback quality >90%
5. No regression in existing metrics
6. All 352 queries complete successfully

❌ **FAIL** if:
- Any query takes >20s
- Timeout rate >1%
- Fallback quality drops significantly
- Test failures increase

⚠️ **INVESTIGATE** if:
- P99 latency >10s
- Timeout rate 0.5-1%
- Product relevance drops >5%

---

## Post-Test Actions

### If PASS:
1. ✅ Mark timeout implementation as production-ready
2. ✅ Update SESSION_SUMMARY.md with results
3. ✅ Document actual performance metrics
4. ✅ Proceed to Week 2 testing tasks

### If FAIL:
1. ❌ Analyze which queries are timing out
2. ❌ Check if timeouts are too aggressive
3. ❌ Investigate fallback quality issues
4. ❌ Adjust timeout values if needed (e.g., 15s → 20s for MedGemma)

### If INVESTIGATE:
1. ⚠️ Review borderline cases
2. ⚠️ Check if specific query types are problematic
3. ⚠️ Consider optimizations before adjusting timeouts
4. ⚠️ Profile slow queries to find root cause

---

**Test initiated:** 2026-02-18 13:09
**Test status:** Running (352 queries in progress)
