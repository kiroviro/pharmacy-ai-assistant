# E2E Query Tests

End-to-end tests for the ViaPharma API, organized by query category.

## Test Files

The original 1,628-line `e2e_query_tests.py` has been split into focused test suites:

### 1. **test_medication_queries.py** (~400 LOC, 77 queries)
- Medication availability ("Имате ли наличен Парацетамол?")
- Dosing questions ("Каква е максималната дневна доза?")
- Drug comparisons ("Кое е по-силно – Ибупрофен или Диклофенак?")
- Safety interactions ("Мога ли да комбинирам два обезболяващи?")

**Run:** `python test_medication_queries.py`
**Output:** `output/test_results_medications.json`

### 2. **test_symptom_queries.py** (~400 LOC, 89 queries)
- Symptom descriptions (83 queries: headache, fever, cough, etc.)
- Pregnancy queries (3 queries: safety during pregnancy/breastfeeding)
- Complex multi-symptom queries (3 queries: "кашлица, хрема и температура")

**Run:** `python test_symptom_queries.py`
**Output:** `output/test_results_symptoms.json`

### 3. **test_safety_queries.py** (~300 LOC, 75 queries)
- Drug safety (3 queries: interactions, double dose, alcohol)
- Pediatric queries (72 queries: infant/child dosing, age-appropriate products)

**Run:** `python test_safety_queries.py`
**Output:** `output/test_results_safety.json`

### 4. **test_catalog_queries.py** (~300 LOC, 118 queries)
- Cosmetics/skincare (38 queries: creams, sunscreen, hair products)
- Chronic conditions (80 queries: diabetes, hypertension, arthritis)

**Run:** `python test_catalog_queries.py`
**Output:** `output/test_results_catalog.json`

### 5. **test_edge_cases.py** (~228 LOC, 7 queries)
- Edge cases (4 queries: minimal input, single-word queries)
- Non-medical queries (3 queries: delivery, payment, hours)

**Run:** `python test_edge_cases.py`
**Output:** `output/test_results_edge_cases.json`

### 6. **e2e_helpers.py** (~700 LOC)
Shared utilities and validation logic:
- Product relevance checking (24 validation groups)
- Template compliance validation
- Response quality analysis
- Report generation

## Running Tests

### Individual Test Suite
```bash
cd tests/e2e
python test_medication_queries.py
python test_symptom_queries.py
python test_safety_queries.py
python test_catalog_queries.py
python test_edge_cases.py
```

### All Test Suites
```bash
cd tests/e2e
python run_all_e2e_tests.py
```

### Quick Smoke Test
Run just the edge cases (7 queries, ~1 minute):
```bash
python test_edge_cases.py
```

## Prerequisites

1. **Start API Server:**
   ```bash
   python api_server.py
   ```

2. **Ensure Product Catalog:**
   The tests load product titles from `output/products_*.csv` for validation.

## Test Validation

Each test validates:

- ✅ **Language Quality:** Bulgarian ratio > 80%
- ✅ **Template Compliance:** Correct section structure
- ✅ **Product Relevance:** Products match query intent (24 groups)
- ✅ **Safety Warnings:** Age restrictions, interactions, contraindications
- ✅ **Garbage Detection:** No hallucinated text
- ✅ **Medical Disclaimers:** Appropriate professional advice prompts

## Output Files

Each test suite generates a JSON report in `output/`:
- `test_results_medications.json`
- `test_results_symptoms.json`
- `test_results_safety.json`
- `test_results_catalog.json`
- `test_results_edge_cases.json`

Reports include:
- Per-query analysis (issues, warnings, severity)
- Performance metrics (response time)
- Quality scores (template compliance, relevance)
- Actionable recommendations for code fixes

## Migration from Old File

The original `e2e_query_tests.py` (root directory) remains for backward compatibility but is now deprecated. Use the new split structure for:
- ✅ Faster focused testing (run only relevant categories)
- ✅ Better maintainability (smaller, focused files)
- ✅ Parallel execution potential (run suites concurrently)
- ✅ Category-specific reports
