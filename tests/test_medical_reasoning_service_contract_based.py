"""
Contract-based tests for MedicalReasoningService.

Tests focus on behavior rather than implementation details.
"""

import pytest

from src.medical_model import MedicalReasoning
from src.services.medical_reasoning_service import MedicalReasoningService


# =========================================================================
# Mock Classes
# =========================================================================


class MockMedicalModel:
    """Mock medical model for testing."""

    def __init__(self, return_reasoning=None, raise_error=False):
        self.return_reasoning = return_reasoning
        self.raise_error = raise_error

    def get_medical_reasoning(self, text: str) -> MedicalReasoning:
        """Simulate medical model reasoning."""
        if self.raise_error:
            raise Exception("Model error")

        if self.return_reasoning:
            return self.return_reasoning

        # Default mock reasoning
        return MedicalReasoning(
            symptoms=["headache"],
            likely_cause="tension",
            treatment_type="analgesics",
            warnings=[],
            see_doctor=False,
        )


# =========================================================================
# Test Fixtures
# =========================================================================


@pytest.fixture
def service():
    """Create MedicalReasoningService instance."""
    return MedicalReasoningService()


@pytest.fixture
def service_with_model():
    """Create MedicalReasoningService with mock model."""
    mock_model = MockMedicalModel()
    return MedicalReasoningService(medical_model=mock_model)


# =========================================================================
# Contract-Based Tests for get_medical_reasoning
# =========================================================================


class TestGetMedicalReasoningContract:
    """Contract-based tests for get_medical_reasoning method."""

    def test_returns_valid_medical_reasoning(self, service_with_model):
        """Test that get_medical_reasoning returns valid MedicalReasoning (contract)."""
        result = service_with_model.get_medical_reasoning("главоболие")

        # Contract: must return MedicalReasoning object
        assert isinstance(result, MedicalReasoning), "Must return MedicalReasoning object"
        assert hasattr(result, "symptoms"), "Must have symptoms field"
        assert hasattr(result, "treatment_type"), "Must have treatment_type field"

    def test_fallback_on_model_error(self):
        """Test fallback behavior when model fails (contract)."""
        mock_model = MockMedicalModel(raise_error=True)
        service = MedicalReasoningService(medical_model=mock_model)

        result = service.get_medical_reasoning("температура")

        # Contract: must return fallback reasoning on error
        assert isinstance(result, MedicalReasoning), "Must return MedicalReasoning even on error"
        assert len(result.warnings) > 0, "Fallback should include warnings"

    def test_handles_no_model(self, service):
        """Test behavior when no model is available (contract)."""
        result = service.get_medical_reasoning("кашлица")

        # Contract: must return fallback reasoning when no model
        assert isinstance(result, MedicalReasoning), "Must return MedicalReasoning without model"
        assert result.symptoms, "Must have some symptoms"


# =========================================================================
# Contract-Based Tests for create_fallback_reasoning
# =========================================================================


class TestCreateFallbackReasoningContract:
    """Contract-based tests for create_fallback_reasoning method."""

    def test_returns_valid_fallback_reasoning(self, service):
        """Test that fallback reasoning is valid (contract)."""
        result = service.create_fallback_reasoning("главоболие")

        # Contract: must return safe, conservative reasoning
        assert isinstance(result, MedicalReasoning), "Must return MedicalReasoning"
        assert len(result.symptoms) > 0, "Must have at least one symptom"
        assert len(result.warnings) > 0, "Must include warnings"
        assert result.see_doctor is False, "Fallback should not require doctor"

    def test_detects_common_symptoms(self, service):
        """Test that fallback detects common symptom keywords (contract)."""
        test_cases = [
            ("главоболие", "headache"),
            ("температура", "fever"),
            ("кашлица", "cough"),
        ]

        for input_text, expected_symptom in test_cases:
            result = service.create_fallback_reasoning(input_text)

            # Contract: should detect basic symptoms
            symptoms_lower = [s.lower() for s in result.symptoms]
            assert any(expected_symptom in s for s in symptoms_lower), \
                f"Should detect '{expected_symptom}' from '{input_text}'"


# =========================================================================
# Contract-Based Tests for Query Classification
# =========================================================================


class TestQueryClassificationContract:
    """Contract-based tests for query classification methods."""

    def test_is_pregnancy_related_query_detects_pregnancy(self, service):
        """Test pregnancy query detection (contract behavior)."""
        # Contract: should detect pregnancy-related keywords
        pregnancy_queries = [
            "бременна съм",
            "кърмене",
            "pregnancy",
            "breastfeeding",
        ]

        # Note: Without user_condition_patterns, service won't detect these
        # This tests the contract behavior when patterns are provided
        service_with_patterns = MedicalReasoningService(
            user_condition_patterns={
                "pregnancy": ["бременна", "pregnancy"],
                "breastfeeding": ["кърмене", "breastfeeding"]
            }
        )

        for query in pregnancy_queries:
            assert service_with_patterns.is_pregnancy_related_query(query), \
                f"Should detect '{query}' as pregnancy-related"

    def test_is_drug_combination_query_detects_combinations(self, service):
        """Test drug combination query detection (contract behavior)."""
        # Contract: should detect drug combination keywords
        combination_queries = [
            "може ли да взема ибупрофен с парацетамол",
            "can I take ibuprofen with paracetamol",
            "заедно с",
            "together with",
        ]

        for query in combination_queries:
            assert service.is_drug_combination_query(query), \
                f"Should detect '{query}' as drug combination query"

    def test_is_drug_combination_query_negative_cases(self, service):
        """Test that non-combination queries are not flagged (contract behavior)."""
        non_combination_queries = [
            "главоболие",
            "температура",
            "headache",
        ]

        for query in non_combination_queries:
            assert not service.is_drug_combination_query(query), \
                f"Should not detect '{query}' as drug combination query"

    def test_is_substitute_query_detects_substitutes(self, service):
        """Test substitute query detection (contract behavior)."""
        # Contract: should detect substitute/alternative keywords
        substitute_queries = [
            "заместител на аспирин",
            "алтернатива на ибупрофен",
            "substitute for",
            "generic for",
            "alternative to",
        ]

        for query in substitute_queries:
            assert service.is_substitute_query(query), \
                f"Should detect '{query}' as substitute query"

    def test_is_substitute_query_negative_cases(self, service):
        """Test that regular queries are not flagged as substitute (contract behavior)."""
        regular_queries = [
            "главоболие",
            "temperature",
            "кашлица",
        ]

        for query in regular_queries:
            assert not service.is_substitute_query(query), \
                f"Should not detect '{query}' as substitute query"


# =========================================================================
# Contract-Based Tests for Symptom Validation
# =========================================================================


class TestSymptomValidationContract:
    """Contract-based tests for symptom validation methods."""

    def test_validate_symptoms_against_query_filters_phantom_symptoms(self, service):
        """Test that phantom symptoms are filtered (contract)."""
        # Query with no symptom keywords
        query = "помощ"
        symptoms = ["headache", "fever", "cough"]

        filtered = service.validate_symptoms_against_query(symptoms, query)

        # Contract: should filter out phantom symptoms
        assert len(filtered) == 0, "Should filter phantom symptoms when query has no keywords"

    def test_validate_symptoms_against_query_keeps_valid_symptoms(self, service):
        """Test that valid symptoms are kept (contract)."""
        # Query with symptom keywords
        query = "главоболие и температура"
        symptoms = ["headache", "fever"]

        filtered = service.validate_symptoms_against_query(symptoms, query)

        # Contract: should keep valid symptoms
        assert len(filtered) == len(symptoms), "Should keep symptoms when query has keywords"

    def test_query_has_symptom_keywords_detects_keywords(self, service):
        """Test symptom keyword detection (contract)."""
        queries_with_symptoms = [
            "главоболие",
            "температура",
            "кашлица",
            "болка в стомаха",
        ]

        for query in queries_with_symptoms:
            assert service.query_has_symptom_keywords(query), \
                f"Should detect symptom keywords in '{query}'"

    def test_query_has_symptom_keywords_negative_cases(self, service):
        """Test that queries without symptoms are not flagged (contract)."""
        queries_without_symptoms = [
            "помощ",
            "здравей",
            "благодаря",
        ]

        for query in queries_without_symptoms:
            assert not service.query_has_symptom_keywords(query), \
                f"Should not detect symptom keywords in '{query}'"


# =========================================================================
# Contract-Based Tests for Treatment Extraction
# =========================================================================


class TestTreatmentExtractionContract:
    """Contract-based tests for treatment extraction methods."""

    def test_extract_treatment_from_query_finds_treatment(self, service):
        """Test treatment extraction from query (contract)."""
        test_cases = [
            ("главоболие", "analgesics"),
            ("температура", "antipyretics"),
            ("кашлица", "cough"),
            ("диария", "antidiarrheal"),
        ]

        for query, expected_treatment in test_cases:
            result = service.extract_treatment_from_query(query)

            # Contract: should extract correct treatment type
            assert result == expected_treatment, \
                f"Should extract '{expected_treatment}' from '{query}'"

    def test_extract_treatment_from_query_returns_none_for_no_match(self, service):
        """Test treatment extraction with no matches (contract)."""
        result = service.extract_treatment_from_query("помощ")

        # Contract: should return None when no treatment found
        assert result is None, "Should return None when no treatment keywords found"

    def test_get_recommended_ingredients_returns_list(self, service):
        """Test that recommended ingredients returns list (contract)."""
        result = service.get_recommended_ingredients("analgesics")

        # Contract: must return list of ingredients
        assert isinstance(result, list), "Must return list of ingredients"

    def test_get_treatment_action_text_returns_bulgarian_text(self, service):
        """Test that treatment action text returns Bulgarian text (contract)."""
        result = service.get_treatment_action_text("analgesics")

        # Contract: must return non-empty Bulgarian text
        assert isinstance(result, str), "Must return string"
        assert len(result) > 0, "Must return non-empty text for known treatments"

    def test_get_treatment_action_text_handles_unknown_treatment(self, service):
        """Test handling of unknown treatment types (contract)."""
        result = service.get_treatment_action_text("unknown_treatment")

        # Contract: must return empty string for unknown treatments
        assert result == "", "Should return empty string for unknown treatment"


# =========================================================================
# Contract-Based Tests for is_refusal_response
# =========================================================================


class TestIsRefusalResponseContract:
    """Contract-based tests for is_refusal_response method."""

    def test_detects_refusal_responses(self, service):
        """Test refusal response detection (contract)."""
        refusal_reasoning = MedicalReasoning(
            symptoms=[],
            likely_cause="",
            treatment_type="",
            warnings=[],
            see_doctor=True,
            explanation="I cannot provide medical advice for this condition. Please see a doctor.",
        )

        result = service.is_refusal_response(refusal_reasoning)

        # Contract: should detect refusal
        assert result is True, "Should detect refusal response"

    def test_does_not_flag_normal_responses(self, service):
        """Test that normal responses are not flagged as refusals (contract)."""
        normal_reasoning = MedicalReasoning(
            symptoms=["headache"],
            likely_cause="tension",
            treatment_type="analgesics",
            warnings=[],
            see_doctor=False,
            explanation="You may have a tension headache. Over-the-counter pain relievers can help.",
        )

        result = service.is_refusal_response(normal_reasoning)

        # Contract: should not flag normal response as refusal
        assert result is False, "Should not flag normal response as refusal"
