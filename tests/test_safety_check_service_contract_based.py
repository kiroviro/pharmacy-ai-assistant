"""
Contract-based tests for SafetyCheckService.

Tests focus on behavior rather than implementation details.
"""

import pytest

from src.medical_model import MedicalReasoning
from src.services.safety_check_service import SafetyCheckService
from tests.contracts import MedicalReasoningBuilder


# =========================================================================
# Mock Classes
# =========================================================================


class MockSafetyLayer:
    """Mock safety layer for testing."""

    def __init__(self, is_red_flag=False, message=""):
        self.is_red_flag_value = is_red_flag
        self.message_value = message

    def check_safety(self, text):
        """Simulate safety check."""
        from dataclasses import dataclass

        @dataclass
        class SafetyResult:
            is_red_flag: bool
            message: str

        return SafetyResult(is_red_flag=self.is_red_flag_value, message=self.message_value)


class MockSafetyValidator:
    """Mock safety validator for testing."""

    def is_child_related_query(self, text):
        """Simulate child query detection."""
        child_keywords = ["дете", "бебе", "child", "baby", "деца"]
        return any(kw in text.lower() for kw in child_keywords)


class MockMedicalReasoningService:
    """Mock medical reasoning service for testing."""

    def is_pregnancy_related_query(self, text):
        """Simulate pregnancy query detection."""
        pregnancy_keywords = ["бременна", "кърмене", "pregnancy", "breastfeeding"]
        return any(kw in text.lower() for kw in pregnancy_keywords)

    def is_drug_combination_query(self, text):
        """Simulate drug combination detection."""
        combination_keywords = ["заедно с", "together with"]
        return any(kw in text.lower() for kw in combination_keywords)

    def is_substitute_query(self, text):
        """Simulate substitute query detection."""
        substitute_keywords = ["заместител", "алтернатива", "substitute", "alternative"]
        return any(kw in text.lower() for kw in substitute_keywords)


# =========================================================================
# Test Fixtures
# =========================================================================


@pytest.fixture
def service():
    """Create SafetyCheckService instance."""
    return SafetyCheckService()


@pytest.fixture
def service_with_mocks():
    """Create SafetyCheckService with mocks."""
    return SafetyCheckService(
        safety_layer=MockSafetyLayer(),
        safety_validator=MockSafetyValidator(),
        medical_reasoning_service=MockMedicalReasoningService(),
    )


# =========================================================================
# Contract-Based Tests for check_safety
# =========================================================================


class TestCheckSafetyContract:
    """Contract-based tests for check_safety method."""

    def test_returns_tuple_of_bool_and_string(self, service_with_mocks):
        """Test that check_safety returns (bool, str) tuple (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["headache"])
            .with_treatment_type("analgesics")
            .with_see_doctor(False)
            .build()
        )

        is_red_flag, message = service_with_mocks.check_safety(
            "главоболие", "headache", reasoning
        )

        # Contract: must return (bool, str) tuple
        assert isinstance(is_red_flag, bool), "First element must be bool"
        assert isinstance(message, str), "Second element must be str"

    def test_detects_red_flag_in_original_query(self):
        """Test red flag detection in original query (contract)."""
        safety_layer = MockSafetyLayer(is_red_flag=True, message="Emergency!")
        service = SafetyCheckService(safety_layer=safety_layer)

        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["chest pain"])
            .with_see_doctor(False)
            .build()
        )

        is_red_flag, message = service.check_safety(
            "гръдна болка", "chest pain", reasoning
        )

        # Contract: should detect red flag
        assert is_red_flag is True, "Should detect red flag"
        assert len(message) > 0, "Should return safety message"

    def test_continues_for_child_query_with_see_doctor(self, service_with_mocks):
        """Test that child queries continue even with see_doctor=True (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["fever"])
            .with_see_doctor(True)
            .build()
        )

        is_red_flag, message = service_with_mocks.check_safety(
            "температура при дете", "fever in child", reasoning
        )

        # Contract: child queries should not block
        assert is_red_flag is False, "Child queries should not block"
        assert message == "", "Should not return blocking message for child queries"

    def test_continues_for_pregnancy_query_with_see_doctor(self, service_with_mocks):
        """Test that pregnancy queries continue with see_doctor=True (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["nausea"])
            .with_see_doctor(True)
            .build()
        )

        is_red_flag, message = service_with_mocks.check_safety(
            "бременна съм", "I am pregnant", reasoning
        )

        # Contract: pregnancy queries should not block
        assert is_red_flag is False, "Pregnancy queries should not block"
        assert message == "", "Should not return blocking message for pregnancy queries"

    def test_continues_for_drug_combination_query(self, service_with_mocks):
        """Test that drug combination queries continue (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["drug interaction query"])
            .with_see_doctor(True)
            .build()
        )

        is_red_flag, message = service_with_mocks.check_safety(
            "може ли да взема ибупрофен заедно с парацетамол",
            "can I take ibuprofen together with paracetamol",
            reasoning,
        )

        # Contract: drug combination queries should not block
        assert is_red_flag is False, "Drug combination queries should not block"
        assert message == "", "Should not return blocking message for drug combinations"

    def test_continues_for_substitute_query(self, service_with_mocks):
        """Test that substitute queries continue (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["substitute query"])
            .with_see_doctor(True)
            .build()
        )

        is_red_flag, message = service_with_mocks.check_safety(
            "заместител на аспирин", "substitute for aspirin", reasoning
        )

        # Contract: substitute queries should not block
        assert is_red_flag is False, "Substitute queries should not block"
        assert message == "", "Should not return blocking message for substitutes"

    def test_blocks_for_generic_see_doctor(self, service_with_mocks):
        """Test that generic see_doctor=True blocks (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["severe pain"])
            .with_see_doctor(True)
            .build()
        )

        is_red_flag, message = service_with_mocks.check_safety(
            "силна болка", "severe pain", reasoning
        )

        # Contract: generic see_doctor should block
        assert is_red_flag is True, "Generic see_doctor should block"
        assert len(message) > 0, "Should return doctor recommendation message"
        assert "лекар" in message.lower(), "Message should mention doctor"

    def test_handles_no_safety_layer_gracefully(self, service):
        """Test graceful handling when no safety layer available (contract)."""
        reasoning = (
            MedicalReasoningBuilder()
            .with_symptoms(["headache"])
            .with_see_doctor(False)
            .build()
        )

        is_red_flag, message = service.check_safety("главоболие", "headache", reasoning)

        # Contract: should return safe values without safety layer
        assert is_red_flag is False, "Should not block without safety layer"
        assert message == "", "Should return empty message without safety layer"


# =========================================================================
# Contract-Based Tests for Query Classification
# =========================================================================


class TestQueryClassificationContract:
    """Contract-based tests for query classification methods."""

    def test_is_child_query_detects_child_keywords(self, service_with_mocks):
        """Test child query detection (contract)."""
        child_queries = [
            "температура при дете",
            "fever in child",
            "болка при бебе",
        ]

        for query in child_queries:
            assert service_with_mocks.is_child_query(query), \
                f"Should detect '{query}' as child query"

    def test_is_child_query_with_fallback(self, service):
        """Test child query detection with fallback logic (contract)."""
        # Without safety_validator, should use fallback
        assert service.is_child_query("дете с температура"), \
            "Fallback should detect child keyword"
        assert not service.is_child_query("главоболие"), \
            "Fallback should not flag non-child query"

    def test_is_pregnancy_query_detects_pregnancy_keywords(self, service_with_mocks):
        """Test pregnancy query detection (contract)."""
        pregnancy_queries = [
            "бременна съм",
            "pregnancy safe medications",
            "кърмене",
        ]

        for query in pregnancy_queries:
            assert service_with_mocks.is_pregnancy_query(query), \
                f"Should detect '{query}' as pregnancy query"

    def test_is_pregnancy_query_with_fallback(self, service):
        """Test pregnancy query detection with fallback logic (contract)."""
        assert service.is_pregnancy_query("бременна съм"), \
            "Fallback should detect pregnancy keyword"
        assert not service.is_pregnancy_query("главоболие"), \
            "Fallback should not flag non-pregnancy query"

    def test_is_drug_combination_query_detects_combinations(self, service_with_mocks):
        """Test drug combination detection (contract)."""
        combination_queries = [
            "може ли да взема ибупрофен заедно с парацетамол",
            "can I take ibuprofen together with paracetamol",
        ]

        for query in combination_queries:
            assert service_with_mocks.is_drug_combination_query(query), \
                f"Should detect '{query}' as combination query"

    def test_is_substitute_query_detects_substitutes(self, service_with_mocks):
        """Test substitute query detection (contract)."""
        substitute_queries = [
            "заместител на аспирин",
            "substitute for aspirin",
            "алтернатива на ибупрофен",
        ]

        for query in substitute_queries:
            assert service_with_mocks.is_substitute_query(query), \
                f"Should detect '{query}' as substitute query"


# =========================================================================
# Contract-Based Tests for Condition Translation
# =========================================================================


class TestConditionTranslationContract:
    """Contract-based tests for condition translation."""

    def test_get_condition_name_bulgarian_returns_translation(self, service):
        """Test Bulgarian condition name translation (contract)."""
        translations = [
            ("pregnancy", "бременност"),
            ("diabetes", "диабет"),
            ("heart", "сърдечни заболявания"),
        ]

        for key, expected_bg in translations:
            result = service.get_condition_name_bulgarian(key)

            # Contract: should return Bulgarian translation
            assert result == expected_bg, \
                f"Should translate '{key}' to '{expected_bg}'"

    def test_get_condition_name_bulgarian_returns_key_for_unknown(self, service):
        """Test fallback for unknown condition keys (contract)."""
        result = service.get_condition_name_bulgarian("unknown_condition")

        # Contract: should return original key for unknown conditions
        assert result == "unknown_condition", \
            "Should return original key for unknown condition"


# =========================================================================
# Contract-Based Tests for add_contraindication_warning
# =========================================================================


class TestAddContraindicationWarningContract:
    """Contract-based tests for add_contraindication_warning method."""

    def test_returns_unchanged_response(self, service):
        """Test that warning method returns unchanged response (contract)."""
        response = "Test response"
        contraindicated = [("product1", "pregnancy")]
        conditions = ["pregnancy"]

        result = service.add_contraindication_warning(response, contraindicated, conditions)

        # Contract: currently returns unchanged response (warnings in template)
        assert result == response, \
            "Should return unchanged response (warnings handled in template)"

    def test_handles_empty_contraindications(self, service):
        """Test handling of empty contraindications (contract)."""
        response = "Test response"

        result = service.add_contraindication_warning(response, [], [])

        # Contract: should handle empty lists gracefully
        assert result == response, "Should handle empty contraindications"
