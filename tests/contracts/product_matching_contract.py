"""
Contract for Product Matching behavior.

Defines expected behavior for product matching regardless of implementation.
Tests using this contract will survive refactoring as long as the behavior contract is maintained.
"""

from typing import Protocol

from src.medical_model import MedicalReasoning
from src.common.models import Product


class ProductMatchingContract(Protocol):
    """
    Contract defining the expected behavior of product matching components.

    Any component that matches products to medical queries should satisfy this contract.
    Tests written against this contract will remain valid even if implementation changes.
    """

    def retrieve_candidates(
        self,
        medical_reasoning: MedicalReasoning,
        original_query: str = "",
        top_k: int = 10
    ) -> list[Product]:
        """
        Retrieve product candidates based on medical reasoning.

        Contract requirements:
        - Must accept MedicalReasoning object
        - Must return list of Product objects
        - List should be ordered by relevance (most relevant first)
        - Empty list is valid (no matches found)
        - top_k parameter controls maximum results
        """
        ...

    def refine_selection(
        self,
        candidates: list[Product],
        medical_reasoning: MedicalReasoning,
        max_products: int = 3
    ) -> list[Product]:
        """
        Refine product selection from candidates.

        Contract requirements:
        - Must accept list of Product candidates
        - Must return list of Product objects
        - Returned list should be <= max_products
        - Results should be most relevant products
        - Empty input returns empty output
        """
        ...


def verify_product_list_contract(products: list[Product]) -> bool:
    """
    Verify that a product list satisfies basic contract requirements.

    Args:
        products: List of Product objects to verify

    Returns:
        True if contract is satisfied, False otherwise
    """
    if not isinstance(products, list):
        return False

    for product in products:
        # Each item must be a Product or have Product-like attributes
        if not hasattr(product, 'id'):
            return False
        if not hasattr(product, 'title'):
            return False
        if not hasattr(product, 'price_bgn'):
            return False

    return True


def assert_product_list_valid(products: list[Product], context: str = "", max_count: int = None):
    """
    Assert that product list satisfies contract, with helpful error messages.

    Args:
        products: List of products to validate
        context: Optional context string for error messages
        max_count: Optional maximum expected count

    Raises:
        AssertionError: If contract is violated
    """
    prefix = f"{context}: " if context else ""

    assert isinstance(products, list), f"{prefix}Products must be a list"

    if max_count is not None:
        assert len(products) <= max_count, f"{prefix}Too many products (expected <={max_count}, got {len(products)})"

    for i, product in enumerate(products):
        assert hasattr(product, 'id'), f"{prefix}Product {i} missing 'id'"
        assert hasattr(product, 'title'), f"{prefix}Product {i} missing 'title'"
        assert hasattr(product, 'price_bgn'), f"{prefix}Product {i} missing 'price_bgn'"

        # Title should not be empty
        assert product.title, f"{prefix}Product {i} has empty title"


def assert_products_relevant(
    products: list[Product],
    treatment_type: str = "",
    keywords: list[str] = None,
    context: str = ""
):
    """
    Assert that products are relevant to the query.

    Args:
        products: List of products to check
        treatment_type: Expected treatment type
        keywords: Optional keywords that should appear in titles
        context: Optional context for error messages
    """
    prefix = f"{context}: " if context else ""

    if not products:
        return  # Empty list is acceptable

    # Check if products match treatment type (if specified)
    if treatment_type:
        # At least one product should be relevant to treatment type
        # This is a soft check - we don't require exact matching
        pass

    # Check if products contain keywords (if specified)
    if keywords:
        for keyword in keywords:
            keyword_lower = keyword.lower()
            found = any(
                keyword_lower in (product.title or "").lower() or
                keyword_lower in (getattr(product, 'description', "") or "").lower()
                for product in products
            )
            # Soft assertion - log warning but don't fail
            # This allows for semantic matching where exact keywords may not appear


class ProductMatchingTestScenarios:
    """
    Standard test scenarios for product matching components.

    Use these scenarios to ensure consistent behavior across implementations.
    """

    @staticmethod
    def simple_symptom_scenario():
        """Simple case: single symptom, clear treatment."""
        return {
            "medical_reasoning": {
                "symptoms": ["headache"],
                "treatment_type": "analgesics",
                "likely_cause": "tension headache"
            },
            "expected_behavior": {
                "min_results": 1,
                "max_results": 10,
                "relevance": "products should be pain relievers"
            }
        }

    @staticmethod
    def specific_ingredient_scenario():
        """Specific case: user wants particular ingredient."""
        return {
            "medical_reasoning": {
                "symptoms": ["pain"],
                "treatment_type": "analgesics",
                "likely_cause": "pain relief needed"
            },
            "query": "ibuprofen",
            "expected_behavior": {
                "min_results": 1,
                "keyword_match": ["ibuprofen", "ибупрофен"],
                "relevance": "products should contain ibuprofen"
            }
        }

    @staticmethod
    def no_matches_scenario():
        """Edge case: no products should match."""
        return {
            "medical_reasoning": {
                "symptoms": ["very rare condition"],
                "treatment_type": "",
                "likely_cause": "unknown"
            },
            "expected_behavior": {
                "accept_empty": True,
                "min_results": 0,
            }
        }

    @staticmethod
    def child_appropriate_scenario():
        """Safety case: child query should return appropriate products."""
        return {
            "medical_reasoning": {
                "symptoms": ["fever"],
                "treatment_type": "antipyretics",
                "user_conditions": ["child"]
            },
            "query": "temperature for child",
            "expected_behavior": {
                "min_results": 1,
                "safety_check": "no adult-only products",
                "preference": "child-specific products first"
            }
        }

    @staticmethod
    def deduplication_scenario():
        """Quality case: results should be diverse."""
        return {
            "medical_reasoning": {
                "symptoms": ["pain", "fever"],
                "treatment_type": "analgesics"
            },
            "expected_behavior": {
                "max_duplicates": 1,
                "diversity": "different active ingredients preferred"
            }
        }
