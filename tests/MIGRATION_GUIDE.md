# Test Migration Guide: Implementation-Coupled → Contract-Based

This guide shows how to migrate existing tests to use contracts, making them resilient to refactoring.

## Why Migrate?

**Problem with Implementation-Coupled Tests:**
- Break when you refactor internal code
- Test "how" instead of "what"
- Brittle and hard to maintain
- Discourage refactoring

**Benefits of Contract-Based Tests:**
- Survive refactoring (test behavior, not implementation)
- Clear intent (what should happen)
- Easy to maintain (change contract once)
- Encourage refactoring

## Migration Pattern

### Before: Implementation-Coupled

```python
@pytest.fixture
def sample_products():
    """Manual product creation - duplicated across tests."""
    return [
        Product(
            id="1",
            title="Парацетамол 500 мг",
            brand="BrandA",
            composition="Paracetamol 500mg",
            description="Pain relief",
            price_bgn=5.00,
            price_eur=2.50,
        ),
        # ... more manual construction
    ]


def test_retrieve_with_category(sample_products):
    """Test implementation details."""
    mock_store = MockProductStore(sample_products)
    matcher = ProductMatcher(product_store=mock_store)

    # Manually construct reasoning (verbose, duplicated)
    reasoning = MedicalReasoning(
        symptoms=["headache"],
        likely_cause="tension",
        treatment_type="analgesics",
        warnings=[],
    )

    results = matcher.retrieve_candidates(reasoning, "headache")

    # Test implementation details
    assert len(results) > 0
    assert all(isinstance(p, Product) for p in results)
    # Missing: Contract validation!
```

### After: Contract-Based

```python
from tests.contracts import ProductBuilder, simple_medical_reasoning
from tests.contracts.product_matching_contract import assert_product_list_valid

@pytest.fixture
def sample_products():
    """Using builders - clear and concise."""
    return [
        (ProductBuilder()
         .with_id("1")
         .with_title("Парацетамол 500 мг")
         .with_brand("BrandA")
         .with_price(5.00, 2.50)
         .build()),
        # ... clearer, fluent API
    ]


def test_returns_valid_product_list(sample_products):
    """Test behavior using contracts."""
    mock_store = MockProductStore(sample_products)
    matcher = ProductMatcher(product_store=mock_store)

    # Use convenience function (clearer intent)
    reasoning = simple_medical_reasoning("headache", "analgesics")

    results = matcher.retrieve_candidates(reasoning, "headache", top_k=10)

    # Verify contract compliance (behavioral assertion)
    assert_product_list_valid(results, context="headache query", max_count=10)
    # Contract verifies: is list, valid products, respects max_count
```

## Step-by-Step Migration

### Step 1: Identify Tests to Migrate

Good candidates:
- ✅ Tests of public API methods
- ✅ Integration tests
- ✅ Tests that check behavior/output

Poor candidates:
- ❌ Tests of private methods (refactor to test public behavior)
- ❌ Tests of implementation details (ask: "will this break if I refactor?")

### Step 2: Replace Manual Construction with Builders

**Before:**
```python
product = Product(
    id="1",
    title="Paracetamol 500mg",
    price_bgn=5.00,
    price_eur=2.50,
    composition="Paracetamol 500mg",
    # ... 10 more fields
)
```

**After:**
```python
from tests.contracts import simple_product

product = simple_product("1", "Paracetamol 500mg", price=5.00)
```

Or with builder:
```python
from tests.contracts import ProductBuilder

product = (ProductBuilder()
    .with_id("1")
    .with_title("Paracetamol 500mg")
    .with_price(5.00)
    .for_children()  # Semantic helper
    .build())
```

### Step 3: Replace Assertions with Contract Validation

**Before:**
```python
results = matcher.retrieve_candidates(reasoning)

# Manual, incomplete checks
assert len(results) > 0
assert isinstance(results, list)
assert all(isinstance(p, Product) for p in results)
# Missing: Many other invariants!
```

**After:**
```python
from tests.contracts.product_matching_contract import assert_product_list_valid

results = matcher.retrieve_candidates(reasoning)

# Comprehensive contract check (one line!)
assert_product_list_valid(results, context="retrieve", max_count=10)
# Checks: is list, valid products, has required fields, respects max_count
```

### Step 4: Use Scenarios for Common Cases

**Before:**
```python
def test_single_symptom():
    reasoning = MedicalReasoning(...)  # Verbose
    # ... test logic

def test_multiple_symptoms():
    reasoning = MedicalReasoning(...)  # Duplicated
    # ... test logic
```

**After:**
```python
from tests.contracts.product_matching_contract import ProductMatchingTestScenarios

def test_scenario_simple_symptom():
    scenario = ProductMatchingTestScenarios.simple_symptom_scenario()

    reasoning = (MedicalReasoningBuilder()
        .with_symptoms(scenario["medical_reasoning"]["symptoms"])
        .with_treatment_type(scenario["medical_reasoning"]["treatment_type"])
        .build())

    results = matcher.retrieve_candidates(reasoning)

    # Verify using scenario expectations
    assert len(results) >= scenario["expected_behavior"]["min_results"]
```

## Common Patterns

### Pattern 1: Empty Input/Output

**Contract:** Empty input should return empty output

```python
def test_empty_store_returns_empty_list():
    matcher = ProductMatcher(product_store=MockProductStore([]))

    reasoning = simple_medical_reasoning("headache")
    results = matcher.retrieve_candidates(reasoning)

    # Contract: empty store → empty results
    assert_product_list_valid(results)
    assert len(results) == 0
```

### Pattern 2: Subset Relationship

**Contract:** Output should be subset of input

```python
def test_filter_returns_subset(sample_products):
    matcher = ProductMatcher(product_store=MockProductStore())

    filtered = matcher.filter_by_name_match(sample_products, "парацетамол")

    # Contract: filtered ⊆ original
    assert all(p in sample_products for p in filtered)
```

### Pattern 3: Size Constraints

**Contract:** Output should respect max_products

```python
def test_respects_max_products_limit(sample_products):
    matcher = ProductMatcher(product_store=MockProductStore())

    deduplicated = matcher.deduplicate_by_ingredient(sample_products, max_products=2)

    # Contract: result ≤ max_products
    assert_product_list_valid(deduplicated, max_count=2)
```

## Migration Checklist

For each test file:
- [ ] Import contract assertions (`assert_product_list_valid`, etc.)
- [ ] Import builders (`ProductBuilder`, `MedicalReasoningBuilder`)
- [ ] Import convenience functions (`simple_product`, `simple_medical_reasoning`)
- [ ] Replace manual Product construction with builders
- [ ] Replace manual MedicalReasoning construction with builders
- [ ] Replace manual assertions with contract validation
- [ ] Add context strings to assertions for better error messages
- [ ] Consider using test scenarios for common cases
- [ ] Verify all tests still pass
- [ ] Run with coverage to ensure no regression

## Examples

### Complete Migration Example

See `tests/test_product_matcher_contract_based.py` for a complete example of migrated tests.

**Key differences:**
1. Uses `ProductBuilder` for test data
2. Uses `simple_medical_reasoning()` for common cases
3. Uses `assert_product_list_valid()` for validation
4. Tests focus on behavior (contracts) not implementation
5. Clear context strings for debugging

### Side-by-Side Comparison

| Aspect | Before | After |
|--------|--------|-------|
| **Product creation** | 15 lines | 5 lines (builder) |
| **Assertions** | 3-5 manual checks | 1 contract check |
| **Intent** | Unclear | Crystal clear |
| **Refactor-safe** | ❌ Breaks easily | ✅ Survives refactoring |
| **Maintainability** | Low | High |

## FAQs

**Q: Should I migrate all tests at once?**
A: No! Migrate incrementally. Start with 1-2 files as examples.

**Q: What about old tests?**
A: Keep them! They still pass. Migrate opportunistically when you touch a file.

**Q: Can I mix both styles?**
A: Yes, but aim for consistency within a file.

**Q: Do mocks need contracts?**
A: No, mocks are OK. Contracts are for testing behavior of real components.

**Q: What if a contract doesn't fit my use case?**
A: Extend the contract! Add new assertion functions as needed.

---

**Status**: Phase 4 migration in progress
**Next**: Migrate SafetyValidator tests
**Reference**: `tests/contracts/README.md` for contract documentation
