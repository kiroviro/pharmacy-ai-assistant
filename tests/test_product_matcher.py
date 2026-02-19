"""
Comprehensive tests for ProductMatcher class.

Tests the two-stage product matching pipeline:
1. retrieve_candidates: Fast vector search
2. refine_selection: Optional LLM refinement
3. pharmacological_rerank: Ingredient-based prioritization
4. deduplicate_by_ingredient: Variety enforcement
5. filter_by_name_match: Catalog query filtering
"""

import pytest

from src.medical_model import MedicalReasoning
from src.common.models import Product
from src.pipeline.product_matcher import ProductMatcher
from src.pipeline.symptom_mappings import extract_treatment_from_query


# =========================================================================
# Mock Classes
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
# Test Fixtures
# =========================================================================


@pytest.fixture
def sample_products():
    """Create sample products for testing."""
    return [
        Product(
            id="1",
            title="Парацетамол 500 мг",
            brand="BrandA",
            composition="Paracetamol 500mg",
            description="Pain relief",
            price_bgn=5.00,
            price_eur=2.50,
        ),
        Product(
            id="2",
            title="Ибупрофен 400 мг",
            brand="BrandB",
            composition="Ibuprofen 400mg",
            description="Anti-inflammatory",
            price_bgn=8.00,
            price_eur=4.00,
        ),
        Product(
            id="3",
            title="Парацетамол 250 мг",
            brand="BrandC",
            composition="Paracetamol 250mg",
            description="For children",
            price_bgn=4.00,
            price_eur=2.00,
        ),
        Product(
            id="4",
            title="Витамин C",
            brand="BrandD",
            composition="Ascorbic acid 1000mg",
            description="Vitamin supplement",
            price_bgn=12.00,
            price_eur=6.00,
        ),
    ]


@pytest.fixture
def sample_medical_reasoning():
    """Create sample medical reasoning."""
    return MedicalReasoning(
        symptoms=["headache", "fever"],
        likely_cause="common cold",
        treatment_type="analgesics",
        warnings=["consult doctor if symptoms persist"],
        see_doctor=False,
        user_conditions=[],
    )


# =========================================================================
# Test retrieve_candidates
# =========================================================================


class TestRetrieveCandidates:
    """Test the retrieve_candidates method (Stage 1: vector search)."""

    def test_retrieve_with_category(self, sample_products, sample_medical_reasoning):
        """Test retrieval with category-aware search."""
        mock_store = MockProductStore(sample_products)
        matcher = ProductMatcher(product_store=mock_store)

        results = matcher.retrieve_candidates(sample_medical_reasoning, "болка в главата", top_k=10)

        assert len(results) > 0
        assert all(isinstance(p, Product) for p in results)

    def test_retrieve_empty_store(self, sample_medical_reasoning):
        """Test retrieval from empty product store."""
        mock_store = MockProductStore([])
        matcher = ProductMatcher(product_store=mock_store)

        results = matcher.retrieve_candidates(sample_medical_reasoning, "headache")

        assert results == []

    def test_retrieve_without_treatment_type(self, sample_products):
        """Test retrieval when treatment_type is missing."""
        mock_store = MockProductStore(sample_products)
        matcher = ProductMatcher(product_store=mock_store)

        reasoning = MedicalReasoning(
            symptoms=["headache"],
            likely_cause="tension",
            treatment_type="",
            warnings=[],
        )

        results = matcher.retrieve_candidates(reasoning, "headache")

        assert len(results) > 0

    def test_retrieve_with_gi_symptoms(self, sample_products):
        """Test that GI symptoms override treatment type."""
        mock_store = MockProductStore(sample_products)
        matcher = ProductMatcher(product_store=mock_store)

        reasoning = MedicalReasoning(
            symptoms=["cough"],
            likely_cause="cold",
            treatment_type="cough",
            warnings=[],
        )

        # Query with GI symptoms should override treatment_type
        results = matcher.retrieve_candidates(reasoning, "диария и стомашна болка")

        assert len(results) > 0


# =========================================================================
# Test refine_selection
# =========================================================================


class TestRefineSelection:
    """Test the refine_selection method (Stage 2: LLM refinement)."""

    def test_refine_with_medical_model(self, sample_products, sample_medical_reasoning):
        """Test refinement with medical model available."""
        mock_model = MockMedicalModel(return_products=sample_products[:2])
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store, medical_model=mock_model)

        refined = matcher.refine_selection(sample_products, sample_medical_reasoning, max_products=3)

        assert len(refined) <= 3
        assert all(isinstance(p, Product) for p in refined)

    def test_refine_without_medical_model(self, sample_products, sample_medical_reasoning):
        """Test refinement falls back when no medical model."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store, medical_model=None)

        refined = matcher.refine_selection(sample_products, sample_medical_reasoning, max_products=3)

        assert len(refined) <= 3
        assert refined == sample_products[:3]

    def test_refine_empty_candidates(self, sample_medical_reasoning):
        """Test refinement with no candidates."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        refined = matcher.refine_selection([], sample_medical_reasoning, max_products=3)

        assert refined == []

    def test_refine_llm_exception_fallback(self, sample_products, sample_medical_reasoning):
        """Test refinement falls back on LLM exception."""

        class FailingMedicalModel:
            def refine_product_selection(self, *args, **kwargs):
                raise RuntimeError("LLM failed")

        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store, medical_model=FailingMedicalModel())

        refined = matcher.refine_selection(sample_products, sample_medical_reasoning, max_products=3)

        # Should fall back to top candidates
        assert len(refined) <= 3


# =========================================================================
# Test pharmacological_rerank
# =========================================================================


class TestPharmacologicalRerank:
    """Test the pharmacological_rerank method."""

    def test_rerank_prioritizes_recommended_ingredients(self, sample_products):
        """Test that products with recommended ingredients are ranked higher."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        # For analgesics, paracetamol and ibuprofen are recommended
        reranked = matcher.pharmacological_rerank(sample_products, "analgesics")

        # First two products should be pain relievers (paracetamol, ibuprofen)
        assert "парацетамол" in reranked[0].title.lower() or "ибупрофен" in reranked[0].title.lower()

    def test_rerank_empty_products(self):
        """Test reranking empty product list."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        reranked = matcher.pharmacological_rerank([], "analgesics")

        assert reranked == []

    def test_rerank_no_treatment_type(self, sample_products):
        """Test reranking without treatment type."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        reranked = matcher.pharmacological_rerank(sample_products, "")

        # Should return products in original order
        assert len(reranked) == len(sample_products)


# =========================================================================
# Test deduplicate_by_ingredient
# =========================================================================


class TestDeduplicateByIngredient:
    """Test the deduplicate_by_ingredient method."""

    def test_deduplicate_removes_duplicates(self, sample_products):
        """Test that duplicate ingredients are removed."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        # Two products have paracetamol
        deduplicated = matcher.deduplicate_by_ingredient(sample_products, max_products=3, max_per_ingredient=1)

        # Should keep only one paracetamol product
        paracetamol_count = sum(1 for p in deduplicated if "парацетамол" in p.title.lower())
        assert paracetamol_count == 1

    def test_deduplicate_respects_max_products(self, sample_products):
        """Test that max_products limit is respected."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        deduplicated = matcher.deduplicate_by_ingredient(sample_products, max_products=2)

        assert len(deduplicated) <= 2

    def test_deduplicate_empty_products(self):
        """Test deduplication with empty product list."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        deduplicated = matcher.deduplicate_by_ingredient([], max_products=3)

        assert deduplicated == []

    def test_deduplicate_allows_multiple_per_ingredient(self, sample_products):
        """Test that max_per_ingredient allows multiple products."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        # Allow 2 products per ingredient
        deduplicated = matcher.deduplicate_by_ingredient(sample_products, max_products=4, max_per_ingredient=2)

        # Should keep both paracetamol products
        paracetamol_count = sum(1 for p in deduplicated if "парацетамол" in p.title.lower())
        assert paracetamol_count == 2


# =========================================================================
# Test filter_by_name_match
# =========================================================================


class TestFilterByNameMatch:
    """Test the filter_by_name_match method."""

    def test_filter_matches_product_name(self, sample_products):
        """Test filtering by product name."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        filtered = matcher.filter_by_name_match(sample_products, "парацетамол")

        assert len(filtered) > 0
        assert all("парацетамол" in p.title.lower() for p in filtered)

    def test_filter_matches_brand_name(self, sample_products):
        """Test filtering by brand name."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        filtered = matcher.filter_by_name_match(sample_products, "BrandA")

        assert len(filtered) > 0
        assert all(p.brand == "BrandA" for p in filtered)

    def test_filter_ignores_generic_terms(self, sample_products):
        """Test that generic terms don't over-filter."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        # "мг" is a generic term and should not filter
        filtered = matcher.filter_by_name_match(sample_products, "мг")

        assert len(filtered) == len(sample_products)

    def test_filter_empty_search_term(self, sample_products):
        """Test filtering with empty search term."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        filtered = matcher.filter_by_name_match(sample_products, "")

        assert len(filtered) == len(sample_products)

    def test_filter_no_matches_returns_top_results(self, sample_products):
        """Test that no matches returns top 3 results."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        filtered = matcher.filter_by_name_match(sample_products, "nonexistent")

        assert len(filtered) == 3


# =========================================================================
# Test Helper Methods
# =========================================================================


class TestHelperMethods:
    """Test helper methods in ProductMatcher."""

    def test_build_search_query_with_treatment_type(self, sample_medical_reasoning):
        """Test search query building with treatment type."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        query = matcher._build_search_query(sample_medical_reasoning, "headache")

        assert "analgesics" in query
        assert "headache" in query or "fever" in query

    def test_build_search_query_filters_non_useful_symptoms(self):
        """Test that non-useful symptoms are filtered."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        reasoning = MedicalReasoning(
            symptoms=["drug interaction query", "headache"],
            likely_cause="tension",
            treatment_type="analgesics",
            warnings=[],
        )

        query = matcher._build_search_query(reasoning, "")

        assert "drug interaction query" not in query
        assert "analgesics" in query

    def test_extract_treatment_from_query_diarrhea(self):
        """Test treatment extraction for diarrhea (now uses centralized function)."""
        treatment = extract_treatment_from_query("имам диария и болки в корема")
        assert treatment == "antidiarrheal"

    def test_extract_treatment_from_query_constipation(self):
        """Test treatment extraction for constipation (now uses centralized function)."""
        treatment = extract_treatment_from_query("запек от няколко дни")
        assert treatment == "laxatives"

    def test_extract_treatment_from_query_heartburn(self):
        """Test treatment extraction for heartburn (now uses centralized function)."""
        treatment = extract_treatment_from_query("имам рефлукс и киселини")
        assert treatment == "antacids"

    def test_is_drug_combination_query(self):
        """Test drug combination query detection."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        is_combo = matcher._is_drug_combination_query("може ли парацетамол заедно с ибупрофен")

        assert is_combo is True

    def test_is_not_drug_combination_query(self):
        """Test that regular queries are not flagged as combo queries."""
        mock_store = MockProductStore()
        matcher = ProductMatcher(product_store=mock_store)

        is_combo = matcher._is_drug_combination_query("болка в главата")

        assert is_combo is False


# =========================================================================
# Integration Tests
# =========================================================================


class TestProductMatcherIntegration:
    """Integration tests for the full ProductMatcher pipeline."""

    def test_full_pipeline_with_medical_model(self, sample_products, sample_medical_reasoning):
        """Test the complete pipeline: retrieve → rerank → refine → deduplicate."""
        mock_store = MockProductStore(sample_products)
        mock_model = MockMedicalModel(return_products=sample_products[:2])
        matcher = ProductMatcher(product_store=mock_store, medical_model=mock_model)

        # Stage 1: Retrieve candidates
        candidates = matcher.retrieve_candidates(sample_medical_reasoning, "headache", top_k=10)

        # Stage 2: Pharmacological rerank
        reranked = matcher.pharmacological_rerank(candidates, sample_medical_reasoning.treatment_type)

        # Stage 3: LLM refinement
        refined = matcher.refine_selection(reranked, sample_medical_reasoning, max_products=5)

        # Stage 4: Deduplicate
        final = matcher.deduplicate_by_ingredient(refined, max_products=3)

        assert len(final) <= 3
        assert all(isinstance(p, Product) for p in final)

    def test_full_pipeline_without_medical_model(self, sample_products, sample_medical_reasoning):
        """Test the complete pipeline without LLM refinement."""
        mock_store = MockProductStore(sample_products)
        matcher = ProductMatcher(product_store=mock_store, medical_model=None)

        # Stage 1: Retrieve candidates
        candidates = matcher.retrieve_candidates(sample_medical_reasoning, "headache", top_k=10)

        # Stage 2: Pharmacological rerank
        reranked = matcher.pharmacological_rerank(candidates, sample_medical_reasoning.treatment_type)

        # Stage 3: Deduplicate (skip refinement)
        final = matcher.deduplicate_by_ingredient(reranked, max_products=3)

        assert len(final) <= 3
        assert all(isinstance(p, Product) for p in final)
