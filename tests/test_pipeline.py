"""
Integration tests for the Pipeline orchestration.

Tests the pipeline flow with mocked components to verify correct orchestration
without loading the actual ML models.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class MockMedicalReasoning:
    """Mock result from medical model."""
    symptoms: list
    likely_cause: str
    treatment_type: str
    see_doctor: bool = False
    red_flags: list = None
    warnings: list = None
    explanation: str = ""
    how_treatment_helps: str = ""
    self_care_tips: list = None
    duration_guidance: str = ""

    def __post_init__(self):
        if self.red_flags is None:
            self.red_flags = []
        if self.warnings is None:
            self.warnings = []
        if self.self_care_tips is None:
            self.self_care_tips = []


class MockTranslator:
    """Mock translator for testing."""
    def translate_to_english(self, text: str) -> str:
        return f"[EN] {text}"

    def translate_to_bulgarian(self, text: str) -> str:
        return f"[BG] {text}"

    def load_all(self):
        pass


class MockMedicalModel:
    """Mock medical model for testing."""
    def __init__(self):
        self._loaded = True

    def load(self):
        pass

    def get_medical_reasoning(self, symptoms: str) -> MockMedicalReasoning:
        return MockMedicalReasoning(
            symptoms=["headache", "fever"],
            likely_cause="viral infection",
            treatment_type="analgesic, antipyretic",
            see_doctor=False,
            warnings=["Consult doctor if symptoms persist"],
            explanation="Common viral symptoms",
            how_treatment_helps="Reduces pain and fever",
            self_care_tips=["Rest", "Stay hydrated"],
            duration_guidance="Usually resolves in 3-5 days"
        )

    def refine_product_selection(self, user_query, medical_reasoning, candidate_products, max_products=3):
        # Return first max_products from candidates
        return candidate_products[:max_products]


class MockProductStore:
    """Mock product store for testing."""
    def __init__(self):
        self.collection = Mock()
        self.collection.count.return_value = 100

    def search(self, query: str, n_results: int = 5):
        return [
            {
                "id": "prod_001",
                "title": "Парацетамол 500mg",
                "description": "Обезболяващо и антипиретик",
                "price_bgn": 5.99,
                "price_eur": 3.0,
                "category": "pain_relief",
                "is_otc": True,
                "url_handle": "paracetamol-500mg"
            },
            {
                "id": "prod_002",
                "title": "Ибупрофен 400mg",
                "description": "Противовъзпалително средство",
                "price_bgn": 7.99,
                "price_eur": 4.0,
                "category": "pain_relief",
                "is_otc": True,
                "url_handle": "ibuprofen-400mg"
            },
        ]


class MockIntentClassifier:
    """Mock intent classifier for testing."""
    def is_medical_query(self, query: str):
        # Check for known non-medical patterns
        non_medical = ["време", "weather", "виц", "joke", "новини"]
        for pattern in non_medical:
            if pattern in query.lower():
                return False, 0.9, "Non-medical query"
        return True, 0.9, "Medical query detected"

    def get_rejection_message(self, lang: str = "bg", reason: str = None):
        if lang == "bg":
            return "Съжалявам, мога да помагам само със здравни въпроси."
        return "Sorry, I can only help with health-related questions."


class MockSafetyLayer:
    """Mock safety layer for testing."""
    def check_safety(self, text: str):
        """Check for safety issues."""
        result = Mock()
        # Detect emergency keywords
        emergency_keywords = ["chest pain", "difficulty breathing", "болка в гърдите"]
        for keyword in emergency_keywords:
            if keyword in text.lower():
                result.is_red_flag = True
                result.message = "Seek immediate medical attention"
                return result
        result.is_red_flag = False
        result.message = ""
        return result

    def filter_otc_only(self, products: list) -> list:
        result = []
        for p in products:
            if isinstance(p, dict):
                if p.get("is_otc", True):
                    result.append(p)
            else:
                # Handle Product objects
                if getattr(p, "is_otc", True):
                    result.append(p)
        return result

    def add_safety_disclaimer(self, response: str, safety_result) -> str:
        return response


@pytest.fixture
def mock_pipeline():
    """Create a pipeline with all components mocked."""
    mock_translator = MockTranslator()
    mock_model = MockMedicalModel()
    mock_store = MockProductStore()
    mock_intent = MockIntentClassifier()
    mock_safety = MockSafetyLayer()

    with patch('src.pipeline.get_translator', return_value=mock_translator):
        with patch('src.pipeline.get_medical_model', return_value=mock_model):
            with patch('src.pipeline.get_product_store', return_value=mock_store):
                with patch('src.pipeline.get_intent_classifier', return_value=mock_intent):
                    with patch('src.pipeline.get_safety_layer', return_value=mock_safety):
                        # Clear the global pipeline instance
                        import src.pipeline as pipeline_module
                        pipeline_module._pipeline = None

                        from src.pipeline import Pipeline
                        pipeline = Pipeline()
                        yield pipeline


class TestPipelineInitialization:
    """Tests for pipeline initialization."""

    def test_pipeline_components_exist(self, mock_pipeline):
        """Pipeline should have all required components."""
        assert mock_pipeline.intent_classifier is not None
        assert mock_pipeline.safety_layer is not None

    def test_lazy_loading_works(self, mock_pipeline):
        """Components should be lazily loaded."""
        # Access translator to trigger lazy load
        translator = mock_pipeline.translator
        assert translator is not None


class TestPipelineFlow:
    """Tests for the complete pipeline flow."""

    def test_medical_query_flow(self, mock_pipeline):
        """Medical query should go through full pipeline."""
        result = mock_pipeline.process("Имам главоболие")

        # Should return a result with response
        assert result is not None
        assert hasattr(result, 'response')
        assert len(result.response) > 0
        assert result.is_medical is True

    def test_non_medical_query_rejected(self, mock_pipeline):
        """Non-medical query should be rejected early."""
        result = mock_pipeline.process("какво е времето")

        assert result is not None
        assert result.is_medical is False
        assert "здравни въпроси" in result.response or "medical" in result.response.lower()

    def test_empty_query_handled(self, mock_pipeline):
        """Empty query should be handled gracefully."""
        result = mock_pipeline.process("")

        assert result is not None
        # Empty query might be rejected or handled
        assert hasattr(result, 'response')


class TestPipelineResults:
    """Tests for pipeline result structure."""

    def test_result_has_required_fields(self, mock_pipeline):
        """Result should have all required fields."""
        result = mock_pipeline.process("болка в стомаха")

        assert hasattr(result, 'response')
        assert hasattr(result, 'is_medical')
        assert hasattr(result, 'is_red_flag')
        assert hasattr(result, 'original_text')
        assert hasattr(result, 'translated_text')

    def test_result_response_is_string(self, mock_pipeline):
        """Response should be a string."""
        result = mock_pipeline.process("имам температура")

        assert isinstance(result.response, str)

    def test_result_flags_are_boolean(self, mock_pipeline):
        """Flags should be boolean."""
        result = mock_pipeline.process("болка")

        assert isinstance(result.is_medical, bool)
        assert isinstance(result.is_red_flag, bool)

    def test_medical_result_has_products(self, mock_pipeline):
        """Medical query result should have product info."""
        result = mock_pipeline.process("имам главоболие")

        assert result.is_medical is True
        # Should have candidate and selected products
        assert hasattr(result, 'candidate_products')
        assert hasattr(result, 'selected_products')


class TestPipelineEdgeCases:
    """Tests for edge cases."""

    def test_unicode_input_handled(self, mock_pipeline):
        """Unicode Bulgarian input should be handled."""
        result = mock_pipeline.process("Имам силно главоболие и температура")

        assert result is not None
        assert hasattr(result, 'response')

    def test_mixed_language_input(self, mock_pipeline):
        """Mixed language input should be handled."""
        result = mock_pipeline.process("Имам headache и fever")

        assert result is not None

    def test_very_long_input(self, mock_pipeline):
        """Very long input should be handled."""
        long_input = "болка " * 100
        result = mock_pipeline.process(long_input)

        assert result is not None

    def test_special_characters(self, mock_pipeline):
        """Special characters should be handled."""
        result = mock_pipeline.process("болка!!! в стомаха??? (силна)")

        assert result is not None


class TestPipelineWithRealComponents:
    """Integration tests using real components (slower, requires models).

    These tests are marked as slow and can be skipped in CI.
    """

    @pytest.mark.slow
    def test_real_intent_classifier(self):
        """Test with real intent classifier."""
        from src.intent_classifier import IntentClassifier
        classifier = IntentClassifier()

        # Medical query
        is_medical, _, _ = classifier.is_medical_query("имам главоболие")
        assert is_medical

        # Non-medical query
        is_medical, _, _ = classifier.is_medical_query("какво е времето")
        assert not is_medical

    @pytest.mark.slow
    def test_real_safety_layer(self):
        """Test with real safety layer."""
        from src.safety import SafetyLayer
        safety = SafetyLayer()

        # Normal symptom
        result = safety.check_safety("headache")
        assert not result.is_red_flag

        # Emergency symptom
        result = safety.check_safety("chest pain difficulty breathing")
        assert result.is_red_flag
