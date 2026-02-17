"""
Unit tests for the Safety Layer.

These tests are CRITICAL - the safety layer must never miss emergency symptoms.
Target: 100% detection rate for emergency symptoms.
"""

from src.safety import SafetyCheckResult


class TestEmergencyDetection:
    """Tests for emergency symptom detection - MUST have 100% accuracy."""

    def test_emergency_symptoms_bulgarian(self, safety_layer, emergency_symptoms_bg):
        """All Bulgarian emergency symptoms must be detected."""
        for symptom in emergency_symptoms_bg:
            result = safety_layer.check_safety(symptom)
            assert result.is_red_flag, f"FAILED to detect emergency: '{symptom}'"
            assert result.severity == "emergency", f"Wrong severity for: '{symptom}'"
            assert result.should_refer_to_doctor, f"Should refer to doctor: '{symptom}'"

    def test_emergency_symptoms_english(self, safety_layer, emergency_symptoms_en):
        """All English emergency symptoms must be detected."""
        for symptom in emergency_symptoms_en:
            result = safety_layer.check_safety(symptom)
            assert result.is_red_flag, f"FAILED to detect emergency: '{symptom}'"
            assert result.severity == "emergency", f"Wrong severity for: '{symptom}'"
            assert result.should_refer_to_doctor, f"Should refer to doctor: '{symptom}'"

    def test_emergency_in_longer_text_bg(self, safety_layer):
        """Emergency symptoms must be detected even in longer text."""
        texts = [
            "Днес се чувствам зле и имам болка в гърдите",
            "Не мога да дишам добре от сутринта",
            "Имах гърч преди малко и съм много уплашен",
            "Имам суицидни мисли и не знам какво да правя",
        ]
        for text in texts:
            result = safety_layer.check_safety(text)
            assert result.is_red_flag, f"FAILED to detect emergency in: '{text}'"
            assert result.severity == "emergency"

    def test_emergency_message_is_bulgarian(self, safety_layer):
        """Emergency message should be in Bulgarian."""
        result = safety_layer.check_safety("болка в гърдите")
        assert "СПЕШНО" in result.message or "спешно" in result.message.lower()
        assert "112" in result.message


class TestUrgentDetection:
    """Tests for urgent symptom detection."""

    def test_urgent_symptoms_bulgarian(self, safety_layer, urgent_symptoms_bg):
        """Bulgarian urgent symptoms must be detected."""
        for symptom in urgent_symptoms_bg:
            result = safety_layer.check_safety(symptom)
            assert result.is_red_flag, f"FAILED to detect urgent: '{symptom}'"
            assert result.severity == "urgent", f"Wrong severity for: '{symptom}'"
            assert result.should_refer_to_doctor

    def test_urgent_symptoms_english(self, safety_layer, urgent_symptoms_en):
        """English urgent symptoms must be detected."""
        for symptom in urgent_symptoms_en:
            result = safety_layer.check_safety(symptom)
            assert result.is_red_flag, f"FAILED to detect urgent: '{symptom}'"
            assert result.severity == "urgent", f"Wrong severity for: '{symptom}'"

    def test_urgent_message_recommends_doctor(self, safety_layer):
        """Urgent message should recommend seeing a doctor."""
        result = safety_layer.check_safety("кръв в урината")
        assert "лекар" in result.message.lower()


class TestNoFalsePositives:
    """Tests to ensure normal queries don't trigger false positives."""

    def test_normal_queries_no_red_flag_bg(self, safety_layer, normal_medical_queries_bg):
        """Normal Bulgarian medical queries should NOT trigger red flags."""
        for query in normal_medical_queries_bg:
            result = safety_layer.check_safety(query)
            assert not result.is_red_flag, f"False positive for: '{query}'"
            assert result.severity in ["none", "warning"], f"Wrong severity for: '{query}'"

    def test_normal_queries_no_red_flag_en(self, safety_layer, normal_medical_queries_en):
        """Normal English medical queries should NOT trigger red flags."""
        for query in normal_medical_queries_en:
            result = safety_layer.check_safety(query)
            assert not result.is_red_flag, f"False positive for: '{query}'"

    def test_common_phrases_no_false_positive(self, safety_layer):
        """Common phrases that contain trigger words but aren't emergencies."""
        safe_phrases = [
            "имам леко главоболие",  # Not "worst headache ever"
            "малко ме боли коремът",  # Not "severe abdominal pain"
            "имам температура 37.5",  # Not high fever
            "кашлям от вчера",  # Normal cough
            "хрема и запушен нос",  # Common cold
        ]
        for phrase in safe_phrases:
            result = safety_layer.check_safety(phrase)
            assert not result.is_red_flag, f"False positive for: '{phrase}'"


class TestWarningDetection:
    """Tests for warning symptom detection."""

    def test_warning_symptoms_detected(self, safety_layer):
        """Warning symptoms should be detected but not block."""
        warning_symptoms = [
            "кашлица повече от 2 седмици",
            "загуба на тегло без причина",
            "нощно изпотяване",
            "бучка под кожата",
            "persistent cough",
            "unexplained weight loss",
        ]
        for symptom in warning_symptoms:
            result = safety_layer.check_safety(symptom)
            assert result.severity == "warning", f"Should be warning: '{symptom}'"
            assert not result.is_red_flag, "Warning should not be red flag"
            assert result.should_refer_to_doctor


class TestOTCFilter:
    """Tests for OTC product filtering."""

    def test_filter_otc_only(self, safety_layer):
        """Should filter to only OTC products."""

        class MockProduct:
            def __init__(self, name, is_otc):
                self.name = name
                self.is_otc = is_otc

        products = [
            MockProduct("Paracetamol", True),
            MockProduct("Antibiotics", False),
            MockProduct("Ibuprofen", True),
            MockProduct("Prescription Drug", False),
        ]

        filtered = safety_layer.filter_otc_only(products)
        assert len(filtered) == 2
        assert all(p.is_otc for p in filtered)

    def test_filter_empty_list(self, safety_layer):
        """Should handle empty product list."""
        filtered = safety_layer.filter_otc_only([])
        assert filtered == []


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_input(self, safety_layer):
        """Should handle empty input."""
        result = safety_layer.check_safety("")
        assert not result.is_red_flag
        assert result.severity == "none"

    def test_none_input(self, safety_layer):
        """Should handle None input."""
        result = safety_layer.check_safety(None)
        assert not result.is_red_flag
        assert result.severity == "none"

    def test_whitespace_only(self, safety_layer):
        """Should handle whitespace-only input."""
        result = safety_layer.check_safety("   \n\t  ")
        assert not result.is_red_flag

    def test_mixed_case(self, safety_layer):
        """Should detect symptoms regardless of case."""
        result = safety_layer.check_safety("БОЛКА В ГЪРДИТЕ")
        assert result.is_red_flag
        assert result.severity == "emergency"

    def test_special_characters(self, safety_layer):
        """Should handle special characters."""
        result = safety_layer.check_safety("болка в гърдите!!!")
        assert result.is_red_flag


class TestSafetyCheckResult:
    """Tests for SafetyCheckResult dataclass."""

    def test_result_attributes(self, safety_layer):
        """Result should have all required attributes."""
        result = safety_layer.check_safety("болка в гърдите")
        assert hasattr(result, "is_red_flag")
        assert hasattr(result, "severity")
        assert hasattr(result, "matched_symptoms")
        assert hasattr(result, "message")
        assert hasattr(result, "should_refer_to_doctor")

    def test_matched_symptoms_populated(self, safety_layer):
        """Matched symptoms should be populated."""
        result = safety_layer.check_safety("болка в гърдите")
        assert len(result.matched_symptoms) > 0
        assert "болка в гърдите" in result.matched_symptoms


class TestDisclaimers:
    """Tests for safety disclaimers."""

    def test_add_safety_disclaimer_warning(self, safety_layer):
        """Should add disclaimer for warning severity."""
        warning_result = SafetyCheckResult(
            is_red_flag=False,
            severity="warning",
            matched_symptoms=["persistent cough"],
            message="Monitor symptoms",
            should_refer_to_doctor=True,
        )
        response = "Here are some products"
        result = safety_layer.add_safety_disclaimer(response, warning_result)
        assert "Monitor symptoms" in result
        assert response in result

    def test_no_disclaimer_for_none_severity(self, safety_layer):
        """Should not add disclaimer for none severity."""
        none_result = SafetyCheckResult(
            is_red_flag=False, severity="none", matched_symptoms=[], message="", should_refer_to_doctor=False
        )
        response = "Here are some products"
        result = safety_layer.add_safety_disclaimer(response, none_result)
        assert result == response
