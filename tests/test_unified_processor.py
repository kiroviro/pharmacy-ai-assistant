"""
Tests for the unified LLM processor.

Tests cover:
- Data class serialization and deserialization
- Cache functionality
- Response parsing
- Fallback behavior
- Integration with safety layer
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.unified_processor import (
    UnifiedProcessor,
    UnifiedProcessorResult,
    IntentResult,
    SafetyResult,
    ExtractionResult,
    ReasoningResult,
    ProcessorCache,
    get_unified_processor,
)


# =============================================================================
# DATA CLASS TESTS
# =============================================================================

class TestIntentResult:
    """Tests for IntentResult dataclass."""

    def test_creation(self):
        result = IntentResult(
            is_pharmacy_related=True,
            confidence=0.95,
            rejection_reason=None,
        )
        assert result.is_pharmacy_related is True
        assert result.confidence == 0.95
        assert result.rejection_reason is None

    def test_rejection(self):
        result = IntentResult(
            is_pharmacy_related=False,
            confidence=0.9,
            rejection_reason="weather_query",
        )
        assert result.is_pharmacy_related is False
        assert result.rejection_reason == "weather_query"


class TestSafetyResult:
    """Tests for SafetyResult dataclass."""

    def test_safe_result(self):
        result = SafetyResult(level="safe")
        assert result.level == "safe"
        assert result.detected_flags == []
        assert result.action == "proceed"

    def test_emergency_result(self):
        result = SafetyResult(
            level="emergency",
            detected_flags=["chest pain", "difficulty breathing"],
            action="call_emergency",
        )
        assert result.level == "emergency"
        assert len(result.detected_flags) == 2
        assert result.action == "call_emergency"


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_default_values(self):
        result = ExtractionResult()
        assert result.symptoms == []
        assert result.user_conditions == []
        assert result.age_group is None
        assert result.query_translated == ""

    def test_with_conditions(self):
        result = ExtractionResult(
            symptoms=["fever", "cough"],
            user_conditions=["pregnancy"],
            age_group="adult",
            query_translated="I have fever and cough",
        )
        assert "fever" in result.symptoms
        assert "pregnancy" in result.user_conditions
        assert result.age_group == "adult"


class TestReasoningResult:
    """Tests for ReasoningResult dataclass."""

    def test_default_values(self):
        result = ReasoningResult()
        assert result.treatment_category == ""
        assert result.explanation == ""
        assert result.self_care_tips == []
        assert result.warnings == []
        assert result.see_doctor is False

    def test_with_reasoning(self):
        result = ReasoningResult(
            treatment_category="antipyretics",
            explanation="Fever is the body fighting infection",
            explanation_bg="Температурата е защитна реакция",
            self_care_tips=["rest", "drink fluids"],
            self_care_tips_bg=["почивайте", "пийте течности"],
            warnings=["see doctor if fever persists"],
            warnings_bg=["посетете лекар ако температурата продължава"],
            see_doctor=False,
        )
        assert result.treatment_category == "antipyretics"
        assert len(result.self_care_tips) == 2
        assert len(result.self_care_tips_bg) == 2


class TestUnifiedProcessorResult:
    """Tests for UnifiedProcessorResult dataclass."""

    def test_to_dict(self):
        result = UnifiedProcessorResult(
            intent=IntentResult(is_pharmacy_related=True, confidence=0.95),
            safety=SafetyResult(level="safe"),
            extraction=ExtractionResult(symptoms=["headache"]),
            reasoning=ReasoningResult(treatment_category="analgesics"),
        )
        data = result.to_dict()

        assert data["intent"]["is_pharmacy_related"] is True
        assert data["safety"]["level"] == "safe"
        assert "headache" in data["extraction"]["symptoms"]
        assert data["reasoning"]["treatment_category"] == "analgesics"

    def test_from_dict(self):
        data = {
            "intent": {"is_pharmacy_related": True, "confidence": 0.9, "rejection_reason": None},
            "safety": {"level": "warning", "detected_flags": ["infant fever"], "action": "warn_and_proceed"},
            "extraction": {"symptoms": ["fever"], "user_conditions": ["child"], "age_group": "infant", "query_translated": "baby has fever"},
            "reasoning": {"treatment_category": "pediatric antipyretics", "see_doctor": True},
        }
        result = UnifiedProcessorResult.from_dict(data)

        assert result.intent.is_pharmacy_related is True
        assert result.safety.level == "warning"
        assert "fever" in result.extraction.symptoms
        assert result.extraction.age_group == "infant"
        assert result.reasoning.see_doctor is True

    def test_roundtrip_serialization(self):
        original = UnifiedProcessorResult(
            intent=IntentResult(is_pharmacy_related=True, confidence=0.95),
            safety=SafetyResult(level="safe", detected_flags=[]),
            extraction=ExtractionResult(symptoms=["cough"], user_conditions=["pregnancy"]),
            reasoning=ReasoningResult(treatment_category="cough suppressants"),
        )
        data = original.to_dict()
        restored = UnifiedProcessorResult.from_dict(data)

        assert restored.intent.is_pharmacy_related == original.intent.is_pharmacy_related
        assert restored.safety.level == original.safety.level
        assert restored.extraction.symptoms == original.extraction.symptoms
        assert restored.reasoning.treatment_category == original.reasoning.treatment_category


# =============================================================================
# CACHE TESTS
# =============================================================================

class TestProcessorCache:
    """Tests for the processor cache."""

    def test_cache_miss(self):
        cache = ProcessorCache(max_size=10)
        result = cache.get("test query")
        assert result is None
        assert cache.get_stats()["misses"] == 1

    def test_cache_hit(self):
        cache = ProcessorCache(max_size=10)
        original = UnifiedProcessorResult(
            intent=IntentResult(is_pharmacy_related=True, confidence=0.95),
            safety=SafetyResult(level="safe"),
            extraction=ExtractionResult(),
        )
        cache.set("test query", original)
        result = cache.get("test query")

        assert result is not None
        assert result.intent.is_pharmacy_related is True
        assert result.from_cache is True
        assert cache.get_stats()["hits"] == 1

    def test_cache_normalization(self):
        """Cache should normalize queries for better hit rate."""
        cache = ProcessorCache(max_size=10)
        original = UnifiedProcessorResult(
            intent=IntentResult(is_pharmacy_related=True, confidence=0.95),
            safety=SafetyResult(level="safe"),
            extraction=ExtractionResult(),
        )
        cache.set("Test Query?", original)

        # Same query with different casing/punctuation should hit cache
        result = cache.get("test query")
        assert result is not None

    def test_cache_eviction(self):
        """Cache should evict old entries when full."""
        cache = ProcessorCache(max_size=3)

        for i in range(5):
            result = UnifiedProcessorResult(
                intent=IntentResult(is_pharmacy_related=True, confidence=float(i) / 10),
                safety=SafetyResult(level="safe"),
                extraction=ExtractionResult(),
            )
            cache.set(f"query {i}", result)

        # First 2 queries should be evicted
        assert cache.get("query 0") is None
        assert cache.get("query 1") is None
        # Later queries should still be in cache
        assert cache.get("query 4") is not None

        stats = cache.get_stats()
        assert stats["size"] == 3

    def test_cache_clear(self):
        cache = ProcessorCache(max_size=10)
        result = UnifiedProcessorResult(
            intent=IntentResult(is_pharmacy_related=True, confidence=0.95),
            safety=SafetyResult(level="safe"),
            extraction=ExtractionResult(),
        )
        cache.set("test", result)
        cache.clear()

        assert cache.get("test") is None
        assert cache.get_stats()["size"] == 0


# =============================================================================
# RESPONSE PARSING TESTS
# =============================================================================

class TestResponseParsing:
    """Tests for LLM response parsing."""

    @pytest.fixture
    def processor(self):
        """Create processor without loading model."""
        proc = UnifiedProcessor.__new__(UnifiedProcessor)
        proc._cache = ProcessorCache(max_size=100)
        proc._loaded = False
        return proc

    def test_parse_valid_json(self, processor):
        """Parser should handle valid JSON responses."""
        response = json.dumps({
            "intent": {"is_pharmacy_related": True, "confidence": 0.95, "rejection_reason": None},
            "safety": {"level": "safe", "detected_flags": [], "action": "proceed"},
            "extracted": {"symptoms": ["headache"], "user_conditions": [], "age_group": "adult", "query_translated": "I have a headache"},
            "recommendation": {"treatment_category": "analgesics", "explanation": "...", "self_care_tips": [], "warnings": [], "see_doctor": False},
        })
        result = processor._parse_response(response, "test query")

        assert result.intent.is_pharmacy_related is True
        assert result.safety.level == "safe"
        assert "headache" in result.extraction.symptoms

    def test_parse_json_with_text(self, processor):
        """Parser should extract JSON from text response."""
        response = 'Here is the analysis:\n{"intent": {"is_pharmacy_related": true, "confidence": 0.9}, "safety": {"level": "safe"}, "extracted": {"symptoms": []}}'
        result = processor._parse_response(response, "test query")

        assert result.intent.is_pharmacy_related is True

    def test_fallback_on_invalid_json(self, processor):
        """Parser should use fallback for invalid JSON."""
        response = "This is not valid JSON at all"
        result = processor._parse_response(response, "главоболие")

        # Fallback should still return a valid result
        assert isinstance(result, UnifiedProcessorResult)
        assert result.intent.confidence == 0.3  # Low confidence for fallback

    def test_fallback_detects_non_medical(self, processor):
        """Fallback should detect obvious non-medical queries."""
        result = processor._fallback_result("какво е времето днес")

        assert result.intent.is_pharmacy_related is False

    def test_fallback_detects_emergency(self, processor):
        """Fallback should detect emergency keywords."""
        result = processor._fallback_result("болка в гърдите не мога да дишам")

        assert result.safety.level == "emergency"
        assert result.safety.action == "call_emergency"


# =============================================================================
# INTEGRATION TESTS (WITH MOCKS)
# =============================================================================

class TestUnifiedProcessorIntegration:
    """Integration tests with mocked LLM."""

    @pytest.fixture
    def mock_processor(self):
        """Create processor with mocked LLM."""
        with patch('src.unified_processor.load') as mock_load, \
             patch('src.unified_processor.generate') as mock_generate:

            mock_load.return_value = (MagicMock(), MagicMock())

            processor = UnifiedProcessor(
                model_path="./test/model",
                cache_size=100,
            )
            processor._mock_generate = mock_generate
            yield processor

    def test_process_medical_query(self, mock_processor):
        """Test processing a medical query."""
        mock_processor._mock_generate.return_value = json.dumps({
            "intent": {"is_pharmacy_related": True, "confidence": 0.95, "rejection_reason": None},
            "safety": {"level": "safe", "detected_flags": [], "action": "proceed"},
            "extracted": {"symptoms": ["headache"], "user_conditions": [], "age_group": "adult", "query_translated": "I have a headache"},
            "recommendation": {"treatment_category": "analgesics", "explanation": "Tension headache", "self_care_tips": ["rest"], "warnings": [], "see_doctor": False},
        })

        result = mock_processor.process("имам главоболие")

        assert result.intent.is_pharmacy_related is True
        assert result.safety.level == "safe"
        assert "headache" in result.extraction.symptoms

    def test_process_non_medical_query(self, mock_processor):
        """Test rejecting a non-medical query."""
        mock_processor._mock_generate.return_value = json.dumps({
            "intent": {"is_pharmacy_related": False, "confidence": 0.92, "rejection_reason": "weather_query"},
            "safety": {"level": "safe", "detected_flags": [], "action": "proceed"},
            "extracted": {"symptoms": [], "user_conditions": [], "age_group": None, "query_translated": "what is the weather"},
            "recommendation": None,
        })

        result = mock_processor.process("какво е времето")

        assert result.intent.is_pharmacy_related is False
        assert result.intent.rejection_reason == "weather_query"

    def test_process_emergency_query(self, mock_processor):
        """Test detecting an emergency."""
        mock_processor._mock_generate.return_value = json.dumps({
            "intent": {"is_pharmacy_related": True, "confidence": 0.99, "rejection_reason": None},
            "safety": {"level": "emergency", "detected_flags": ["chest pain", "difficulty breathing"], "action": "call_emergency"},
            "extracted": {"symptoms": ["chest pain", "difficulty breathing"], "user_conditions": [], "age_group": None, "query_translated": "chest pain and can't breathe"},
            "recommendation": None,
        })

        result = mock_processor.process("болка в гърдите не мога да дишам")

        assert result.safety.level == "emergency"
        assert result.safety.action == "call_emergency"
        assert "chest pain" in result.safety.detected_flags

    def test_caching_prevents_duplicate_inference(self, mock_processor):
        """Test that caching prevents duplicate LLM calls."""
        mock_processor._mock_generate.return_value = json.dumps({
            "intent": {"is_pharmacy_related": True, "confidence": 0.95, "rejection_reason": None},
            "safety": {"level": "safe", "detected_flags": [], "action": "proceed"},
            "extracted": {"symptoms": ["headache"], "user_conditions": [], "age_group": "adult", "query_translated": "headache"},
            "recommendation": {"treatment_category": "analgesics"},
        })

        # First call
        result1 = mock_processor.process("главоболие")
        assert result1.from_cache is False

        # Second call with same query should use cache
        result2 = mock_processor.process("главоболие")
        assert result2.from_cache is True

        # LLM should only be called once
        assert mock_processor._mock_generate.call_count == 1


# =============================================================================
# SAFETY INTEGRATION TESTS
# =============================================================================

class TestSafetyIntegration:
    """Tests for safety layer integration."""

    def test_hybrid_safety_keyword_wins(self):
        """Hard-coded keyword detection should take priority."""
        from src.safety import SafetyLayer

        safety = SafetyLayer()
        result = safety.check_safety_with_llm_result(
            text="болка в гърдите",  # Emergency keyword
            llm_safety_level="safe",  # LLM missed it
            llm_detected_flags=[],
        )

        # Hard-coded should catch it even if LLM missed
        assert result.severity == "emergency"

    def test_hybrid_safety_llm_augments(self):
        """LLM should catch things keywords miss."""
        from src.safety import SafetyLayer

        safety = SafetyLayer()
        result = safety.check_safety_with_llm_result(
            text="чувствам се много зле",  # Not a keyword match
            llm_safety_level="urgent",  # LLM detected concern
            llm_detected_flags=["severe distress"],
        )

        # LLM detection should be used
        assert result.severity == "urgent"
        assert result.is_red_flag is True

    def test_hybrid_safety_both_safe(self):
        """Both agreeing on safe should return safe."""
        from src.safety import SafetyLayer

        safety = SafetyLayer()
        result = safety.check_safety_with_llm_result(
            text="имам леко главоболие",
            llm_safety_level="safe",
            llm_detected_flags=[],
        )

        assert result.severity == "none"
        assert result.is_red_flag is False
