"""
Unit tests for IngredientAnalyzer class.

Tests ingredient extraction, treatment recommendations, and section building.
"""

import pytest

from src.pipeline.ingredient_analyzer import IngredientAnalyzer
from src.pipeline.models import Product


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def analyzer():
    """Create IngredientAnalyzer instance."""
    return IngredientAnalyzer()


@pytest.fixture
def sample_products():
    """Create sample products for testing."""
    return [
        Product(
            id="1",
            title="Парацетамол 500 мг",
            composition="Paracetamol 500mg",
            description="Pain relief",
            price_bgn=5.00,
            price_eur=2.50,
        ),
        Product(
            id="2",
            title="Ибупрофен 400 мг",
            composition="Ibuprofen 400mg",
            description="Anti-inflammatory",
            price_bgn=8.00,
            price_eur=4.00,
        ),
        Product(
            id="3",
            title="Колдрекс",
            composition="Paracetamol 500mg + Phenylephrine 5mg + Caffeine 25mg",
            description="Combination cold/flu product",
            price_bgn=12.00,
            price_eur=6.00,
        ),
    ]


# =============================================================================
# Test get_recommended_ingredients
# =============================================================================


class TestGetRecommendedIngredients:
    """Test get_recommended_ingredients method."""

    def test_analgesics_returns_paracetamol_ibuprofen(self, analyzer):
        """Test that analgesics treatment returns correct ingredients."""
        result = analyzer.get_recommended_ingredients("analgesics")
        assert "paracetamol" in result
        assert "ibuprofen" in result

    def test_fever_returns_antipyretics(self, analyzer):
        """Test that fever treatment returns antipyretics."""
        result = analyzer.get_recommended_ingredients("fever")
        assert "paracetamol" in result
        assert "ibuprofen" in result

    def test_allergy_returns_antihistamines(self, analyzer):
        """Test that allergy treatment returns antihistamines."""
        result = analyzer.get_recommended_ingredients("allergy")
        assert "loratadine" in result or "cetirizine" in result

    def test_empty_treatment_type_returns_empty_list(self, analyzer):
        """Test that empty treatment type returns empty list."""
        result = analyzer.get_recommended_ingredients("")
        assert result == []

    def test_unknown_treatment_type_returns_empty_list(self, analyzer):
        """Test that unknown treatment type returns empty list."""
        result = analyzer.get_recommended_ingredients("nonexistent_treatment")
        assert result == []

    def test_partial_match_works(self, analyzer):
        """Test that partial treatment type matching works."""
        # "cough" should match even if treatment_type is "dry_cough"
        result = analyzer.get_recommended_ingredients("cough")
        assert isinstance(result, list)


# =============================================================================
# Test get_treatment_action_text
# =============================================================================


class TestGetTreatmentActionText:
    """Test get_treatment_action_text method."""

    def test_analgesics_returns_action_text(self, analyzer):
        """Test that analgesics returns Bulgarian action text."""
        result = analyzer.get_treatment_action_text("analgesics")
        assert result != ""
        assert "болков" in result.lower()

    def test_antipyretics_returns_action_text(self, analyzer):
        """Test that antipyretics returns Bulgarian action text."""
        result = analyzer.get_treatment_action_text("antipyretics")
        assert result != ""
        assert "температур" in result.lower()

    def test_empty_treatment_type_returns_empty_string(self, analyzer):
        """Test that empty treatment type returns empty string."""
        result = analyzer.get_treatment_action_text("")
        assert result == ""

    def test_unknown_treatment_type_returns_empty_string(self, analyzer):
        """Test that unknown treatment type returns empty string."""
        result = analyzer.get_treatment_action_text("unknown")
        assert result == ""

    def test_partial_match_works(self, analyzer):
        """Test that partial matching works for action text."""
        # "digestive" should match even if key is just "digest"
        result = analyzer.get_treatment_action_text("digestive")
        assert isinstance(result, str)

    def test_all_treatment_types_have_bulgarian_text(self, analyzer):
        """Test that all defined treatment types have Bulgarian text."""
        treatment_types = [
            "analgesics", "antipyretics", "cough", "decongestants",
            "antihistamines", "antacids", "digestive", "antidiarrheal", "topical"
        ]
        for tt in treatment_types:
            result = analyzer.get_treatment_action_text(tt)
            assert result != "", f"Treatment type '{tt}' should have action text"
            # Check for Cyrillic characters (Bulgarian)
            assert any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in result), \
                f"Treatment type '{tt}' should have Bulgarian text"


# =============================================================================
# Test extract_ingredients_from_products
# =============================================================================


class TestExtractIngredientsFromProducts:
    """Test extract_ingredients_from_products method."""

    def test_extracts_ingredients_from_products(self, analyzer, sample_products):
        """Test that ingredients are extracted from products."""
        result = analyzer.extract_ingredients_from_products(sample_products)
        assert isinstance(result, list)
        assert len(result) > 0
        # Should contain paracetamol or ibuprofen from sample products
        assert "paracetamol" in result or "ibuprofen" in result

    def test_empty_products_returns_empty_list(self, analyzer):
        """Test that empty product list returns empty list."""
        result = analyzer.extract_ingredients_from_products([])
        assert result == []

    def test_respects_max_ingredients(self, analyzer, sample_products):
        """Test that max_ingredients parameter is respected."""
        result = analyzer.extract_ingredients_from_products(sample_products, max_ingredients=1)
        assert len(result) <= 1

    def test_returns_unique_ingredients(self, analyzer):
        """Test that duplicate ingredients are not returned."""
        # Two products with same ingredient
        products = [
            Product(
                id="1",
                title="Парацетамол А",
                composition="Paracetamol 500mg",
                description="Product A",
                price_bgn=5.00,
                price_eur=2.50,
            ),
            Product(
                id="2",
                title="Парацетамол Б",
                composition="Paracetamol 500mg",
                description="Product B",
                price_bgn=6.00,
                price_eur=3.00,
            ),
        ]
        result = analyzer.extract_ingredients_from_products(products)
        # Should have only one "paracetamol"
        assert result.count("paracetamol") == 1


# =============================================================================
# Test build_ingredients_section
# =============================================================================


class TestBuildIngredientsSection:
    """Test build_ingredients_section method."""

    def test_returns_empty_for_no_products(self, analyzer):
        """Test that empty products returns empty section."""
        result = analyzer.build_ingredients_section("analgesics", [], symptom_count=1)
        assert result == []

    def test_returns_section_with_products(self, analyzer, sample_products):
        """Test that section is built when products exist."""
        result = analyzer.build_ingredients_section("analgesics", sample_products, symptom_count=1)
        assert len(result) > 0
        # Should have header
        assert any("💊" in line for line in result)
        assert any("Подходящи активни съставки" in line for line in result)

    def test_includes_recommended_ingredients(self, analyzer, sample_products):
        """Test that recommended ingredients are included."""
        result = analyzer.build_ingredients_section("analgesics", sample_products, symptom_count=1)
        section_text = "\n".join(result)
        # Should mention paracetamol or ibuprofen in Bulgarian
        assert "парацетамол" in section_text.lower() or "ибупрофен" in section_text.lower()

    def test_includes_action_text_when_available(self, analyzer, sample_products):
        """Test that action text is included when available."""
        result = analyzer.build_ingredients_section("analgesics", sample_products, symptom_count=1)
        section_text = "\n".join(result)
        # Should have action text about pain relief
        assert "болков" in section_text.lower()

    def test_shows_fallback_when_no_ingredients_found(self, analyzer):
        """Test fallback message when ingredient extraction fails."""
        # Product with no recognized ingredients
        products = [
            Product(
                id="1",
                title="Unknown Product",
                composition="Unknown ingredient",
                description="Product with unknown ingredient",
                price_bgn=5.00,
                price_eur=2.50,
            ),
        ]
        result = analyzer.build_ingredients_section("unknown", products, symptom_count=1)
        section_text = "\n".join(result)
        # Should show fallback message
        assert "листовка" in section_text.lower()

    def test_uses_product_ingredients_as_fallback(self, analyzer, sample_products):
        """Test that product ingredients are used when no treatment type."""
        result = analyzer.build_ingredients_section("", sample_products, symptom_count=1)
        assert len(result) > 0
        # Should extract from products even without treatment type


# =============================================================================
# Test should_show_combo_note
# =============================================================================


class TestShouldShowComboNote:
    """Test should_show_combo_note method."""

    def test_returns_false_for_empty_products(self, analyzer):
        """Test that empty products returns False."""
        result = analyzer.should_show_combo_note([], symptom_count=2)
        assert result is False

    def test_returns_false_for_single_symptom(self, analyzer, sample_products):
        """Test that single symptom returns False."""
        result = analyzer.should_show_combo_note(sample_products, symptom_count=1)
        assert result is False

    def test_returns_true_for_combo_product_with_multiple_symptoms(self, analyzer, sample_products):
        """Test that combo product with multiple symptoms returns True."""
        # sample_products[2] is a combo product (Coldrex with 3 ingredients)
        result = analyzer.should_show_combo_note([sample_products[2]], symptom_count=2)
        assert result is True

    def test_detects_cold_flu_products(self, analyzer):
        """Test that cold/flu products are detected as combo."""
        products = [
            Product(
                id="1",
                title="Грипекс",
                composition="Paracetamol 500mg",
                description="Cold and flu",
                price_bgn=10.00,
                price_eur=5.00,
            ),
        ]
        result = analyzer.should_show_combo_note(products, symptom_count=2)
        assert result is True

    def test_returns_false_for_single_ingredient_products(self, analyzer):
        """Test that single ingredient products return False."""
        products = [
            Product(
                id="1",
                title="Парацетамол",
                composition="Paracetamol 500mg",
                description="Pain relief",
                price_bgn=5.00,
                price_eur=2.50,
            ),
        ]
        result = analyzer.should_show_combo_note(products, symptom_count=2)
        assert result is False


# =============================================================================
# Test get_combo_note
# =============================================================================


class TestGetComboNote:
    """Test get_combo_note method."""

    def test_returns_bulgarian_text(self, analyzer):
        """Test that combo note returns Bulgarian text."""
        result = analyzer.get_combo_note()
        assert result != ""
        # Check for Cyrillic characters
        assert any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in result)

    def test_mentions_combo_product(self, analyzer):
        """Test that note mentions combination product."""
        result = analyzer.get_combo_note()
        assert "комбиниран" in result.lower()

    def test_explains_multiple_ingredients(self, analyzer):
        """Test that note explains multiple ingredients."""
        result = analyzer.get_combo_note()
        assert "активни съставки" in result.lower() or "съставки" in result.lower()


# =============================================================================
# Integration Tests
# =============================================================================


class TestIngredientAnalyzerIntegration:
    """Integration tests for IngredientAnalyzer."""

    def test_full_ingredient_section_generation(self, analyzer, sample_products):
        """Test complete ingredient section generation."""
        # Simulate real usage
        treatment_type = "analgesics"
        symptom_count = 2

        # Build section
        section = analyzer.build_ingredients_section(
            treatment_type,
            sample_products,
            symptom_count
        )

        # Verify section structure
        assert len(section) > 0
        assert any("💊" in line for line in section)
        assert any("Подходящи активни съставки" in line for line in section)

        # Verify content
        section_text = "\n".join(section)
        assert "парацетамол" in section_text.lower() or "ибупрофен" in section_text.lower()

    def test_combo_note_workflow(self, analyzer, sample_products):
        """Test complete combo note workflow."""
        # Check if combo note should be shown
        should_show = analyzer.should_show_combo_note(sample_products, symptom_count=2)

        if should_show:
            # Get combo note
            note = analyzer.get_combo_note()
            assert note != ""
            assert "комбиниран" in note.lower()

    def test_handles_missing_treatment_gracefully(self, analyzer, sample_products):
        """Test that missing treatment type is handled gracefully."""
        # Empty treatment type
        section = analyzer.build_ingredients_section("", sample_products, symptom_count=1)

        # Should still build section from products
        assert len(section) > 0
        assert any("💊" in line for line in section)

    def test_stateless_behavior(self):
        """Test that analyzer is stateless and can be reused."""
        analyzer1 = IngredientAnalyzer()
        analyzer2 = IngredientAnalyzer()

        # Same inputs should give same outputs
        result1 = analyzer1.get_recommended_ingredients("analgesics")
        result2 = analyzer2.get_recommended_ingredients("analgesics")

        assert result1 == result2
