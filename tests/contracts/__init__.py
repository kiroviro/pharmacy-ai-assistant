"""
Test Contracts for ViaPharma.

This package contains behavioral contracts for testing components.
Tests written against these contracts will survive refactoring as long as
the behavior contract is maintained.

Usage:
    from tests.contracts import MedicalReasoningBuilder, ProductBuilder
    from tests.contracts.medical_reasoning_contract import assert_medical_reasoning_valid

    # Build test data
    reasoning = (MedicalReasoningBuilder()
        .with_symptoms(["headache", "fever"])
        .with_treatment_type("analgesics")
        .build())

    # Verify contract
    assert_medical_reasoning_valid(reasoning)
"""

from tests.contracts.test_builders import (
    MedicalReasoningBuilder,
    ProductBuilder,
    simple_medical_reasoning,
    complex_medical_reasoning,
    simple_product,
    child_product,
    adult_product,
    product_list,
)

__all__ = [
    "MedicalReasoningBuilder",
    "ProductBuilder",
    "simple_medical_reasoning",
    "complex_medical_reasoning",
    "simple_product",
    "child_product",
    "adult_product",
    "product_list",
]
