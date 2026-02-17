"""
Unit tests for refactored pipeline modules (product_ingredients, query_router).

These tests run without loading MLX or other heavy dependencies.
Run with: python -m pytest tests/test_refactored_modules.py -v
Or: python tests/test_refactored_modules.py (standalone)
"""

import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_product_ingredients_imports():
    """Product ingredients module imports and exposes expected symbols."""
    from src.pipeline import product_ingredients as pi

    assert hasattr(pi, "INGREDIENT_PATTERNS_GLOBAL")
    assert hasattr(pi, "INGREDIENT_BG_NAMES")
    assert hasattr(pi, "TREATMENT_TO_INGREDIENTS")
    assert hasattr(pi, "extract_product_ingredient")
    assert hasattr(pi, "extract_all_product_ingredients")
    assert hasattr(pi, "is_combination_product")
    assert hasattr(pi, "extract_composition_summary")
    assert hasattr(pi, "extract_contraindication_summary")
    assert hasattr(pi, "build_ingredient_duplication_warning")
    assert hasattr(pi, "get_recommended_ingredients")


def test_get_recommended_ingredients():
    """Test treatment type to ingredients mapping."""
    from src.pipeline.product_ingredients import get_recommended_ingredients

    assert "paracetamol" in get_recommended_ingredients("analgesics")
    assert "ibuprofen" in get_recommended_ingredients("analgesics")
    assert "dextromethorphan" in get_recommended_ingredients("cough")
    assert get_recommended_ingredients("") == []
    assert get_recommended_ingredients("unknown_xyz") == []


def test_extract_product_ingredient():
    """Test ingredient extraction from product-like object."""
    from src.pipeline.product_ingredients import extract_product_ingredient

    class MockProduct:
        def __init__(self, composition, title=""):
            self.composition = composition
            self.title = title

    assert extract_product_ingredient(MockProduct("парацетамол 500mg")) == "paracetamol"
    assert extract_product_ingredient(MockProduct("", "Нурофен таблетки")) == "ibuprofen"
    assert extract_product_ingredient(MockProduct("витамин C")) == ""


def test_is_combination_product():
    """Test combination product detection."""
    from src.pipeline.product_ingredients import is_combination_product

    class MockProduct:
        def __init__(self, composition, title=""):
            self.composition = composition
            self.title = title

    single = MockProduct("парацетамол 500mg")
    combo = MockProduct("парацетамол и ибупрофен")
    assert not is_combination_product(single)
    assert is_combination_product(combo)


def test_query_router_imports():
    """Query router module exposes expected functions."""
    from src.pipeline import query_router as qr

    assert hasattr(qr, "is_catalog_query")
    assert hasattr(qr, "extract_catalog_search_term")
    assert hasattr(qr, "is_comparison_query")
    assert hasattr(qr, "extract_comparison_drugs")
    assert hasattr(qr, "is_single_drug_name_query")
    assert hasattr(qr, "is_help_clarification_query")
    assert hasattr(qr, "get_help_clarification_message")


def test_catalog_query_detection():
    """Test catalog query routing."""
    from src.pipeline.query_router import is_catalog_query

    ok, term = is_catalog_query("покажи ми слънцезащитен крем")
    assert ok
    assert "слънцезащитен" in term or len(term) > 2

    ok, term = is_catalog_query("имате ли витамини?")
    assert ok

    ok, term = is_catalog_query("главоболие и температура")
    assert not ok  # Medical query, not catalog


def test_comparison_query_detection():
    """Test comparison query routing."""
    from src.pipeline.query_router import is_comparison_query

    ok, drugs = is_comparison_query("ибупрофен или парацетамол - кое е по-добро?")
    assert ok
    assert len(drugs) >= 2

    ok, drugs = is_comparison_query("сравни нурофен и панадол")
    assert ok
    assert len(drugs) >= 2

    ok, drugs = is_comparison_query("главоболие - какво да взема")
    assert not ok


def test_single_drug_name_query():
    """Test single drug name detection."""
    from src.pipeline.query_router import is_single_drug_name_query

    assert is_single_drug_name_query("аспирин")
    assert is_single_drug_name_query("парацетамол 500")
    assert not is_single_drug_name_query("болки в главата")


def test_help_clarification_query():
    """Test help/greeting detection."""
    from src.pipeline.query_router import get_help_clarification_message, is_help_clarification_query

    assert is_help_clarification_query("помощ")
    assert is_help_clarification_query("здравей")
    assert is_help_clarification_query("help")
    assert not is_help_clarification_query("помощ за главоболие")

    msg = get_help_clarification_message()
    assert "аптечен асистент" in msg or "асистент" in msg


if __name__ == "__main__":
    # Run as standalone script
    import unittest
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
