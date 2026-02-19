"""
Contract-based tests for SafetyValidator class.

Demonstrates migration from implementation-coupled to contract-based testing.
Tests focus on behavior rather than implementation details.
"""

import pytest

from src.pipeline.safety_validator import SafetyValidator
from tests.contracts import (
    ProductBuilder,
    simple_product,
    child_product,
    adult_product,
)
from tests.contracts.safety_check_contract import (
    assert_age_filtering_valid,
    assert_severity_filtering_valid,
    assert_no_unsafe_products,
    SafetyCheckTestScenarios,
)


# =========================================================================
# Test Fixtures Using Builders
# =========================================================================


@pytest.fixture
def sample_products():
    """Create sample products using builders."""
    return [
        # Child product
        (ProductBuilder()
         .with_id("1")
         .with_title("Панадол за деца сироп 120 мг/5 мл")
         .with_description("Болкоуспокояващо за деца")
         .with_composition("Paracetamol 120mg/5ml")
         .with_price(8.00, 4.00)
         .for_children()
         .build()),

        # Adult product
        (ProductBuilder()
         .with_id("2")
         .with_title("Ибупрофен 400 мг таблетки")
         .with_description("Болкоуспокояващо за възрастни")
         .with_composition("Ibuprofen 400mg")
         .with_price(10.00, 5.00)
         .build()),

        # General use product
        (ProductBuilder()
         .with_id("3")
         .with_title("Парацетамол 500 мг")
         .with_description("Болкоуспокояващо")
         .with_composition("Paracetamol 500mg")
         .with_price(6.00, 3.00)
         .build()),

        # Baby product
        (ProductBuilder()
         .with_id("4")
         .with_title("Нурофен бейби суспензия")
         .with_description("За бебета и деца")
         .with_composition("Ibuprofen 100mg/5ml")
         .with_price(12.00, 6.00)
         .for_children()
         .build()),

        # Adult-only product
        (ProductBuilder()
         .with_id("5")
         .with_title("Комбиномед за възрастни")
         .with_description("Комбиниран препарат над 18 години")
         .with_composition("Paracetamol + Caffeine")
         .with_price(15.00, 7.50)
         .build()),
    ]


# =========================================================================
# Contract-Based Tests for filter_by_age_appropriateness
# =========================================================================


class TestFilterByAgeAppropriatenessContract:
    """Contract-based tests for filter_by_age_appropriateness method."""

    def test_child_query_returns_valid_subset(self, sample_products):
        """Test that child query filtering returns valid subset (contract)."""
        validator = SafetyValidator()

        filtered = validator.filter_by_age_appropriateness(sample_products, "дете с температура")

        # Verify contract compliance
        assert_age_filtering_valid(sample_products, filtered, "дете с температура",
                                   context="child query")

    def test_child_query_excludes_adult_only_products(self, sample_products):
        """Test that adult-only products are filtered for child queries (contract)."""
        validator = SafetyValidator()

        filtered = validator.filter_by_age_appropriateness(sample_products, "болка при дете")

        # Contract: filtered should be subset
        assert_age_filtering_valid(sample_products, filtered, "болка при дете")

        # Contract: adult-only products should be excluded
        titles = [p.title for p in filtered]
        assert "Комбиномед за възрастни" not in titles, \
            "Adult-only products should be filtered for child queries"

    def test_baby_query_returns_safe_products(self, sample_products):
        """Test baby query filtering returns safe products (contract)."""
        validator = SafetyValidator()

        filtered = validator.filter_by_age_appropriateness(sample_products, "температура при бебе")

        # Verify contract compliance
        assert_age_filtering_valid(sample_products, filtered, "температура при бебе",
                                   context="baby query")
        assert_no_unsafe_products(filtered, age_group="infant", context="baby query")

    def test_adult_query_no_filtering_applied(self, sample_products):
        """Test that adult queries don't filter products (contract)."""
        validator = SafetyValidator()

        filtered = validator.filter_by_age_appropriateness(sample_products, "главоболие")

        # Contract: all products should be returned for adult queries
        assert len(filtered) == len(sample_products), \
            "Adult queries should not filter products"
        assert_age_filtering_valid(sample_products, filtered, "главоболие")

    def test_empty_query_returns_all_products(self, sample_products):
        """Test empty query behavior (contract)."""
        validator = SafetyValidator()

        filtered = validator.filter_by_age_appropriateness(sample_products, "")

        # Contract: empty query should return all products
        assert len(filtered) == len(sample_products), \
            "Empty query should not filter products"

    def test_filtering_all_returns_originals(self):
        """Test fallback behavior when all products filtered (contract)."""
        validator = SafetyValidator()

        # Create adult-only products
        adult_only = [adult_product("1", "Продукт за възрастни над 18 години")]

        filtered = validator.filter_by_age_appropriateness(adult_only, "болка при дете")

        # Contract: should return originals rather than empty list
        assert len(filtered) > 0, "Should return originals if all would be filtered"

    def test_scenario_child_query(self):
        """Test using contract scenario for child queries."""
        validator = SafetyValidator()

        # Use scenario from contract
        scenario = SafetyCheckTestScenarios.child_query_scenario()

        # Build products from scenario
        products = [
            child_product("1", "Child Paracetamol Syrup"),
            adult_product("2", "Adult Ibuprofen 400mg"),
            simple_product("3", "Paracetamol 500mg"),
        ]

        filtered = validator.filter_by_age_appropriateness(products, scenario["query"])

        # Verify contract
        assert_age_filtering_valid(products, filtered, scenario["query"])

        # Verify scenario expectations
        titles = [p.title for p in filtered]
        # Adult products should be excluded (or at least not prioritized)
        adult_count = sum(1 for t in titles if "Adult" in t)
        child_count = sum(1 for t in titles if "Child" in t)
        assert child_count > 0, "Child products should be included"


# =========================================================================
# Contract-Based Tests for filter_by_severity
# =========================================================================


class TestFilterBySeverityContract:
    """Contract-based tests for filter_by_severity method."""

    def test_single_symptom_respects_max_count(self, sample_products):
        """Test that single symptom filtering respects max count (contract)."""
        validator = SafetyValidator()

        filtered = validator.filter_by_severity(sample_products, symptom_count=1)

        # Verify contract compliance
        assert_severity_filtering_valid(sample_products, filtered, symptom_count=1,
                                       context="single symptom")

    def test_multiple_symptoms_respects_max_count(self, sample_products):
        """Test that multiple symptom filtering respects max count (contract)."""
        validator = SafetyValidator()

        filtered = validator.filter_by_severity(sample_products, symptom_count=3)

        # Verify contract compliance
        assert_severity_filtering_valid(sample_products, filtered, symptom_count=3,
                                       context="multiple symptoms")

    def test_empty_products_returns_empty(self):
        """Test empty input behavior (contract)."""
        validator = SafetyValidator()

        filtered = validator.filter_by_severity([], symptom_count=1)

        # Contract: empty input should return empty output
        assert filtered == [], "Empty input should return empty output"

    def test_homeopathic_products_deprioritized(self):
        """Test that homeopathic products are ranked lower (contract)."""
        validator = SafetyValidator()

        # Create test products
        products = [
            (ProductBuilder()
             .with_id("1")
             .with_title("Хомеопатично средство")
             .with_description("Хомеопатия")
             .with_composition("Homeopathic dilution")
             .with_price(20.00, 10.00)
             .build()),

            (ProductBuilder()
             .with_id("2")
             .with_title("Парацетамол 500 мг")
             .with_description("Болкоуспокояващо")
             .with_composition("Paracetamol 500mg")
             .with_price(6.00, 3.00)
             .build()),
        ]

        filtered = validator.filter_by_severity(products, symptom_count=1)

        # Verify contract
        assert_severity_filtering_valid(products, filtered, symptom_count=1)

        # Contract: non-homeopathic should be prioritized
        if len(filtered) > 0:
            assert "парацетамол" in filtered[0].title.lower(), \
                "Non-homeopathic products should be prioritized"

    def test_scenario_simple_symptom(self):
        """Test using contract scenario for simple symptoms."""
        validator = SafetyValidator()

        scenario = SafetyCheckTestScenarios.simple_symptom_scenario()

        # Build products
        products = [
            simple_product("1", "Paracetamol 500mg", price=6.00),
            (ProductBuilder()
             .with_id("2")
             .with_title("Multi-symptom Cold Relief")
             .with_composition("Paracetamol + Caffeine + Phenylephrine")
             .with_price(12.00, 6.00)
             .build()),
        ]

        filtered = validator.filter_by_severity(products, symptom_count=scenario["symptom_count"])

        # Verify contract
        assert_severity_filtering_valid(products, filtered,
                                       symptom_count=scenario["symptom_count"])

        # Verify scenario expectations
        assert len(filtered) <= scenario["expected_behavior"]["max_results"]


# =========================================================================
# Contract-Based Tests for Query Classification Methods
# =========================================================================


class TestQueryClassificationContract:
    """Contract-based tests for query classification methods."""

    def test_is_child_related_query_detects_child_keywords(self):
        """Test child query detection (contract behavior)."""
        validator = SafetyValidator()

        # Contract: should detect common child-related keywords
        child_queries = [
            "температура при дете",
            "болка при бебето",
            "за дете 5 години",
        ]

        for query in child_queries:
            assert validator.is_child_related_query(query), \
                f"Should detect '{query}' as child-related"

    def test_is_child_related_query_negative_cases(self):
        """Test that non-child queries are not flagged (contract behavior)."""
        validator = SafetyValidator()

        # Contract: should not flag regular queries
        adult_queries = [
            "главоболие",
            "за възрастни",
            "болка в гърба",
        ]

        for query in adult_queries:
            assert not validator.is_child_related_query(query), \
                f"Should not detect '{query}' as child-related"

    def test_is_safety_information_query_detects_safety_keywords(self):
        """Test safety information query detection (contract behavior)."""
        validator = SafetyValidator()

        # Contract: should detect safety-related keywords
        safety_queries = [
            "безопасно ли е да взема",
            "странични ефекти",
            "противопоказания",
        ]

        for query in safety_queries:
            assert validator.is_safety_information_query(query), \
                f"Should detect '{query}' as safety query"

    def test_is_safety_information_query_negative_cases(self):
        """Test that regular queries are not flagged (contract behavior)."""
        validator = SafetyValidator()

        # Contract: should not flag regular queries
        regular_queries = [
            "болка в главата",
            "температура",
        ]

        for query in regular_queries:
            assert not validator.is_safety_information_query(query), \
                f"Should not detect '{query}' as safety query"

    def test_is_chronic_disease_query_detects_chronic_conditions(self):
        """Test chronic disease query detection (contract behavior)."""
        validator = SafetyValidator()

        # Contract: should detect chronic disease keywords
        chronic_queries = [
            "диабет тип 2",
            "високо кръвно налягане",
            "хипертония",
        ]

        for query in chronic_queries:
            assert validator.is_chronic_disease_query(query), \
                f"Should detect '{query}' as chronic disease query"

    def test_is_chronic_disease_query_negative_cases(self):
        """Test that acute conditions are not flagged (contract behavior)."""
        validator = SafetyValidator()

        # Contract: should not flag acute conditions
        acute_queries = [
            "настинка",
            "главоболие",
        ]

        for query in acute_queries:
            assert not validator.is_chronic_disease_query(query), \
                f"Should not detect '{query}' as chronic disease query"


# =========================================================================
# Contract-Based Tests for Disclaimer Methods
# =========================================================================


class TestDisclaimersContract:
    """Contract-based tests for disclaimer generation methods."""

    def test_add_child_disclaimer_preserves_response(self):
        """Test that child disclaimer preserves response (contract)."""
        validator = SafetyValidator()

        response = "Test response"
        result = validator.add_child_disclaimer(response)

        # Contract: disclaimer handled in template, response unchanged
        assert result == response, "Child disclaimer should not modify response"

    def test_add_safety_info_disclaimer_preserves_response(self):
        """Test that safety info disclaimer preserves response (contract)."""
        validator = SafetyValidator()

        response = "Test response"
        result = validator.add_safety_info_disclaimer(response)

        # Contract: disclaimer handled in template, response unchanged
        assert result == response, "Safety info disclaimer should not modify response"

    def test_add_chronic_disease_disclaimer_adds_warning(self):
        """Test that chronic disease disclaimer adds warning (contract)."""
        validator = SafetyValidator()

        response = "Препоръчвам продукти за диабет"
        result = validator.add_chronic_disease_disclaimer(response)

        # Contract: should add disclaimer for chronic diseases
        assert len(result) > len(response), "Should add disclaimer"
        assert "хронични заболявания" in result.lower() or "рецепта" in result.lower(), \
            "Disclaimer should mention chronic diseases or prescriptions"

    def test_add_chronic_disease_disclaimer_skips_if_doctor_mentioned(self):
        """Test that disclaimer skips if doctor already mentioned (contract)."""
        validator = SafetyValidator()

        response = "Препоръчвам консултация с лекар"
        result = validator.add_chronic_disease_disclaimer(response)

        # Contract: should not add duplicate disclaimer
        assert result == response, \
            "Should not add disclaimer if doctor already mentioned"

    def test_add_chronic_disease_disclaimer_skips_if_emergency_mentioned(self):
        """Test that disclaimer skips if emergency mentioned (contract)."""
        validator = SafetyValidator()

        response = "При спешност обадете се на 112"
        result = validator.add_chronic_disease_disclaimer(response)

        # Contract: should not add disclaimer if emergency already mentioned
        assert result == response, \
            "Should not add disclaimer if emergency already mentioned"


# =========================================================================
# Integration Tests Using Contracts
# =========================================================================


class TestSafetyValidatorIntegrationContract:
    """Contract-based integration tests for SafetyValidator."""

    def test_full_child_safety_pipeline_maintains_contracts(self, sample_products):
        """Test complete child safety pipeline using contracts."""
        validator = SafetyValidator()

        # Stage 1: Detect child query
        query = "температура при дете 3 години"
        assert validator.is_child_related_query(query), \
            "Should detect child query"

        # Stage 2: Filter by age appropriateness
        age_filtered = validator.filter_by_age_appropriateness(sample_products, query)

        # Verify age filtering contract
        assert_age_filtering_valid(sample_products, age_filtered, query,
                                   context="child pipeline - age filter")
        assert_no_unsafe_products(age_filtered, age_group="child",
                                  context="child pipeline - safety check")

        # Stage 3: Filter by severity
        final = validator.filter_by_severity(age_filtered, symptom_count=1)

        # Verify severity filtering contract
        assert_severity_filtering_valid(age_filtered, final, symptom_count=1,
                                       context="child pipeline - severity filter")

        # Stage 4: Add disclaimer
        response = "Препоръки за дете"
        result = validator.add_child_disclaimer(response)

        # Contract: disclaimer handled in template
        assert result == response

    def test_full_chronic_disease_pipeline_maintains_contracts(self, sample_products):
        """Test complete chronic disease pipeline using contracts."""
        validator = SafetyValidator()

        # Stage 1: Detect chronic disease query
        query = "продукти за диабет"
        assert validator.is_chronic_disease_query(query), \
            "Should detect chronic disease query"

        # Stage 2: Filter products by severity
        filtered = validator.filter_by_severity(sample_products, symptom_count=2)

        # Verify severity filtering contract
        assert_severity_filtering_valid(sample_products, filtered, symptom_count=2,
                                       context="chronic disease pipeline")

        # Stage 3: Add chronic disease disclaimer
        response = "Препоръки за диабет"
        result = validator.add_chronic_disease_disclaimer(response)

        # Contract: disclaimer should be added
        assert len(result) > len(response), \
            "Should add disclaimer for chronic disease"
        assert "хронични заболявания" in result.lower(), \
            "Disclaimer should mention chronic diseases"

    def test_edge_case_empty_products_through_pipeline(self):
        """Test pipeline with empty products (contract edge case)."""
        validator = SafetyValidator()

        empty_products = []

        # Stage 1: Age filtering
        age_filtered = validator.filter_by_age_appropriateness(empty_products, "дете")
        assert age_filtered == [], "Empty input should return empty output"

        # Stage 2: Severity filtering
        severity_filtered = validator.filter_by_severity(age_filtered, symptom_count=1)
        assert severity_filtered == [], "Empty input should return empty output"

    def test_edge_case_all_products_filtered(self):
        """Test fallback when all products would be filtered (contract edge case)."""
        validator = SafetyValidator()

        # Create only adult products
        adult_products = [
            adult_product("1", "Adult Product 1"),
            adult_product("2", "Adult Product 2"),
        ]

        # Try to filter for child query
        filtered = validator.filter_by_age_appropriateness(adult_products, "дете с болка")

        # Contract: should return originals rather than empty
        assert len(filtered) > 0, \
            "Should return originals when all would be filtered (fallback behavior)"
