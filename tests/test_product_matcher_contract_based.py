"""
Contract-based tests for ProductMatcher class.

Demonstrates migration from implementation-coupled to contract-based testing.
Tests focus on behavior rather than implementation details.
"""

import pytest

from src.pipeline.product_matcher import ProductMatcher
from tests.contracts import (
    MedicalReasoningBuilder,
    ProductBuilder,
    simple_medical_reasoning,
)
from tests.contracts.product_matching_contract import (
    assert_product_list_valid,
    ProductMatchingTestScenarios,
)


# =========================================================================
# Mock Classes (same as before - mocks are OK)
# =========================================================================


class MockProductStore:
    """Mock product store for testing."""

    def __init__(self, products=None):
        self.products = products or []
        self.collection = self

    def count(self):
        return len(self.products)

    def search_by_category(self, query, treatment_type, n_results):
        """Simulate category-aware search."""
        return self.products[:n_results]

    def hybrid_search(self, query, n_results):
        """Simulate hybrid search."""
        return self.products[:n_results]


class MockMedicalModel:
    """Mock medical model for testing."""

    def __init__(self, return_products=None):
        self.return_products = return_products or []

    def refine_product_selection(self, user_query, medical_reasoning, candidate_products, max_products):
        """Simulate LLM-based refinement."""
        return self.return_products if self.return_products else candidate_products[:max_products]


# =========================================================================
# Test Fixtures Using Builders
# =========================================================================


@pytest.fixture
def sample_products():
    """Create sample products using builders."""
    return [
        (ProductBuilder()
         .with_id("1")
         .with_title("Парацетамол 500 мг")
         .with_brand("BrandA")
         .with_composition("Paracetamol 500mg")
         .with_description("Pain relief")
         .with_price(5.00, 2.50)
         .build()),

        (ProductBuilder()
         .with_id("2")
         .with_title("Ибупрофен 400 мг")
         .with_brand("BrandB")
         .with_composition("Ibuprofen 400mg")
         .with_description("Anti-inflammatory")
         .with_price(8.00, 4.00)
         .build()),

        (ProductBuilder()
         .with_id("3")
         .with_title("Парацетамол 250 мг")
         .with_brand("BrandC")
         .with_composition("Paracetamol 250mg")
         .with_description("For children")
         .with_price(4.00, 2.00)
         .for_children()
         .build()),

        (ProductBuilder()
         .with_id("4")
         .with_title("Витамин C")
         .with_brand("BrandD")
         .with_composition("Ascorbic acid 1000mg")
         .with_description("Vitamin supplement")
         .with_price(12.00, 6.00)
         .build()),
    ]


# =========================================================================
# Contract-Based Tests for retrieve_candidates
# =========================================================================


class TestRetrieveCandidatesContract:
    """Contract-based tests for retrieve_candidates method."""

    def test_returns_valid_product_list(self, sample_products):
        """Test that retrieve_candidates returns valid product list (contract)."""
        mock_store = MockProductStore(sample_products)
        matcher = ProductMatcher(product_store=mock_store)

        # Use builder for medical reasoning
        reasoning = (MedicalReasoningBuilder()
                     .with_symptoms(["headache"])
                     .with_treatment_type("analgesics")
                     .build())

        results = matcher.retrieve_candidates(reasoning, "headache", top_k=10)

        # Verify contract compliance (not implementation)
        assert_product_list_valid(results, context="headache query", max_count=10)

    def test_empty_store_returns_empty_list(self):
        """Test empty store behavior (contract)."""
        mock_store = MockProductStore([])
        matcher = ProductMatcher(product_store=mock_store)

        reasoning = simple_medical_reasoning("headache", "analgesics")
        results = matcher.retrieve_candidates(reasoning, "headache")

        # Contract: empty input should return empty output
        assert_product_list_valid(results, context="empty store")
        assert len(results) == 0, "Empty store should return empty results"

    def test_respects_top_k_limit(self, sample_products):
        """Test that top_k parameter is respected (contract)."""
        mock_store = MockProductStore(sample_products)
        matcher = ProductMatcher(product_store=mock_store)

        reasoning = simple_medical_reasoning("pain", "analgesics")
        results = matcher.retrieve_candidates(reasoning, "pain", top_k=2)

        # Contract: results should not exceed top_k
        assert_product_list_valid(results, context="top_k=2", max_count=2)

    def test_scenario_simple_symptom(self, sample_products):
        """Test using contract scenario."""
        mock_store = MockProductStore(sample_products)
        matcher = ProductMatcher(product_store=mock_store)

        scenario = ProductMatchingTestScenarios.simple_symptom_scenario()

        # Build reasoning from scenario
        reasoning = (MedicalReasoningBuilder()
                     .with_symptoms(scenario["medical_reasoning"]["symptoms"])
                     .with_treatment_type(scenario["medical_reasoning"]["treatment_type"])
                     .with_likely_cause(scenario["medical_reasoning"]["likely_cause"])
                     .build())

        results = matcher.retrieve_candidates(reasoning)

        # Verify using scenario expectations
        min_results = scenario["expected_behavior"]["min_results"]
        max_results = scenario["expected_behavior"]["max_results"]

        assert len(results) >= min_results, f"Should have at least {min_results} results"
        assert len(results) <= max_results, f"Should have at most {max_results} results"


# =========================================================================
# Contract-Based Tests for refine_selection
# =========================================================================


class TestRefineSelectionContract:
    """Contract-based tests for refine_selection method."""

    def test_returns_subset_of_candidates(self, sample_products):
        """Test that refined selection is subset of candidates (contract)."""
        mock_model = MockMedicalModel(return_products=sample_products[:2])
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store, medical_model=mock_model)

        reasoning = simple_medical_reasoning("headache", "analgesics")
        refined = matcher.refine_selection(sample_products, reasoning, max_products=3)

        # Contract: refined list should be valid and <= max_products
        assert_product_list_valid(refined, context="refined selection", max_count=3)
        assert all(p in sample_products for p in refined), "Refined products must be from candidates"

    def test_empty_candidates_returns_empty(self):
        """Test empty input behavior (contract)."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        reasoning = simple_medical_reasoning("headache")
        refined = matcher.refine_selection([], reasoning, max_products=3)

        # Contract: empty input should return empty output
        assert refined == [], "Empty candidates should return empty list"

    def test_without_medical_model_returns_top_candidates(self, sample_products):
        """Test fallback behavior without medical model (contract)."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store, medical_model=None)

        reasoning = simple_medical_reasoning("headache")
        refined = matcher.refine_selection(sample_products, reasoning, max_products=2)

        # Contract: should return valid subset even without model
        assert_product_list_valid(refined, max_count=2)
        assert len(refined) <= 2, "Should respect max_products even without model"


# =========================================================================
# Contract-Based Tests for pharmacological_rerank
# =========================================================================


class TestPharmacologicalRerankContract:
    """Contract-based tests for pharmacological_rerank method."""

    def test_returns_all_input_products(self, sample_products):
        """Test that reranking returns all products (contract)."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        reranked = matcher.pharmacological_rerank(sample_products, "analgesics")

        # Contract: reranking should preserve count (may reorder)
        assert len(reranked) == len(sample_products), "Reranking should not drop products"
        # Check that all original products are present (order may change)
        assert all(any(p.id == orig.id for p in reranked) for orig in sample_products), \
            "Reranking should preserve all products"

    def test_empty_list_returns_empty(self):
        """Test empty input behavior (contract)."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        reranked = matcher.pharmacological_rerank([], "analgesics")

        # Contract: empty input should return empty output
        assert reranked == []


# =========================================================================
# Contract-Based Tests for deduplicate_by_ingredient
# =========================================================================


class TestDeduplicateByIngredientContract:
    """Contract-based tests for deduplicate_by_ingredient method."""

    def test_respects_max_products_limit(self, sample_products):
        """Test that max_products limit is respected (contract)."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        deduplicated = matcher.deduplicate_by_ingredient(sample_products, max_products=2)

        # Contract: result should not exceed max_products
        assert_product_list_valid(deduplicated, max_count=2)

    def test_returns_subset_of_input(self, sample_products):
        """Test that result is subset of input (contract)."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        deduplicated = matcher.deduplicate_by_ingredient(sample_products, max_products=3)

        # Contract: deduplication should return subset
        assert all(p in sample_products for p in deduplicated), "Result must be subset of input"

    def test_empty_list_returns_empty(self):
        """Test empty input behavior (contract)."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        deduplicated = matcher.deduplicate_by_ingredient([], max_products=3)

        # Contract: empty input should return empty output
        assert deduplicated == []


# =========================================================================
# Contract-Based Tests for filter_by_name_match
# =========================================================================


class TestFilterByNameMatchContract:
    """Contract-based tests for filter_by_name_match method."""

    def test_returns_subset_of_input(self, sample_products):
        """Test that filter returns subset (contract)."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        filtered = matcher.filter_by_name_match(sample_products, "парацетамол")

        # Contract: filtering should return subset
        assert all(p in sample_products for p in filtered), "Filtered must be subset of input"

    def test_empty_search_returns_all(self, sample_products):
        """Test empty search behavior (contract)."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        filtered = matcher.filter_by_name_match(sample_products, "")

        # Contract: empty search should return all products
        assert len(filtered) == len(sample_products), "Empty search should return all"

    def test_no_matches_returns_top_results(self, sample_products):
        """Test fallback behavior when no matches (contract)."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        filtered = matcher.filter_by_name_match(sample_products, "nonexistent")

        # Contract: no matches should return top results (fallback behavior)
        assert_product_list_valid(filtered, max_count=3)
        assert len(filtered) <= 3, "Fallback should return max 3 products"


# =========================================================================
# Integration Tests Using Contracts
# =========================================================================


class TestProductMatcherIntegrationContract:
    """Contract-based integration tests."""

    def test_full_pipeline_produces_valid_output(self, sample_products):
        """Test complete pipeline using contracts."""
        mock_store = MockProductStore(sample_products)
        mock_model = MockMedicalModel(return_products=sample_products[:2])
        matcher = ProductMatcher(product_store=mock_store, medical_model=mock_model)

        # Use builder for input
        reasoning = (MedicalReasoningBuilder()
                     .with_symptoms(["headache", "fever"])
                     .with_treatment_type("analgesics")
                     .with_likely_cause("common cold")
                     .build())

        # Stage 1: Retrieve
        candidates = matcher.retrieve_candidates(reasoning, "headache", top_k=10)
        assert_product_list_valid(candidates, context="retrieve stage", max_count=10)

        # Stage 2: Rerank
        reranked = matcher.pharmacological_rerank(candidates, reasoning.treatment_type)
        assert len(reranked) == len(candidates), "Reranking preserves count"

        # Stage 3: Refine
        refined = matcher.refine_selection(reranked, reasoning, max_products=5)
        assert_product_list_valid(refined, context="refine stage", max_count=5)

        # Stage 4: Deduplicate
        final = matcher.deduplicate_by_ingredient(refined, max_products=3)
        assert_product_list_valid(final, context="final stage", max_count=3)

        # Overall contract: final result should be valid products
        assert all(isinstance(p, type(sample_products[0])) for p in final)
