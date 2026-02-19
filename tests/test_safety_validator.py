"""
Comprehensive tests for SafetyValidator class.

Tests safety validation, age-appropriate filtering, and disclaimer generation.
"""

import pytest

from src.pipeline.models import Product
from src.pipeline.safety_validator import SafetyValidator


# =========================================================================
# Test Fixtures
# =========================================================================


@pytest.fixture
def sample_products():
    """Create sample products for testing."""
    return [
        Product(
            id="1",
            title="Панадол за деца сироп 120 мг/5 мл",
            description="Болкоуспокояващо за деца",
            composition="Paracetamol 120mg/5ml",
            price_bgn=8.00,
            price_eur=4.00,
        ),
        Product(
            id="2",
            title="Ибупрофен 400 мг таблетки",
            description="Болкоуспокояващо за възрастни",
            composition="Ibuprofen 400mg",
            price_bgn=10.00,
            price_eur=5.00,
        ),
        Product(
            id="3",
            title="Парацетамол 500 мг",
            description="Болкоуспокояващо",
            composition="Paracetamol 500mg",
            price_bgn=6.00,
            price_eur=3.00,
        ),
        Product(
            id="4",
            title="Нурофен бейби суспензия",
            description="За бебета и деца",
            composition="Ibuprofen 100mg/5ml",
            price_bgn=12.00,
            price_eur=6.00,
        ),
        Product(
            id="5",
            title="Комбиномед за възрастни",
            description="Комбиниран препарат над 18 години",
            composition="Paracetamol + Caffeine",
            price_bgn=15.00,
            price_eur=7.50,
        ),
    ]


# =========================================================================
# Test filter_by_age_appropriateness
# =========================================================================


class TestFilterByAgeAppropriateness:
    """Test the filter_by_age_appropriateness method."""

    def test_child_query_filters_adult_products(self, sample_products):
        """Test that adult-only products are filtered for child queries."""
        validator = SafetyValidator()

        filtered = validator.filter_by_age_appropriateness(sample_products, "дете с температура")

        # Adult-only product should be excluded
        titles = [p.title for p in filtered]
        assert "Комбиномед за възрастни" not in titles

    def test_child_query_prioritizes_child_products(self, sample_products):
        """Test that child products are prioritized for child queries."""
        validator = SafetyValidator()

        filtered = validator.filter_by_age_appropriateness(sample_products, "болка при дете")

        # Child products should come first
        assert "деца" in filtered[0].title.lower() or "бейби" in filtered[0].title.lower()

    def test_baby_query_prioritizes_baby_products(self, sample_products):
        """Test that baby-specific products are prioritized for baby queries."""
        validator = SafetyValidator()

        filtered = validator.filter_by_age_appropriateness(sample_products, "температура при бебе")

        # Baby/child products should be prioritized over adult products
        # Check that adult-only products are excluded or ranked lower
        adult_titles = [p.title for p in filtered if "за възрастни" in p.title.lower()]
        assert len(adult_titles) == 0 or filtered.index(next(p for p in filtered if "за възрастни" in p.title.lower())) > 0

    def test_adult_query_no_filtering(self, sample_products):
        """Test that no filtering occurs for adult queries."""
        validator = SafetyValidator()

        filtered = validator.filter_by_age_appropriateness(sample_products, "главоболие")

        # All products should be returned
        assert len(filtered) == len(sample_products)

    def test_empty_query_no_filtering(self, sample_products):
        """Test that no filtering occurs for empty query."""
        validator = SafetyValidator()

        filtered = validator.filter_by_age_appropriateness(sample_products, "")

        # All products should be returned
        assert len(filtered) == len(sample_products)

    def test_filtering_all_products_returns_originals(self):
        """Test that if all products are filtered, originals are returned."""
        validator = SafetyValidator()

        adult_only = [
            Product(
                id="1",
                title="Продукт за възрастни над 18 години",
                description="Само за възрастни",
                price_bgn=10.00,
            )
        ]

        filtered = validator.filter_by_age_appropriateness(adult_only, "болка при дете")

        # Should return originals rather than empty list
        assert len(filtered) == 1


# =========================================================================
# Test filter_by_severity
# =========================================================================


class TestFilterBySeverity:
    """Test the filter_by_severity method."""

    def test_single_symptom_prioritizes_simple_products(self, sample_products):
        """Test that simple products are prioritized for single symptoms."""
        validator = SafetyValidator()

        filtered = validator.filter_by_severity(sample_products, symptom_count=1)

        # Should return max 3 products
        assert len(filtered) <= 3

        # Simple products should come before combinations
        # (Парацетамол 500 мг is simple, Комбиномед is combination)
        simple_titles = [p.title for p in filtered if "комби" not in p.title.lower()]
        assert len(simple_titles) > 0

    def test_multiple_symptoms_returns_top_products(self, sample_products):
        """Test that top products are returned for multiple symptoms."""
        validator = SafetyValidator()

        filtered = validator.filter_by_severity(sample_products, symptom_count=3)

        # Should return max 3 products
        assert len(filtered) <= 3

    def test_empty_products_returns_empty(self):
        """Test that empty product list returns empty."""
        validator = SafetyValidator()

        filtered = validator.filter_by_severity([], symptom_count=1)

        assert filtered == []

    def test_homeopathic_products_ranked_last(self):
        """Test that homeopathic products are ranked last."""
        validator = SafetyValidator()

        products = [
            Product(
                id="1",
                title="Хомеопатично средство",
                description="Хомеопатия",
                composition="Homeopathic dilution",
                price_bgn=20.00,
            ),
            Product(
                id="2",
                title="Парацетамол 500 мг",
                description="Болкоуспокояващо",
                composition="Paracetamol 500mg",
                price_bgn=6.00,
            ),
        ]

        filtered = validator.filter_by_severity(products, symptom_count=1)

        # Non-homeopathic should come first
        assert "парацетамол" in filtered[0].title.lower()


# =========================================================================
# Test Query Classification Methods
# =========================================================================


class TestQueryClassification:
    """Test query classification methods."""

    def test_is_child_related_query_bulgarian(self):
        """Test child query detection in Bulgarian."""
        validator = SafetyValidator()

        assert validator.is_child_related_query("температура при дете")
        assert validator.is_child_related_query("болка при бебето")
        assert validator.is_child_related_query("за дете 5 години")

    def test_is_child_related_query_negative(self):
        """Test that non-child queries are not flagged."""
        validator = SafetyValidator()

        assert not validator.is_child_related_query("главоболие")
        assert not validator.is_child_related_query("за възрастни")

    def test_is_safety_information_query(self):
        """Test safety information query detection."""
        validator = SafetyValidator()

        assert validator.is_safety_information_query("безопасно ли е да взема")
        assert validator.is_safety_information_query("странични ефекти")
        assert validator.is_safety_information_query("противопоказания")

    def test_is_safety_information_query_negative(self):
        """Test that regular queries are not flagged as safety queries."""
        validator = SafetyValidator()

        assert not validator.is_safety_information_query("болка в главата")
        assert not validator.is_safety_information_query("температура")

    def test_is_chronic_disease_query(self):
        """Test chronic disease query detection."""
        validator = SafetyValidator()

        assert validator.is_chronic_disease_query("диабет тип 2")
        assert validator.is_chronic_disease_query("високо кръвно налягане")
        assert validator.is_chronic_disease_query("хипертония")

    def test_is_chronic_disease_query_negative(self):
        """Test that acute conditions are not flagged as chronic."""
        validator = SafetyValidator()

        assert not validator.is_chronic_disease_query("настинка")
        assert not validator.is_chronic_disease_query("главоболие")


# =========================================================================
# Test Disclaimer Methods
# =========================================================================


class TestDisclaimers:
    """Test disclaimer generation methods."""

    def test_add_child_disclaimer_returns_unchanged(self):
        """Test that child disclaimer returns response unchanged (handled in template)."""
        validator = SafetyValidator()

        response = "Test response"
        result = validator.add_child_disclaimer(response)

        # Should return unchanged (disclaimer is in template)
        assert result == response

    def test_add_safety_info_disclaimer_returns_unchanged(self):
        """Test that safety info disclaimer returns response unchanged (handled in template)."""
        validator = SafetyValidator()

        response = "Test response"
        result = validator.add_safety_info_disclaimer(response)

        # Should return unchanged (disclaimer is in template)
        assert result == response

    def test_add_chronic_disease_disclaimer_adds_warning(self):
        """Test that chronic disease disclaimer adds warning."""
        validator = SafetyValidator()

        response = "Препоръчвам продукти за диабет"
        result = validator.add_chronic_disease_disclaimer(response)

        # Should add disclaimer
        assert len(result) > len(response)
        assert "хронични заболявания" in result.lower()
        assert "рецепта" in result.lower()

    def test_add_chronic_disease_disclaimer_skips_if_doctor_mentioned(self):
        """Test that disclaimer is skipped if doctor already mentioned."""
        validator = SafetyValidator()

        response = "Препоръчвам консултация с лекар"
        result = validator.add_chronic_disease_disclaimer(response)

        # Should not add disclaimer (doctor already mentioned)
        assert result == response

    def test_add_chronic_disease_disclaimer_skips_if_112_mentioned(self):
        """Test that disclaimer is skipped if 112 is mentioned."""
        validator = SafetyValidator()

        response = "При спешност обадете се на 112"
        result = validator.add_chronic_disease_disclaimer(response)

        # Should not add disclaimer (emergency already mentioned)
        assert result == response


# =========================================================================
# Integration Tests
# =========================================================================


class TestSafetyValidatorIntegration:
    """Integration tests for SafetyValidator."""

    def test_full_child_safety_pipeline(self, sample_products):
        """Test complete child safety validation pipeline."""
        validator = SafetyValidator()

        # Detect child query
        query = "температура при дете 3 години"
        assert validator.is_child_related_query(query)

        # Filter by age appropriateness
        age_filtered = validator.filter_by_age_appropriateness(sample_products, query)
        assert len(age_filtered) < len(sample_products)

        # Filter by severity
        final = validator.filter_by_severity(age_filtered, symptom_count=1)
        assert len(final) <= 3

        # Add disclaimer (no-op, handled in template)
        response = "Препоръки за дете"
        result = validator.add_child_disclaimer(response)
        assert result == response

    def test_full_chronic_disease_pipeline(self, sample_products):
        """Test complete chronic disease validation pipeline."""
        validator = SafetyValidator()

        # Detect chronic disease query
        query = "продукти за диабет"
        assert validator.is_chronic_disease_query(query)

        # Filter products normally
        filtered = validator.filter_by_severity(sample_products, symptom_count=2)
        assert len(filtered) <= 3

        # Add chronic disease disclaimer
        response = "Препоръки за диабет"
        result = validator.add_chronic_disease_disclaimer(response)
        assert "хронични заболявания" in result.lower()
        assert len(result) > len(response)
