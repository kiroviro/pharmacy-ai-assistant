"""
Integration tests for the Pipeline orchestration.

Tests the pipeline flow with mocked components to verify correct orchestration
without loading the actual ML models.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

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
    user_conditions: list = None

    def __post_init__(self):
        if self.red_flags is None:
            self.red_flags = []
        if self.warnings is None:
            self.warnings = []
        if self.self_care_tips is None:
            self.self_care_tips = []
        if self.user_conditions is None:
            self.user_conditions = []


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

    def _get_mock_products(self):
        return [
            {
                "id": "prod_001",
                "title": "Парацетамол 500mg",
                "description": "Обезболяващо и антипиретик",
                "price_bgn": 5.99,
                "price_eur": 3.0,
                "category": "pain_relief",
                "is_otc": True,
                "url_handle": "paracetamol-500mg",
                "contraindications": "",
                "brand": "Generic",
                "composition": "paracetamol 500mg",
            },
            {
                "id": "prod_002",
                "title": "Ибупрофен 400mg",
                "description": "Противовъзпалително средство",
                "price_bgn": 7.99,
                "price_eur": 4.0,
                "category": "pain_relief",
                "is_otc": True,
                "url_handle": "ibuprofen-400mg",
                "contraindications": "Не се препоръчва при бременност",
                "brand": "Generic",
                "composition": "ibuprofen 400mg",
            },
        ]

    def search(self, query: str, n_results: int = 5):
        return self._get_mock_products()[:n_results]

    def hybrid_search(self, query: str, n_results: int = 5, **kwargs):
        return self._get_mock_products()[:n_results]

    def search_by_category(self, query: str, treatment_type: str, n_results: int = 5):
        return self._get_mock_products()[:n_results]


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

    with patch('src.translator.get_translator', return_value=mock_translator):
        with patch('src.medical_model.get_medical_model', return_value=mock_model):
            with patch('src.product_store.get_product_store', return_value=mock_store):
                with patch('src.intent_classifier.get_intent_classifier', return_value=mock_intent):
                    with patch('src.safety.get_safety_layer', return_value=mock_safety):
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
        # Rejection message varies, check for common parts
        assert ("здравн" in result.response.lower() or "medical" in result.response.lower())

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


# =============================================================================
# CONTRAINDICATION FILTERING TESTS
# =============================================================================

class TestUserConditionExtraction:
    """Tests for extracting user conditions from query text."""

    def test_pregnancy_detection_bulgarian(self):
        """Should detect pregnancy mentions in Bulgarian."""
        from src.pipeline import extract_user_conditions

        conditions = extract_user_conditions("Бременна съм и ме боли главата")
        assert "pregnancy" in conditions

        conditions = extract_user_conditions("по време на бременност какво да взема")
        assert "pregnancy" in conditions

    def test_pregnancy_detection_english(self):
        """Should detect pregnancy mentions in English."""
        from src.pipeline import extract_user_conditions

        conditions = extract_user_conditions("I am pregnant and have a headache")
        assert "pregnancy" in conditions

    def test_breastfeeding_detection(self):
        """Should detect breastfeeding mentions."""
        from src.pipeline import extract_user_conditions

        conditions = extract_user_conditions("Кърмя и ме боли гърлото")
        assert "breastfeeding" in conditions

        conditions = extract_user_conditions("Кърмене - какво мога да взема")
        assert "breastfeeding" in conditions

    def test_child_detection_bulgarian(self):
        """Should detect child/baby mentions in Bulgarian."""
        from src.pipeline import extract_user_conditions

        conditions = extract_user_conditions("Детето ми има температура")
        assert "child" in conditions

        conditions = extract_user_conditions("Бебето има кашлица")
        assert "child" in conditions

    def test_child_detection_with_age(self):
        """Should detect age patterns indicating children."""
        from src.pipeline import extract_user_conditions

        conditions = extract_user_conditions("Дете на 3 години има хрема")
        assert "child" in conditions

    def test_diabetes_detection(self):
        """Should detect diabetes mentions."""
        from src.pipeline import extract_user_conditions

        conditions = extract_user_conditions("Имам диабет, какво да взема за болка")
        assert "diabetes" in conditions

        conditions = extract_user_conditions("Диабетик съм и ме боли главата")
        assert "diabetes" in conditions

    def test_heart_condition_detection(self):
        """Should detect heart condition mentions."""
        from src.pipeline import extract_user_conditions

        conditions = extract_user_conditions("Имам проблеми със сърцето")
        assert "heart" in conditions

        conditions = extract_user_conditions("Страдам от хипертония")
        assert "heart" in conditions

    def test_multiple_conditions(self):
        """Should detect multiple conditions in one query."""
        from src.pipeline import extract_user_conditions

        conditions = extract_user_conditions("Бременна съм и имам диабет")
        assert "pregnancy" in conditions
        assert "diabetes" in conditions

    def test_no_conditions(self):
        """Should return empty list when no conditions detected."""
        from src.pipeline import extract_user_conditions

        conditions = extract_user_conditions("Имам главоболие")
        assert conditions == []

    def test_allergy_detection(self):
        """Should detect allergy mentions."""
        from src.pipeline import extract_user_conditions

        conditions = extract_user_conditions("Имам алергия към аспирин")
        assert "allergy" in conditions

    def test_stomach_issues_detection(self):
        """Should detect stomach/GI condition mentions."""
        from src.pipeline import extract_user_conditions

        conditions = extract_user_conditions("Имам гастрит, какво да взема")
        assert "stomach" in conditions

        conditions = extract_user_conditions("Страдам от стомашна язва")
        assert "stomach" in conditions


class TestContraindicationCheck:
    """Tests for checking product contraindications."""

    def test_pregnancy_contraindication_match(self):
        """Should detect pregnancy contraindication in product."""
        from src.pipeline import check_contraindication

        contra_text = "Не се препоръчва по време на бременност и кърмене"
        has_contra, matching = check_contraindication(contra_text, ["pregnancy"])

        assert has_contra is True
        assert "pregnancy" in matching

    def test_no_contraindication(self):
        """Should return False when no matching contraindication."""
        from src.pipeline import check_contraindication

        contra_text = "Може да се приема от възрастни"
        has_contra, matching = check_contraindication(contra_text, ["pregnancy"])

        assert has_contra is False
        assert matching == []

    def test_empty_contraindications(self):
        """Should handle empty contraindications text."""
        from src.pipeline import check_contraindication

        has_contra, matching = check_contraindication("", ["pregnancy"])
        assert has_contra is False

        has_contra, matching = check_contraindication(None, ["pregnancy"])
        assert has_contra is False

    def test_empty_conditions(self):
        """Should handle empty user conditions."""
        from src.pipeline import check_contraindication

        has_contra, matching = check_contraindication("Some text", [])
        assert has_contra is False

    def test_multiple_matching_conditions(self):
        """Should detect multiple matching contraindications."""
        from src.pipeline import check_contraindication

        contra_text = "Не се препоръчва при бременност, диабет или сърдечни заболявания"
        has_contra, matching = check_contraindication(
            contra_text, ["pregnancy", "diabetes", "heart"]
        )

        assert has_contra is True
        assert len(matching) >= 2

    def test_child_age_contraindication(self):
        """Should detect child age restrictions."""
        from src.pipeline import check_contraindication

        contra_text = "Не давайте на деца под 12 години"
        has_contra, matching = check_contraindication(contra_text, ["child"])

        assert has_contra is True
        assert "child" in matching


class TestContraindicationFiltering:
    """Tests for filtering products by contraindications."""

    @dataclass
    class MockProduct:
        """Mock product for testing."""
        id: str
        title: str
        contraindications: str
        is_otc: bool = True

    def test_filter_removes_contraindicated(self):
        """Should remove products with matching contraindications."""
        from src.pipeline import filter_by_contraindications

        products = [
            self.MockProduct("1", "Product A", "Не се препоръчва при бременност"),
            self.MockProduct("2", "Product B", "Подходящ за всички възрастни"),
            self.MockProduct("3", "Product C", "Не давайте по време на бременност"),
        ]

        safe, contraindicated = filter_by_contraindications(products, ["pregnancy"])

        assert len(safe) == 1
        assert safe[0].id == "2"
        assert len(contraindicated) == 2

    def test_filter_no_conditions(self):
        """Should return all products when no conditions specified."""
        from src.pipeline import filter_by_contraindications

        products = [
            self.MockProduct("1", "Product A", "Не се препоръчва при бременност"),
            self.MockProduct("2", "Product B", "Подходящ за всички"),
        ]

        safe, contraindicated = filter_by_contraindications(products, [])

        assert len(safe) == 2
        assert len(contraindicated) == 0

    def test_filter_empty_products(self):
        """Should handle empty product list."""
        from src.pipeline import filter_by_contraindications

        safe, contraindicated = filter_by_contraindications([], ["pregnancy"])

        assert safe == []
        assert contraindicated == []

    def test_contraindicated_includes_reason(self):
        """Contraindicated products should include matching conditions."""
        from src.pipeline import filter_by_contraindications

        products = [
            self.MockProduct("1", "Product A", "Противопоказан при диабет и бременност"),
        ]

        safe, contraindicated = filter_by_contraindications(
            products, ["pregnancy", "diabetes"]
        )

        assert len(contraindicated) == 1
        product, matching_conditions = contraindicated[0]
        assert "pregnancy" in matching_conditions or "diabetes" in matching_conditions


class TestPipelineResultWithContraindications:
    """Tests for PipelineResult with contraindication fields."""

    def test_result_has_contraindication_fields(self):
        """PipelineResult should have contraindication-related fields."""
        from src.pipeline import PipelineResult

        result = PipelineResult(
            response="Test response",
            user_conditions=["pregnancy"],
            contraindicated_products=[("product", ["pregnancy"])]
        )

        assert hasattr(result, 'user_conditions')
        assert hasattr(result, 'contraindicated_products')
        assert result.user_conditions == ["pregnancy"]
        assert len(result.contraindicated_products) == 1

    def test_result_defaults_to_empty_lists(self):
        """Contraindication fields should default to empty lists."""
        from src.pipeline import PipelineResult

        result = PipelineResult(response="Test")

        assert result.user_conditions == []
        assert result.contraindicated_products == []


class TestContraindicationWarningMessage:
    """Tests for contraindication warning messages."""

    def test_warning_includes_condition(self, mock_pipeline):
        """Warning should mention the user's condition."""
        response = mock_pipeline._add_contraindication_warning(
            "Original response",
            [("MockProduct", ["pregnancy"])],
            ["pregnancy"]
        )

        assert "бременност" in response.lower()

    def test_warning_mentions_filtered_count(self, mock_pipeline):
        """Warning should mention number of filtered products."""
        # Create mock tuples
        filtered = [
            (Mock(title="Product A"), ["pregnancy"]),
            (Mock(title="Product B"), ["pregnancy"]),
        ]

        response = mock_pipeline._add_contraindication_warning(
            "Original response",
            filtered,
            ["pregnancy"]
        )

        assert "2" in response

    def test_no_warning_when_no_contraindicated(self, mock_pipeline):
        """Should not add warning when no products filtered."""
        original = "Original response"
        response = mock_pipeline._add_contraindication_warning(
            original, [], ["pregnancy"]
        )

        assert response == original

    def test_no_warning_when_no_conditions(self, mock_pipeline):
        """Should not add warning when no user conditions."""
        original = "Original response"
        filtered = [(Mock(title="Product A"), ["pregnancy"])]

        response = mock_pipeline._add_contraindication_warning(
            original, filtered, []
        )

        assert response == original
