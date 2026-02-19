# Test Contracts

Contract-based testing for ViaPharma components. Tests written against these contracts will survive refactoring as long as the behavior contract is maintained.

## What is Contract-Based Testing?

Contract-based testing focuses on **behavior** rather than **implementation**. Instead of testing internal details, we test:
- What inputs are accepted
- What outputs are produced
- What constraints are maintained

This makes tests resilient to refactoring—you can change how code works internally without breaking tests.

## Contracts

### 1. MedicalReasoningContract

Tests components that provide medical reasoning.

```python
from tests.contracts import MedicalReasoningBuilder
from tests.contracts.medical_reasoning_contract import assert_medical_reasoning_valid

# Build test data
reasoning = (MedicalReasoningBuilder()
    .with_symptoms(["headache", "fever"])
    .with_treatment_type("analgesics")
    .build())

# Verify contract
assert_medical_reasoning_valid(reasoning)
```

### 2. ProductMatchingContract

Tests components that match products to queries.

```python
from tests.contracts.product_matching_contract import assert_product_list_valid

# Test product matching
products = matcher.retrieve_candidates(reasoning, "headache")

# Verify contract
assert_product_list_valid(products, context="headache query", max_count=10)
```

### 3. SafetyCheckContract

Tests components that perform safety validation.

```python
from tests.contracts.safety_check_contract import assert_age_filtering_valid

# Test age filtering
filtered = validator.filter_by_age_appropriateness(products, "child fever")

# Verify contract
assert_age_filtering_valid(products, filtered, "child fever")
```

## Test Builders

Builders make it easy to create valid test data:

```python
from tests.contracts import MedicalReasoningBuilder, ProductBuilder

# Medical reasoning with fluent API
reasoning = (MedicalReasoningBuilder()
    .with_symptoms(["headache", "fever", "fatigue"])
    .with_likely_cause("common cold")
    .with_treatment_type("analgesics")
    .with_see_doctor(False)
    .build())

# Product with fluent API
product = (ProductBuilder()
    .with_id("1")
    .with_title("Paracetamol 500mg")
    .with_price(bgn=5.00, eur=2.50)
    .with_composition("Paracetamol 500mg")
    .for_children()  # Mark as child-appropriate
    .build())
```

## Convenience Functions

Quick test data creation:

```python
from tests.contracts import (
    simple_medical_reasoning,
    complex_medical_reasoning,
    simple_product,
    child_product,
    adult_product,
)

# Simple cases
reasoning = simple_medical_reasoning("headache", "analgesics")
product = simple_product("1", "Paracetamol 500mg")

# Child-specific
child_prod = child_product("2", "Child Paracetamol Syrup")

# Adult-specific
adult_prod = adult_product("3", "Adult Ibuprofen 400mg")
```

## Test Scenarios

Pre-defined scenarios for common cases:

```python
from tests.contracts.medical_reasoning_contract import MedicalReasoningTestScenarios

# Use standard scenario
scenario = MedicalReasoningTestScenarios.single_symptom_scenario()
# Returns: {"input": ["headache"], "expected_fields": [...], ...}

# Apply to your component
result = your_component.analyze(scenario["input"])
for field in scenario["expected_fields"]:
    assert hasattr(result, field)
```

## Benefits

1. **Survives Refactoring**: Change implementation without breaking tests
2. **Clear Intent**: Tests document expected behavior
3. **Consistent Testing**: Same scenarios across implementations
4. **Easy Maintenance**: Update contract once, all tests benefit
5. **Better Coverage**: Scenarios ensure edge cases are tested

## Migration Example

### Before (Implementation-Coupled):
```python
def test_product_matcher_uses_chromadb():
    """BREAKS if we change from ChromaDB to Elasticsearch"""
    matcher = ProductMatcher(product_store=chroma_store)
    # Test internal implementation details
    assert matcher.product_store.__class__.__name__ == "ChromaProductStore"
```

### After (Contract-Based):
```python
def test_product_matcher_retrieves_relevant_products():
    """SURVIVES implementation changes"""
    matcher = ProductMatcher(product_store=any_store)

    reasoning = simple_medical_reasoning("headache", "analgesics")
    products = matcher.retrieve_candidates(reasoning)

    # Test behavior, not implementation
    assert_product_list_valid(products, max_count=10)
    assert len(products) > 0, "Should find pain relievers for headache"
```

## Usage Guidelines

### DO:
- ✅ Test expected inputs and outputs
- ✅ Test behavior and constraints
- ✅ Use builders for test data
- ✅ Use assertions with context
- ✅ Test edge cases via scenarios

### DON'T:
- ❌ Test internal implementation details
- ❌ Test private methods
- ❌ Hard-code specific class names
- ❌ Assume specific algorithms
- ❌ Couple tests to data structures

## Examples

See `/tests/test_product_matcher.py` and `/tests/test_safety_validator.py` for examples of contract-based tests.

---

**Created**: Phase 3 of architecture refactoring
**Purpose**: Make tests resilient to refactoring
**Status**: Ready for use
