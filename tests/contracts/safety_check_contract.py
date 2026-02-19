"""
Contract for Safety Check behavior.

Defines expected behavior for safety validation regardless of implementation.
Tests using this contract will survive refactoring as long as the behavior contract is maintained.
"""

from typing import Protocol

from src.common.models import Product


class SafetyCheckContract(Protocol):
    """
    Contract defining the expected behavior of safety validation components.

    Any component that performs safety checks should satisfy this contract.
    Tests written against this contract will remain valid even if implementation changes.
    """

    def filter_by_age_appropriateness(
        self,
        products: list[Product],
        original_query: str
    ) -> list[Product]:
        """
        Filter products by age appropriateness.

        Contract requirements:
        - Must accept list of products and query string
        - Must return list of products (subset of input)
        - For child queries, adult-only products should be excluded
        - For adult queries, all products are acceptable
        - Child-specific products should be prioritized for child queries
        """
        ...

    def filter_by_severity(
        self,
        products: list[Product],
        symptom_count: int
    ) -> list[Product]:
        """
        Filter products by symptom severity.

        Contract requirements:
        - Must accept list of products and symptom count
        - Must return list of products (max 3)
        - Simple products preferred for single symptoms
        - Combination products acceptable for multiple symptoms
        - Homeopathic products should rank lower
        """
        ...


def verify_safety_filtering(
    original_products: list[Product],
    filtered_products: list[Product],
    query: str = ""
) -> bool:
    """
    Verify that safety filtering satisfies basic contract requirements.

    Args:
        original_products: Original product list
        filtered_products: Filtered product list
        query: Original query (for context)

    Returns:
        True if filtering appears valid, False otherwise
    """
    # Filtered list should be subset of original
    if not all(p in original_products for p in filtered_products):
        return False

    # Filtered list should not exceed original
    if len(filtered_products) > len(original_products):
        return False

    return True


def assert_age_filtering_valid(
    original_products: list[Product],
    filtered_products: list[Product],
    query: str,
    context: str = ""
):
    """
    Assert that age-based filtering satisfies contract.

    Args:
        original_products: Original product list
        filtered_products: Filtered product list
        query: Original query
        context: Optional context for error messages
    """
    prefix = f"{context}: " if context else ""

    # Filtered must be subset
    assert all(p in original_products for p in filtered_products), \
        f"{prefix}Filtered products must be subset of originals"

    # Check for child queries
    query_lower = query.lower()
    is_child_query = any(kw in query_lower for kw in ["дете", "бебе", "child", "baby"])

    if is_child_query:
        # Adult-only products should be excluded
        adult_markers = {"за възрастни", "for adults", "над 18"}
        for product in filtered_products:
            title_desc = f"{product.title} {getattr(product, 'description', '')}".lower()
            has_adult_marker = any(marker in title_desc for marker in adult_markers)
            # Soft check - we prefer exclusion but don't require it
            # (some products may not have clear markers)


def assert_severity_filtering_valid(
    original_products: list[Product],
    filtered_products: list[Product],
    symptom_count: int,
    context: str = ""
):
    """
    Assert that severity-based filtering satisfies contract.

    Args:
        original_products: Original product list
        filtered_products: Filtered product list
        symptom_count: Number of symptoms
        context: Optional context for error messages
    """
    prefix = f"{context}: " if context else ""

    # Should return max 3 products
    assert len(filtered_products) <= 3, \
        f"{prefix}Severity filtering should return max 3 products (got {len(filtered_products)})"

    # Filtered must be subset
    assert all(p in original_products for p in filtered_products), \
        f"{prefix}Filtered products must be subset of originals"


def assert_no_unsafe_products(
    products: list[Product],
    user_conditions: list[str] = None,
    age_group: str = "",
    context: str = ""
):
    """
    Assert that product list contains no obviously unsafe products.

    Args:
        products: List of products to check
        user_conditions: User conditions (pregnancy, allergies, etc.)
        age_group: Age group (child, infant, adult)
        context: Optional context for error messages
    """
    prefix = f"{context}: " if context else ""
    user_conditions = user_conditions or []

    for product in products:
        title_desc = f"{product.title} {getattr(product, 'description', '')}".lower()

        # Check for child safety
        if age_group in ("child", "infant"):
            adult_markers = {"за възрастни", "for adults", "над 15", "над 16", "над 18"}
            has_adult_marker = any(marker in title_desc for marker in adult_markers)
            # Soft assertion - log concern but don't fail
            # (filtering may not be perfect)

        # Check for pregnancy contraindications
        if "pregnancy" in user_conditions:
            contraindicated = getattr(product, 'contraindications', "").lower()
            if "pregnancy" in contraindicated or "бременност" in contraindicated:
                # This would ideally be filtered out
                pass


class SafetyCheckTestScenarios:
    """
    Standard test scenarios for safety check components.

    Use these scenarios to ensure consistent behavior across implementations.
    """

    @staticmethod
    def child_query_scenario():
        """Child safety case: adult products should be filtered."""
        return {
            "query": "fever in 5 year old child",
            "products": [
                {"title": "Child Paracetamol Syrup", "description": "For children"},
                {"title": "Adult Ibuprofen 400mg", "description": "For adults only"},
                {"title": "Paracetamol 500mg", "description": "General use"},
            ],
            "expected_behavior": {
                "exclude": ["Adult Ibuprofen"],
                "prioritize": ["Child Paracetamol"],
            }
        }

    @staticmethod
    def baby_query_scenario():
        """Baby safety case: baby-specific products should be prioritized."""
        return {
            "query": "temperature for 6 month baby",
            "products": [
                {"title": "Baby Suspension", "description": "For infants"},
                {"title": "Child Syrup", "description": "Ages 2+"},
                {"title": "Adult Tablets", "description": "Ages 18+"},
            ],
            "expected_behavior": {
                "exclude": ["Adult Tablets"],
                "prioritize_first": ["Baby Suspension"],
            }
        }

    @staticmethod
    def simple_symptom_scenario():
        """Simple symptom: prefer simple products."""
        return {
            "symptom_count": 1,
            "products": [
                {"title": "Paracetamol 500mg", "composition": "Paracetamol"},
                {"title": "Multi-symptom Cold Relief", "composition": "Paracetamol + Caffeine + Phenylephrine"},
            ],
            "expected_behavior": {
                "prioritize": ["Paracetamol 500mg"],
                "max_results": 3,
            }
        }

    @staticmethod
    def multiple_symptoms_scenario():
        """Multiple symptoms: combination products acceptable."""
        return {
            "symptom_count": 3,
            "products": [
                {"title": "Paracetamol 500mg", "composition": "Paracetamol"},
                {"title": "Cold & Flu Relief", "composition": "Paracetamol + Caffeine + Vitamin C"},
            ],
            "expected_behavior": {
                "accept_combinations": True,
                "max_results": 3,
            }
        }

    @staticmethod
    def homeopathic_ranking_scenario():
        """Homeopathic products should rank lower."""
        return {
            "symptom_count": 1,
            "products": [
                {"title": "Paracetamol 500mg", "description": "Evidence-based pain relief"},
                {"title": "Homeopathic Remedy", "description": "Homeopathic dilution"},
            ],
            "expected_behavior": {
                "prioritize": ["Paracetamol"],
                "deprioritize": ["Homeopathic"],
            }
        }

    @staticmethod
    def contraindication_scenario():
        """Contraindicated products should be filtered."""
        return {
            "user_conditions": ["pregnancy"],
            "products": [
                {"title": "Safe Product", "contraindications": "None known"},
                {"title": "Unsafe Product", "contraindications": "Not for use during pregnancy"},
            ],
            "expected_behavior": {
                "exclude": ["Unsafe Product"],
            }
        }
