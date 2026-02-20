"""
Comprehensive tests for ProductStore (src/product_store.py).

Goal: Increase coverage from 18% to 75%+
"""

import pytest
from unittest.mock import patch, MagicMock
from src.product_store import (
    ProductStore,
    _is_homeopathic_product,
    MIN_SIMILARITY_THRESHOLD,
    TREATMENT_CATEGORY_MAP,
)


class TestProductStoreInitialization:
    """Test product store initialization."""

    def test_init_creates_db_directory(self, tmp_path):
        """Test that database directory is created if it doesn't exist."""
        db_path = tmp_path / "test_chromadb"
        assert not db_path.exists()

        store = ProductStore(db_path=str(db_path))

        assert db_path.exists()
        assert store.db_path == db_path

    def test_embedding_function_lazy_loaded(self, tmp_path):
        """Test that embedding function is only loaded when accessed."""
        store = ProductStore(db_path=str(tmp_path / "test_db"))

        # Not loaded initially
        assert store._embedding_fn is None

        # Loaded on first access
        _ = store.embedding_fn
        assert store._embedding_fn is not None


class TestHomeopathyDetection:
    """Test homeopathic product filtering."""

    def test_homeopathy_detected_by_marker(self):
        """Test that homeopathic markers are detected."""
        test_cases = [
            ("хомеопатичен продукт", True),
            ("Boiron homeopathic remedy", True),
            ("5 CH потенция", True),
            ("9 СН разтвор", True),
            ("3 DH формула", True),
            ("обикновен парацетамол", False),
            ("ибупрофен таблетки", False),
        ]

        for text, expected in test_cases:
            result = _is_homeopathic_product(text)
            assert result == expected, f"Failed for: {text}"

    def test_homeopathy_case_insensitive(self):
        """Test that homeopathy detection is case-insensitive."""
        assert _is_homeopathic_product("ХОМЕОПАТИЧЕН")
        assert _is_homeopathic_product("homeopathic")
        assert _is_homeopathic_product("Boiron")


class TestHybridSearch:
    """Test hybrid search algorithm (vector + keyword boost)."""

    @pytest.fixture
    def mock_store(self, tmp_path):
        """Create a mock product store."""
        store = ProductStore(db_path=str(tmp_path / "test_db"))
        # Mock the collection
        store._collection = MagicMock()
        return store

    def test_keyword_boost_applied(self, mock_store):
        """Test that exact keyword matches get boosted similarity scores."""
        # Mock ChromaDB response
        mock_results = {
            "ids": [["1", "2", "3"]],
            "documents": [["Product with парацетамол", "Ибупрофен продукт", "Друг продукт"]],
            "metadatas": [[
                {"title": "Парацетамол 500мг", "is_otc": True},
                {"title": "Ибупрофен", "is_otc": True},
                {"title": "Витамин C", "is_otc": True},
            ]],
            "distances": [[0.3, 0.4, 0.5]],  # Lower = more similar
        }
        mock_store._collection.query.return_value = mock_results

        # Search for "парацетамол" - should boost first product
        results = mock_store.hybrid_search("парацетамол", n_results=3)

        # hybrid_search returns list[dict], each with 'score' field (higher is better)
        # First product contains keyword, should have higher score than base (1 - 0.3 = 0.7)
        assert len(results) == 3
        assert results[0]["score"] > 0.7  # Boosted above base score
        assert results[0]["title"] == "Парацетамол 500мг"

    def test_multiple_keyword_matches(self, mock_store):
        """Test that multiple keyword matches accumulate boost."""
        mock_results = {
            "ids": [["1"]],
            "documents": [["болка главоболие продукт"]],
            "metadatas": [[{"title": "Product for болка and главоболие", "is_otc": True}]],  # Keywords in title
            "distances": [[0.5]],
        }
        mock_store._collection.query.return_value = mock_results

        results = mock_store.hybrid_search("болка главоболие", n_results=1)

        # hybrid_search returns list[dict] with 'score' field
        # Base score would be 1 - 0.5 = 0.5, but should be boosted higher by keywords in title
        assert len(results) == 1
        assert results[0]["score"] > 0.5  # Boosted by multiple keyword matches in title


class TestCategoryAwareSearch:
    """Test category-aware search functionality."""

    @pytest.fixture
    def mock_store(self, tmp_path):
        store = ProductStore(db_path=str(tmp_path / "test_db"))
        store._collection = MagicMock()
        return store

    def test_treatment_category_mapping_exists(self):
        """Test that treatment category mappings are defined."""
        assert "fever" in TREATMENT_CATEGORY_MAP
        assert "pain" in TREATMENT_CATEGORY_MAP
        assert "allergy" in TREATMENT_CATEGORY_MAP  # Fixed: "allergy" not "allergies"

    def test_category_keywords_boost_relevance(self, mock_store):
        """Test that category keywords improve search results."""
        # Mock response with fever-related products
        mock_results = {
            "ids": [["1", "2"]],
            "documents": [["температура продукт", "друг продукт"]],
            "metadatas": [[
                {"title": "температура Парацетамол", "is_otc": True},  # Keyword in title
                {"title": "Витамини", "is_otc": True},
            ]],
            "distances": [[0.4, 0.4]],  # Same base distance
        }
        mock_store._collection.query.return_value = mock_results

        # Search with query containing "температура" to trigger keyword boost
        results = mock_store.hybrid_search("температура", n_results=2)

        # hybrid_search returns list[dict] - first product should have higher score due to keyword in title
        assert len(results) == 2
        assert results[0]["score"] > 0.6  # Boosted above base (1 - 0.4 = 0.6)
        assert "температура" in results[0]["title"]


class TestHomeopathyFiltering:
    """Test that homeopathic products are filtered from results."""

    @pytest.fixture
    def mock_store(self, tmp_path):
        store = ProductStore(db_path=str(tmp_path / "test_db"))
        store._collection = MagicMock()
        return store

    def test_homeopathy_products_penalized(self, mock_store):
        """Test that homeopathic products get score penalty when ingredients specified."""
        mock_results = {
            "ids": [["1", "2", "3"]],
            "documents": [[
                "Обикновен парацетамол",
                "Хомеопатичен препарат 5 CH",
                "Ибупрофен таблетки",
            ]],
            "metadatas": [[
                {"title": "Парацетамол", "is_otc": True, "composition": "парацетамол 500mg"},
                {"title": "Homeopathic remedy", "is_otc": True, "composition": "homeopathic 5 CH"},
                {"title": "Ибупрофен", "is_otc": True, "composition": "ибупрофен 400mg"},
            ]],
            "distances": [[0.3, 0.3, 0.3]],  # Same base distance
        }
        mock_store._collection.query.return_value = mock_results

        # Search with preferred_ingredients to trigger homeopathy penalty
        results = mock_store.hybrid_search("болка", n_results=3, preferred_ingredients=["парацетамол"])

        # hybrid_search returns list[dict] - homeopathic product should have lower score
        assert len(results) == 3
        titles = [r["title"] for r in results]
        assert "Homeopathic remedy" in titles
        # Homeopathic product should be ranked lower due to penalty
        homeopathy_idx = next(i for i, r in enumerate(results) if "Homeopathic" in r["title"])
        assert homeopathy_idx > 0  # Should not be first due to penalty


class TestSearchEdgeCases:
    """Test edge cases in product search."""

    @pytest.fixture
    def mock_store(self, tmp_path):
        store = ProductStore(db_path=str(tmp_path / "test_db"))
        store._collection = MagicMock()
        return store

    def test_empty_query_handling(self, mock_store):
        """Test that empty queries are handled gracefully."""
        mock_store._collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        results = mock_store.hybrid_search("", n_results=5)

        # hybrid_search returns list[dict] - should be empty
        assert isinstance(results, list)
        assert len(results) == 0

    def test_no_results_returned(self, mock_store):
        """Test handling when no results match."""
        mock_store._collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        results = mock_store.hybrid_search("extremely rare query", n_results=5)

        # hybrid_search returns list[dict] - should be empty
        assert isinstance(results, list)
        assert len(results) == 0

    def test_minimum_similarity_threshold(self, mock_store):
        """Test that results below similarity threshold are filtered."""
        # All results have very low similarity (high distance)
        mock_results = {
            "ids": [["1", "2"]],
            "documents": [["product 1", "product 2"]],
            "metadatas": [[{"title": "P1", "is_otc": True}, {"title": "P2", "is_otc": True}]],
            "distances": [[0.9, 0.95]],  # Very dissimilar (scores would be 0.1, 0.05)
        }
        mock_store._collection.query.return_value = mock_results

        results = mock_store.hybrid_search("totally unrelated", n_results=2)

        # hybrid_search returns list[dict] - low similarity results should be filtered
        # Results with distance > 0.75 (score < 0.25) are filtered by MIN_SIMILARITY_THRESHOLD
        assert len(results) < 2 or all(r["score"] >= MIN_SIMILARITY_THRESHOLD for r in results)


class TestAsyncSearch:
    """Test async search wrapper."""

    @pytest.fixture
    def mock_store(self, tmp_path):
        store = ProductStore(db_path=str(tmp_path / "test_db"))
        store._collection = MagicMock()
        return store

    @pytest.mark.asyncio
    async def test_async_search_calls_sync_search(self, mock_store):
        """Test that async search wrapper calls synchronous search."""
        # hybrid_search returns list[dict], not raw ChromaDB format
        mock_results = [
            {"id": "1", "title": "Test", "is_otc": True, "score": 0.7}
        ]

        # Mock the hybrid_search method to return list format
        with patch.object(mock_store, 'hybrid_search', return_value=mock_results) as mock_search:
            results = await mock_store.hybrid_search_async("test query", n_results=5)

            # Should have called synchronous search
            mock_search.assert_called_once()
            assert results == mock_results


class TestProductRelevanceRanking:
    """Test product ranking and relevance scoring."""

    @pytest.fixture
    def mock_store(self, tmp_path):
        store = ProductStore(db_path=str(tmp_path / "test_db"))
        store._collection = MagicMock()
        return store

    def test_results_sorted_by_distance(self, mock_store):
        """Test that results are sorted by similarity (score descending)."""
        # Unsorted results from ChromaDB
        mock_results = {
            "ids": [["1", "2", "3"]],
            "documents": [["prod 1", "prod 2", "prod 3"]],
            "metadatas": [[
                {"title": "P1", "is_otc": True},
                {"title": "P2", "is_otc": True},
                {"title": "P3", "is_otc": True},
            ]],
            "distances": [[0.5, 0.2, 0.4]],  # Unsorted (scores: 0.5, 0.8, 0.6)
        }
        mock_store._collection.query.return_value = mock_results

        results = mock_store.hybrid_search("query", n_results=3)

        # hybrid_search returns list[dict] sorted by score descending
        assert len(results) == 3
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)  # Highest score first


class TestOTCFiltering:
    """Test OTC (over-the-counter) product filtering."""

    @pytest.fixture
    def mock_store(self, tmp_path):
        store = ProductStore(db_path=str(tmp_path / "test_db"))
        store._collection = MagicMock()
        return store

    def test_prescription_products_included(self, mock_store):
        """Test that hybrid_search does not filter by OTC status (returns all products)."""
        mock_results = {
            "ids": [["1", "2", "3"]],
            "documents": [["prod 1", "prod 2", "prod 3"]],
            "metadatas": [[
                {"title": "OTC Product", "is_otc": True},
                {"title": "Prescription Drug", "is_otc": False},
                {"title": "Another OTC", "is_otc": True},
            ]],
            "distances": [[0.2, 0.3, 0.4]],
        }
        mock_store._collection.query.return_value = mock_results

        results = mock_store.hybrid_search("medicine", n_results=3)

        # hybrid_search returns list[dict] - all products regardless of OTC status
        # OTC filtering happens at query layer, not in product_store
        assert len(results) == 3
        assert results[0]["is_otc"] is True
        assert results[1]["is_otc"] is False  # Prescription products are included
        assert results[2]["is_otc"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
