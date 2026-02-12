"""
Tests for MedGemma medical model caching functionality.

Tests the LRU cache for medical reasoning results without loading the actual model.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCacheKeyNormalization:
    """Tests for query normalization in cache key generation."""

    def test_normalize_removes_extra_whitespace(self):
        """Should normalize multiple spaces to single space."""
        from src.medical_model import MedicalModel

        model = MedicalModel.__new__(MedicalModel)
        model._cache = {}
        model._cache_size = 100

        result = model._normalize_query("headache   and   fever")
        assert result == "headache and fever"

    def test_normalize_lowercases(self):
        """Should convert to lowercase."""
        from src.medical_model import MedicalModel

        model = MedicalModel.__new__(MedicalModel)
        model._cache = {}
        model._cache_size = 100

        result = model._normalize_query("HEADACHE And Fever")
        assert result == "headache and fever"

    def test_normalize_strips_trailing_punctuation(self):
        """Should remove trailing question marks and punctuation."""
        from src.medical_model import MedicalModel

        model = MedicalModel.__new__(MedicalModel)
        model._cache = {}
        model._cache_size = 100

        assert model._normalize_query("headache?") == "headache"
        assert model._normalize_query("headache!") == "headache"
        assert model._normalize_query("headache...") == "headache"
        assert model._normalize_query("headache?!") == "headache"

    def test_normalize_handles_empty_string(self):
        """Should handle empty string."""
        from src.medical_model import MedicalModel

        model = MedicalModel.__new__(MedicalModel)
        model._cache = {}
        model._cache_size = 100

        assert model._normalize_query("") == ""

    def test_equivalent_queries_same_key(self):
        """Semantically equivalent queries should produce same cache key."""
        from src.medical_model import MedicalModel

        model = MedicalModel.__new__(MedicalModel)
        model._cache = {}
        model._cache_size = 100

        key1 = model._get_cache_key("headache and fever", 0.3)
        key2 = model._get_cache_key("HEADACHE AND FEVER", 0.3)
        key3 = model._get_cache_key("headache  and  fever?", 0.3)

        assert key1 == key2
        assert key1 == key3

    def test_different_queries_different_keys(self):
        """Different queries should produce different cache keys."""
        from src.medical_model import MedicalModel

        model = MedicalModel.__new__(MedicalModel)
        model._cache = {}
        model._cache_size = 100

        key1 = model._get_cache_key("headache", 0.3)
        key2 = model._get_cache_key("stomachache", 0.3)

        assert key1 != key2

    def test_different_temperature_different_keys(self):
        """Same query with different temperature should have different keys."""
        from src.medical_model import MedicalModel

        model = MedicalModel.__new__(MedicalModel)
        model._cache = {}
        model._cache_size = 100

        key1 = model._get_cache_key("headache", 0.3)
        key2 = model._get_cache_key("headache", 0.7)

        assert key1 != key2


class TestCacheLRUBehavior:
    """Tests for LRU cache eviction behavior."""

    def test_cache_stores_and_retrieves(self):
        """Should store and retrieve cached items."""
        from src.medical_model import MedicalModel, MedicalReasoning
        from collections import OrderedDict

        model = MedicalModel.__new__(MedicalModel)
        model._cache = OrderedDict()
        model._cache_size = 100
        model._cache_hits = 0
        model._cache_misses = 0

        reasoning = MedicalReasoning(
            symptoms=["headache"],
            likely_cause="tension",
            treatment_type="analgesics",
            warnings=[]
        )

        # Store in cache
        model._put_in_cache("test_key", reasoning)

        # Retrieve from cache
        result = model._get_from_cache("test_key")

        assert result is not None
        assert result.symptoms == ["headache"]
        assert result.likely_cause == "tension"

    def test_cache_miss_returns_none(self):
        """Should return None for cache miss."""
        from src.medical_model import MedicalModel
        from collections import OrderedDict

        model = MedicalModel.__new__(MedicalModel)
        model._cache = OrderedDict()
        model._cache_size = 100
        model._cache_hits = 0
        model._cache_misses = 0

        result = model._get_from_cache("nonexistent_key")

        assert result is None
        assert model._cache_misses == 1

    def test_cache_evicts_oldest_when_full(self):
        """Should evict oldest item when cache is full."""
        from src.medical_model import MedicalModel, MedicalReasoning
        from collections import OrderedDict

        model = MedicalModel.__new__(MedicalModel)
        model._cache = OrderedDict()
        model._cache_size = 3  # Small cache for testing
        model._cache_hits = 0
        model._cache_misses = 0

        reasoning = MedicalReasoning(
            symptoms=["test"],
            likely_cause="test",
            treatment_type="test",
            warnings=[]
        )

        # Fill cache
        model._put_in_cache("key1", reasoning)
        model._put_in_cache("key2", reasoning)
        model._put_in_cache("key3", reasoning)

        assert len(model._cache) == 3
        assert "key1" in model._cache

        # Add one more - should evict key1
        model._put_in_cache("key4", reasoning)

        assert len(model._cache) == 3
        assert "key1" not in model._cache
        assert "key4" in model._cache

    def test_cache_access_updates_lru_order(self):
        """Accessing a cached item should move it to most recently used."""
        from src.medical_model import MedicalModel, MedicalReasoning
        from collections import OrderedDict

        model = MedicalModel.__new__(MedicalModel)
        model._cache = OrderedDict()
        model._cache_size = 3
        model._cache_hits = 0
        model._cache_misses = 0

        reasoning = MedicalReasoning(
            symptoms=["test"],
            likely_cause="test",
            treatment_type="test",
            warnings=[]
        )

        # Fill cache
        model._put_in_cache("key1", reasoning)
        model._put_in_cache("key2", reasoning)
        model._put_in_cache("key3", reasoning)

        # Access key1 - should move it to end
        model._get_from_cache("key1")

        # Add new item - should evict key2 (now oldest)
        model._put_in_cache("key4", reasoning)

        assert "key1" in model._cache  # Was accessed, so preserved
        assert "key2" not in model._cache  # Was oldest, so evicted
        assert "key3" in model._cache
        assert "key4" in model._cache


class TestCacheStatistics:
    """Tests for cache statistics tracking."""

    def test_hit_rate_calculation(self):
        """Should correctly calculate cache hit rate."""
        from src.medical_model import MedicalModel, MedicalReasoning
        from collections import OrderedDict

        model = MedicalModel.__new__(MedicalModel)
        model._cache = OrderedDict()
        model._cache_size = 100
        model._cache_hits = 0
        model._cache_misses = 0

        reasoning = MedicalReasoning(
            symptoms=["test"],
            likely_cause="test",
            treatment_type="test",
            warnings=[]
        )

        # Store item
        model._put_in_cache("key1", reasoning)

        # 2 hits
        model._get_from_cache("key1")
        model._get_from_cache("key1")

        # 1 miss
        model._get_from_cache("nonexistent")

        stats = model.get_cache_stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["total_requests"] == 3
        assert stats["hit_rate_percent"] == pytest.approx(66.67, rel=0.01)

    def test_cache_stats_structure(self):
        """Cache stats should have expected structure."""
        from src.medical_model import MedicalModel
        from collections import OrderedDict

        model = MedicalModel.__new__(MedicalModel)
        model._cache = OrderedDict()
        model._cache_size = 500
        model._cache_hits = 10
        model._cache_misses = 5

        stats = model.get_cache_stats()

        assert "size" in stats
        assert "max_size" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate_percent" in stats
        assert "total_requests" in stats

        assert stats["max_size"] == 500
        assert stats["hits"] == 10
        assert stats["misses"] == 5

    def test_clear_cache(self):
        """Should clear all cached items."""
        from src.medical_model import MedicalModel, MedicalReasoning
        from collections import OrderedDict

        model = MedicalModel.__new__(MedicalModel)
        model._cache = OrderedDict()
        model._cache_size = 100
        model._cache_hits = 0
        model._cache_misses = 0

        reasoning = MedicalReasoning(
            symptoms=["test"],
            likely_cause="test",
            treatment_type="test",
            warnings=[]
        )

        model._put_in_cache("key1", reasoning)
        model._put_in_cache("key2", reasoning)

        assert len(model._cache) == 2

        model.clear_cache()

        assert len(model._cache) == 0


class TestCacheIntegration:
    """Integration tests for caching with mocked model inference."""

    @pytest.fixture
    def mock_medical_model(self):
        """Create a MedicalModel with mocked inference."""
        with patch('src.medical_model.load') as mock_load:
            with patch('src.medical_model.generate') as mock_generate:
                with patch('src.medical_model.make_sampler') as mock_sampler:
                    # Setup mocks
                    mock_load.return_value = (Mock(), Mock())
                    mock_generate.return_value = '{"symptoms": ["headache"], "likely_cause": "tension", "treatment_type": "analgesics", "warnings": [], "see_doctor": false}'
                    mock_sampler.return_value = Mock()

                    from src.medical_model import MedicalModel
                    model = MedicalModel()
                    model.load()

                    yield model, mock_generate

    def test_first_call_runs_inference(self, mock_medical_model):
        """First call should run model inference."""
        model, mock_generate = mock_medical_model

        result = model.get_medical_reasoning("headache")

        assert result is not None
        assert mock_generate.called
        assert model._cache_misses == 1

    def test_second_call_uses_cache(self, mock_medical_model):
        """Second identical call should use cache."""
        model, mock_generate = mock_medical_model

        # First call
        result1 = model.get_medical_reasoning("headache")
        call_count_after_first = mock_generate.call_count

        # Second call (should use cache)
        result2 = model.get_medical_reasoning("headache")

        assert result1.symptoms == result2.symptoms
        assert mock_generate.call_count == call_count_after_first  # No additional calls
        assert model._cache_hits == 1

    def test_normalized_queries_share_cache(self, mock_medical_model):
        """Normalized equivalent queries should share cache entry."""
        model, mock_generate = mock_medical_model

        # First call
        result1 = model.get_medical_reasoning("headache")
        call_count_after_first = mock_generate.call_count

        # Second call with different formatting
        result2 = model.get_medical_reasoning("HEADACHE?")

        assert mock_generate.call_count == call_count_after_first  # No additional calls
        assert model._cache_hits == 1

    def test_use_cache_false_bypasses_cache(self, mock_medical_model):
        """Setting use_cache=False should bypass cache."""
        model, mock_generate = mock_medical_model

        # First call
        model.get_medical_reasoning("headache")
        call_count_after_first = mock_generate.call_count

        # Second call with use_cache=False
        model.get_medical_reasoning("headache", use_cache=False)

        assert mock_generate.call_count == call_count_after_first + 1  # Additional call made
