# Overnight Work Plan - February 18-19, 2026

**User Status:** Sleeping - all changes pre-approved
**Goal:** Complete Week 2.5 validation + start Week 2 testing
**Expected Completion:** By morning

---

## Phase 1: E2E Test Validation (CURRENT - In Progress)

### Status: ⏳ Running
**Task:** Validate timeout implementation with 352 queries

### Success Criteria:
- [ ] All 352 queries succeed (100%)
- [ ] Max response time ≤20s
- [ ] P99 latency <10s
- [ ] Timeout rate <1%
- [ ] No server crashes

### Actions After Completion:
1. Analyze results JSON
2. Extract key metrics:
   - Max response time
   - P99 latency
   - Average response time
   - Timeout trigger count
   - Quality metrics (template compliance, product relevance)
3. Document results in `TIMEOUT_VALIDATION_RESULTS.md`
4. Update `SESSION_SUMMARY.md`

### Expected Outcome:
- ✅ Week 2.5 (Performance Fix) marked COMPLETE
- ✅ Timeout implementation validated for production

---

## Phase 2: Fix Product Store Tests (Task #8)

### Status: ⏳ Ready to Start
**Task:** Fix 11/15 failing tests in `tests/test_product_store.py`

### Current State:
- ✅ 15 test functions created (~340 LOC)
- ❌ 11 tests failing (mock format issues)
- ✅ 4 tests passing

### Root Cause:
Mock return format mismatch - tests expect wrong structure from `hybrid_search()`

### Fix Strategy:
1. **Read actual hybrid_search() return format**
   - Check what dict structure is returned
   - Note fields: id, score, title, brand, price, etc.

2. **Fix test mocks**
   - Update mock return values to match actual format
   - Fix assertions to check correct fields

3. **Run tests and verify**
   - `python3 -m pytest tests/test_product_store.py -v`
   - All 15 tests should pass

### Estimated Time: 1 hour

### Expected Outcome:
- ✅ All 15 product store tests passing
- ✅ Task #8 marked complete
- ✅ Product store coverage: 18% → 75%+

---

## Phase 3: Update Documentation

### Status: ⏳ After Phase 2
**Task:** Update all session documentation with final results

### Files to Update:

1. **SESSION_SUMMARY.md**
   - Mark Week 2.5 complete with metrics
   - Update Week 2 progress (20% → 40%)
   - Update files modified list
   - Update overall progress percentage

2. **TIMEOUT_VALIDATION_RESULTS.md**
   - Add actual E2E test metrics
   - Document timeout behavior observed
   - Mark validation as PASSED or note issues

3. **E2E_TEST_SUMMARY.md**
   - Add final test run results
   - Compare before/after metrics
   - Document any regressions or improvements

4. **REFACTORING_MASTER_PLAN.md**
   - Update Week 2.5 status to COMPLETE
   - Update Week 2 status with progress

### Estimated Time: 30 minutes

---

## Phase 4: Optional - Start Safety Tests (Task #9)

### Status: ⏳ If Time Permits
**Task:** Add safety edge case tests

### Only if Phases 1-3 complete with time remaining

### Test Cases to Add:
1. `test_multiple_emergency_symptoms()` - Multiple red flags in one query
2. `test_misspelled_emergency_symptom()` - "chset pain" vs "chest pain"
3. `test_emergency_buried_in_long_text()` - Red flag hidden in paragraph
4. `test_heartburn_not_chest_pain()` - False positive prevention
5. `test_severity_prioritization()` - High vs medium severity

### File: `tests/test_safety.py`
### Estimated Time: 2-3 hours

### Expected Outcome:
- ✅ Safety coverage: 77% → 85%+
- ✅ Task #9 marked complete (or in progress)

---

## Execution Plan

### Step 1: Monitor E2E Tests (~40 min)
```
Every 5 minutes:
  - Check log file size
  - Read last 50 lines
  - Look for completion marker

When complete:
  - Read full results from test_results.json
  - Extract metrics
  - Generate summary
```

### Step 2: Analyze E2E Results (~15 min)
```python
# Parse test_results.json
results = json.load(open('output/test_results.json'))

# Extract metrics
max_time = max(r['response_time_ms'] for r in results['results'])
avg_time = sum(r['response_time_ms'] for r in results['results']) / len(results['results'])
p99_time = calculate_p99(results['results'])
timeout_count = sum(1 for r in results['results'] if 'timeout' in r.get('error', '').lower())

# Validate
assert max_time <= 20000, f"Max time {max_time}ms exceeds 20s"
assert p99_time < 10000, f"P99 {p99_time}ms exceeds 10s"
assert timeout_count / len(results['results']) < 0.01, "Timeout rate >1%"
```

### Step 3: Fix Product Store Tests (~1 hour)
```bash
# 1. Understand current failure
python3 -m pytest tests/test_product_store.py -v --tb=short

# 2. Check actual return format
python3 -c "
from src.product_store import ProductStore
store = ProductStore()
store.load_products()
results = store.hybrid_search('главоболие', n_results=1)
print('Actual format:', results[0].keys())
"

# 3. Fix mocks in tests
# Edit tests/test_product_store.py

# 4. Verify all pass
python3 -m pytest tests/test_product_store.py -v
```

### Step 4: Update Documentation (~30 min)
```bash
# Update all markdown files with results
# Commit changes with detailed message
```

### Step 5: Safety Tests (If Time) (~2-3 hours)
```bash
# Add tests to tests/test_safety.py
# Run to verify
# Commit
```

---

## Success Metrics

### Minimum Success (Required):
- ✅ E2E tests complete and analyzed
- ✅ Week 2.5 validated (max ≤20s confirmed)
- ✅ Product store tests fixed (15/15 passing)
- ✅ Documentation updated

### Stretch Goals (If Time):
- ✅ Safety edge case tests started/completed
- ✅ Task #9 marked in progress or complete

---

## Rollback Plan

### If E2E Tests Fail:
1. Check failure reason in logs
2. If timeout still causing issues:
   - Adjust timeout values (15s → 20s for MedGemma)
   - Or revert to API-level timeout only
3. Document findings for user review

### If Product Store Tests Can't Be Fixed:
1. Document the issue clearly
2. Mark as blocked
3. Move to documentation updates
4. Let user review in morning

---

## Deliverables Expected in Morning

### Files Modified/Created:
1. ✅ `tests/test_product_store.py` - All tests passing
2. ✅ `SESSION_SUMMARY.md` - Updated with final results
3. ✅ `TIMEOUT_VALIDATION_RESULTS.md` - Final metrics
4. ✅ `E2E_TEST_SUMMARY.md` - Updated with new test run
5. ✅ `OVERNIGHT_WORK_PLAN.md` - This file
6. ✅ `OVERNIGHT_WORK_RESULTS.md` - Summary of completed work
7. ⏳ `tests/test_safety.py` - If time permits

### Task Status Updates:
- Task #12 (Performance Timeouts): ✅ COMPLETE (validated)
- Task #8 (Product Store Tests): ✅ COMPLETE (fixed)
- Task #9 (Safety Tests): ⏳ IN PROGRESS or ✅ COMPLETE

### Overall Progress:
- Week 1: ✅ 100%
- Week 2: 🔧 20% → 40%+ (or 60% if safety tests done)
- Week 2.5: ✅ 100% (validated)

---

## Timeline Estimate

```
Current Time:  22:00 (10 PM)
E2E Complete:  22:45 (10:45 PM)
Analysis:      23:00 (11:00 PM)
Tests Fixed:   00:00 (12:00 AM)
Docs Updated:  00:30 (12:30 AM)
Safety Tests:  03:00 (3:00 AM) - if time
Final Summary: 03:30 (3:30 AM)
```

**Expected completion:** 12:30 AM - 3:30 AM depending on scope

---

## Execution Status

**Current Phase:** Phase 1 - E2E Test Validation
**Status:** ⏳ Running (352 queries)
**Next:** Analyze results → Fix tests → Update docs → (Safety tests if time)

**Auto-approval:** ✅ All changes pre-approved by user

---

**Plan Created:** 2026-02-18 22:00
**Execution Start:** After E2E tests complete
**Expected Completion:** By morning (6-8 AM)
