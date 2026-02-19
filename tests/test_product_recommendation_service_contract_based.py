"""
Contract-based tests for ProductRecommendationService.

Tests focus on behavior rather than implementation details.
"""

import pytest

from src.medical_model import MedicalReasoning
from src.services.product_recommendation_service import ProductRecommendationService
from tests.contracts import MedicalReasoningBuilder, ProductBuilder, simple_product


# =========================================================================
# Mock Classes
# =========================================================================


class MockProductMatcher:
    """Mock product matcher for testing."""

    def __init__(self, return_products=None):
        self.return_products = return_products or []

    def retrieve_candidates(self, medical_reasoning, query, top_k=10):
        """Simulate candidate retrieval."""
        return self.return_products

    def pharmacological_rerank(self, products, treatment_type):
        """Simulate pharmacological reranking."""
        return products  # Return as-is for simplicity

    def refine_selection(self, products, reasoning, max_products=5):
        """Simulate LLM-based refinement."""
        return products[:max_products]

    def deduplicate_by_ingredient(self, products, max_products=3):
        """Simulate deduplication."""
        return products[:max_products]

    def filter_by_name_match(self, products, search_term):
        """Simulate name filtering."""
        search_lower = search_term.lower()
        return [p for p in products if search_lower in p.title.lower()]


class MockSafetyValidator:
    """Mock safety validator for testing."""

    def filter_by_age_appropriateness(self, products, query):
        """Simulate age filtering."""
        return products  # Return as-is for simplicity


class MockSafetyLayer:
    """Mock safety layer for testing."""

    def filter_otc_only(self, products):
        """Simulate OTC filtering."""
        return products  # Return as-is for simplicity


class MockMedicalReasoningService:
    """Mock medical reasoning service for testing."""

    def is_drug_combination_query(self, text):
        """Simulate drug combination detection."""
        return "заедно с" in text.lower() or "together with" in text.lower()


# =========================================================================
# Test Fixtures
# =========================================================================


@pytest.fixture
def service():
    """Create ProductRecommendationService instance."""
    return ProductRecommendationService()


@pytest.fixture
def service_with_mocks():
    """Create ProductRecommendationService with mocks."""
    sample_products = [
        simple_product("1", "Парацетамол 500 мг", price=5.00),
        simple_product("2", "Ибупрофен 400 мг", price=8.00),
        simple_product("3", "Аспирин 100 мг", price=4.00),
    ]

    return ProductRecommendationService(
        product_matcher=MockProductMatcher(return_products=sample_products),
        safety_validator=MockSafetyValidator(),
        safety_layer=MockSafetyLayer(),
        medical_reasoning_service=MockMedicalReasoningService(),
    )


# =========================================================================
# Contract-Based Tests for build_search_query
# =========================================================================


class TestBuildSearchQueryContract:
    """Contract-based tests for build_search_query method."""

    def test_returns_non_empty_search_query(self, service):
        """Test that search query is non-empty (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["headache"])
            .with_treatment_type("analgesics")
            .build()
        )

        query = service.build_search_query(reasoning)

        # Contract: must return non-empty query string
        assert isinstance(query, str), "Must return string"
        assert len(query) > 0, "Must return non-empty query"

    def test_includes_treatment_type_in_query(self, service):
        """Test that treatment type is included in query (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["fever"])
            .with_treatment_type("antipyretics")
            .build()
        )

        query = service.build_search_query(reasoning)

        # Contract: should include treatment type
        assert "antipyretics" in query, "Query should include treatment type"

    def test_includes_symptoms_in_query(self, service):
        """Test that symptoms are included in query (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["headache", "fever"])
            .with_treatment_type("analgesics")
            .build()
        )

        query = service.build_search_query(reasoning)

        # Contract: should include symptoms
        assert "headache" in query or "fever" in query, "Query should include symptoms"

    def test_filters_out_non_useful_symptoms(self, service):
        """Test that non-useful symptoms are filtered (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["drug interaction query", "safety concern"])
            .with_treatment_type("analgesics")
            .build()
        )

        query = service.build_search_query(reasoning)

        # Contract: should filter out non-useful symptoms
        assert "drug interaction query" not in query, "Should filter non-useful symptoms"
        assert "safety concern" not in query, "Should filter non-useful symptoms"

    def test_adds_age_context_for_child_queries(self, service):
        """Test that age context is added for child queries (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["fever"])
            .with_treatment_type("antipyretics")
            .build()
        )

        query = service.build_search_query(reasoning, original_query="температура при дете")

        # Contract: should add age context for child queries
        assert "деца" in query, "Should add age context for child queries"

    def test_returns_fallback_for_empty_reasoning(self, service):
        """Test fallback behavior for empty reasoning (contract)."""
        reasoning = MedicalReasoning(
            symptoms=[],
            likely_cause="",
            treatment_type="",
            warnings=[],
            see_doctor=False,
        )

        query = service.build_search_query(reasoning)

        # Contract: should return fallback query
        assert query == "medicine", "Should return fallback for empty reasoning"


# =========================================================================
# Contract-Based Tests for extract_drug_names
# =========================================================================


class TestExtractDrugNamesContract:
    """Contract-based tests for extract_drug_names method."""

    def test_extracts_drug_names_from_text(self, service):
        """Test drug name extraction (contract)."""
        text = "може ли да взема ибупрофен с парацетамол"

        drug_names = service.extract_drug_names(text)

        # Contract: should extract known drug names
        assert isinstance(drug_names, list), "Must return list"
        assert "ибупрофен" in drug_names, "Should extract ибупрофен"
        assert "парацетамол" in drug_names, "Should extract парацетамол"

    def test_returns_empty_list_for_no_drugs(self, service):
        """Test extraction with no drug names (contract)."""
        text = "главоболие"

        drug_names = service.extract_drug_names(text)

        # Contract: should return empty list when no drugs found
        assert drug_names == [], "Should return empty list for no drugs"

    def test_handles_english_drug_names(self, service):
        """Test extraction of English drug names (contract)."""
        text = "can I take ibuprofen with paracetamol"

        drug_names = service.extract_drug_names(text)

        # Contract: should extract English drug names
        assert "ibuprofen" in drug_names, "Should extract ibuprofen"
        assert "paracetamol" in drug_names, "Should extract paracetamol"


# =========================================================================
# Contract-Based Tests for convert_to_products
# =========================================================================


class TestConvertToProductsContract:
    """Contract-based tests for convert_to_products method."""

    def test_returns_list_of_products(self, service):
        """Test that conversion returns list of products (contract)."""
        # Create mock ChromaDB results
        mock_results = [
            {
                "id": "1",
                "title": "Парацетамол 500 мг",
                "price_bgn": 5.00,
                "price_eur": 2.50,
            }
        ]

        products = service.convert_to_products(mock_results)

        # Contract: must return list
        assert isinstance(products, list), "Must return list"

    def test_handles_empty_results(self, service):
        """Test handling of empty results (contract)."""
        products = service.convert_to_products([])

        # Contract: should return empty list for empty input
        assert products == [], "Should return empty list for empty results"

    def test_handles_invalid_results_gracefully(self, service):
        """Test graceful handling of invalid results (contract)."""
        # Invalid result that will fail parsing
        mock_results = [{"invalid": "data"}]

        products = service.convert_to_products(mock_results)

        # Contract: should handle errors gracefully (may return empty or partial list)
        assert isinstance(products, list), "Must return list even with errors"


# =========================================================================
# Contract-Based Tests for get_recommended_products
# =========================================================================


class TestGetRecommendedProductsContract:
    """Contract-based tests for get_recommended_products method."""

    def test_returns_products_and_contraindications(self, service_with_mocks):
        """Test that pipeline returns products and contraindications (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["headache"])
            .with_treatment_type("analgesics")
            .build()
        )

        selected_products, contraindicated = service_with_mocks.get_recommended_products(
            reasoning, "главоболие", max_products=3
        )

        # Contract: must return tuple of (products, contraindicated)
        assert isinstance(selected_products, list), "Must return list of products"
        assert isinstance(contraindicated, list), "Must return list of contraindicated products"

    def test_respects_max_products_limit(self, service_with_mocks):
        """Test that max_products limit is respected (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["pain"])
            .with_treatment_type("analgesics")
            .build()
        )

        selected_products, _ = service_with_mocks.get_recommended_products(
            reasoning, "болка", max_products=2
        )

        # Contract: should not exceed max_products
        assert len(selected_products) <= 2, "Should respect max_products limit"

    def test_handles_no_product_matcher(self, service):
        """Test handling when no product matcher available (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["headache"])
            .with_treatment_type("analgesics")
            .build()
        )

        selected_products, contraindicated = service.get_recommended_products(
            reasoning, "главоболие"
        )

        # Contract: should return empty lists when no matcher
        assert selected_products == [], "Should return empty products without matcher"
        assert contraindicated == [], "Should return empty contraindications without matcher"


# =========================================================================
# Contract-Based Tests for filter_by_name_match
# =========================================================================


class TestFilterByNameMatchContract:
    """Contract-based tests for filter_by_name_match method."""

    def test_filters_products_by_name(self, service_with_mocks):
        """Test product filtering by name (contract)."""
        products = [
            simple_product("1", "Парацетамол 500 мг"),
            simple_product("2", "Ибупрофен 400 мг"),
            simple_product("3", "Парацетамол 250 мг"),
        ]

        filtered = service_with_mocks.filter_by_name_match(products, "парацетамол")

        # Contract: should filter to matching products
        assert isinstance(filtered, list), "Must return list"
        assert len(filtered) <= len(products), "Filtered list should not exceed original"
        assert all("парацетамол" in p.title.lower() for p in filtered), \
            "All filtered products should match search term"

    def test_returns_empty_for_no_matches(self, service_with_mocks):
        """Test filtering with no matches (contract)."""
        products = [
            simple_product("1", "Парацетамол 500 мг"),
            simple_product("2", "Ибупрофен 400 мг"),
        ]

        filtered = service_with_mocks.filter_by_name_match(products, "аспирин")

        # Contract: should return empty list for no matches
        assert filtered == [], "Should return empty list when no matches"

    def test_handles_no_product_matcher(self, service):
        """Test handling when no product matcher available (contract)."""
        products = [simple_product("1", "Парацетамол 500 мг")]

        filtered = service.filter_by_name_match(products, "парацетамол")

        # Contract: should return original products when no matcher
        assert filtered == products, "Should return original products without matcher"
