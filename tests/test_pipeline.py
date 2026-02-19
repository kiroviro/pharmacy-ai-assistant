"""
Integration tests for the Pipeline orchestration.

Tests the pipeline flow with mocked components to verify correct orchestration
without loading the actual ML models.

Uses dependency injection instead of patching for cleaner, more maintainable tests.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

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

    def translate_symptom(self, symptom: str) -> str:
        """Translate a symptom to Bulgarian."""
        return f"[BG] {symptom}"

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
            duration_guidance="Usually resolves in 3-5 days",
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

    def check_safety_with_llm_result(self, text: str, llm_safety_level: str, llm_detected_flags: list):
        """Check safety with LLM result (hybrid approach)."""
        result = Mock()
        # Simple mock: trust LLM if it says emergency
        if llm_safety_level == "emergency":
            result.is_red_flag = True
            result.severity = "emergency"
            result.message = "Seek immediate medical attention"
            result.matched_symptoms = llm_detected_flags
        else:
            result.is_red_flag = False
            result.severity = "safe"
            result.message = ""
            result.matched_symptoms = []
        return result


@pytest.fixture
def mock_pipeline():
    """
    Create a pipeline with all components mocked using dependency injection.

    This is cleaner than patching - explicitly inject test doubles.
    """
    from src.pipeline.orchestrator import Pipeline
    from src.pipeline.response_builder import ResponseBuilder
    from src.medical_terms_validator import MedicalTermsValidator

    # Create mock components
    mock_translator = MockTranslator()
    mock_medical_model = MockMedicalModel()
    mock_product_store = MockProductStore()
    mock_safety_layer = MockSafetyLayer()

    # Create mock unified processor (UnifiedProcessor is complex, so we mock it)
    mock_unified_processor = Mock()
    mock_unified_processor.load = Mock()

    # Make process() smarter - detect non-medical queries
    def mock_process(query: str):
        query_lower = query.lower()
        # Detect non-medical queries
        non_medical_keywords = ["времето", "weather", "футбол", "football", "политика"]
        is_medical = not any(kw in query_lower for kw in non_medical_keywords)

        return _create_mock_unified_result(is_medical=is_medical)

    mock_unified_processor.process = mock_process

    # Create mock medical validator
    mock_validator = Mock(spec=MedicalTermsValidator)
    mock_validator.validate_and_correct = Mock(return_value=("validated text", []))

    # Create real ResponseBuilder (it's simple and doesn't need heavy dependencies)
    response_builder = ResponseBuilder()

    # Inject dependencies directly - no patching needed!
    pipeline = Pipeline(
        lazy_load=False,  # Load immediately for testing
        safety_layer=mock_safety_layer,
        medical_validator=mock_validator,
        response_builder=response_builder,
        product_store=mock_product_store,
        medical_model=mock_medical_model,
        translator=mock_translator,
        unified_processor=mock_unified_processor,
    )

    return pipeline


def _create_mock_unified_result(is_medical=True):
    """Helper to create a mock unified processor result."""
    # Use a simple Mock object instead of trying to match the complex dataclass structure
    result = Mock()

    # Intent
    result.intent = Mock()
    result.intent.is_pharmacy_related = is_medical
    result.intent.confidence = 0.9 if is_medical else 0.1
    result.intent.rejection_reason = "" if is_medical else "Not a medical query"

    # Extraction
    result.extraction = Mock()
    result.extraction.symptoms = ["главоболие"]
    result.extraction.user_conditions = []
    result.extraction.treatment_query = ""

    # Reasoning
    result.reasoning = Mock()
    result.reasoning.treatment_category = "analgesics"
    result.reasoning.recommended_products = ["paracetamol", "ibuprofen"]
    result.reasoning.explanation_bg = "Можете да вземете обезболяващо."
    result.reasoning.explanation = ""
    result.reasoning.self_care_tips_bg = []
    result.reasoning.self_care_tips = []
    result.reasoning.warnings_bg = []
    result.reasoning.warnings = []

    # Safety
    result.safety = Mock()
    result.safety.level = "safe"
    result.safety.severity_score = 0.1
    result.safety.detected_flags = []

    # Metadata
    result.processing_time_ms = 100.0
    result.from_cache = False
    result.raw_response = ""

    return result


class TestPipelineInitialization:
    """Tests for pipeline initialization."""

    def test_pipeline_components_exist(self, mock_pipeline):
        """Pipeline should have all required components."""
        assert mock_pipeline.safety_layer is not None
        assert mock_pipeline.unified_processor is not None

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
        assert hasattr(result, "response")
        assert len(result.response) > 0
        assert result.is_medical is True

    def test_non_medical_query_rejected(self, mock_pipeline):
        """Non-medical query should be rejected early."""
        result = mock_pipeline.process("какво е времето")

        assert result is not None
        assert result.is_medical is False
        # Rejection message varies, check for common health-related keywords
        assert "здрав" in result.response.lower() or "medical" in result.response.lower()

    def test_empty_query_handled(self, mock_pipeline):
        """Empty query should be handled gracefully."""
        result = mock_pipeline.process("")

        assert result is not None
        # Empty query might be rejected or handled
        assert hasattr(result, "response")


class TestPipelineResults:
    """Tests for pipeline result structure."""

    def test_result_has_required_fields(self, mock_pipeline):
        """Result should have all required fields."""
        result = mock_pipeline.process("болка в стомаха")

        assert hasattr(result, "response")
        assert hasattr(result, "is_medical")
        assert hasattr(result, "is_red_flag")
        assert hasattr(result, "original_text")
        assert hasattr(result, "translated_text")

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
        assert hasattr(result, "candidate_products")
        assert hasattr(result, "selected_products")


class TestPipelineEdgeCases:
    """Tests for edge cases."""

    def test_unicode_input_handled(self, mock_pipeline):
        """Unicode Bulgarian input should be handled."""
        result = mock_pipeline.process("Имам силно главоболие и температура")

        assert result is not None
        assert hasattr(result, "response")

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
        has_contra, matching = check_contraindication(contra_text, ["pregnancy", "diabetes", "heart"])

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

        safe, contraindicated = filter_by_contraindications(products, ["pregnancy", "diabetes"])

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
            contraindicated_products=[("product", ["pregnancy"])],
        )

        assert hasattr(result, "user_conditions")
        assert hasattr(result, "contraindicated_products")
        assert result.user_conditions == ["pregnancy"]
        assert len(result.contraindicated_products) == 1

    def test_result_defaults_to_empty_lists(self):
        """Contraindication fields should default to empty lists."""
        from src.pipeline import PipelineResult

        result = PipelineResult(response="Test")

        assert result.user_conditions == []
        assert result.contraindicated_products == []


class TestContraindicationWarningMessage:
    """Tests for contraindication warning messages.

    Note: As of recent refactor, contraindication warnings are now embedded
    in product card warnings and the safety block, not appended to responses.
    The _add_contraindication_warning method now returns the response unchanged.
    """

    def test_warning_includes_condition(self, mock_pipeline):
        """Contraindication warnings are now in product cards, not appended."""
        original = "Original response"
        response = mock_pipeline._add_contraindication_warning(
            original, [("MockProduct", ["pregnancy"])], ["pregnancy"]
        )

        # Method should return response unchanged (warnings are in product cards)
        assert response == original

    def test_warning_mentions_filtered_count(self, mock_pipeline):
        """Contraindication warnings are now in product cards, not appended."""
        original = "Original response"
        # Create mock tuples
        filtered = [
            (Mock(title="Product A"), ["pregnancy"]),
            (Mock(title="Product B"), ["pregnancy"]),
        ]

        response = mock_pipeline._add_contraindication_warning(original, filtered, ["pregnancy"])

        # Method should return response unchanged (warnings are in product cards)
        assert response == original

    def test_no_warning_when_no_contraindicated(self, mock_pipeline):
        """Should not add warning when no products filtered."""
        original = "Original response"
        response = mock_pipeline._add_contraindication_warning(original, [], ["pregnancy"])

        assert response == original

    def test_no_warning_when_no_conditions(self, mock_pipeline):
        """Should not add warning when no user conditions."""
        original = "Original response"
        filtered = [(Mock(title="Product A"), ["pregnancy"])]

        response = mock_pipeline._add_contraindication_warning(original, filtered, [])

        assert response == original
