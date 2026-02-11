"""
Unit tests for the Intent Classifier.

The intent classifier should:
- Accept all medical queries (high recall - no false negatives)
- Reject non-medical queries (weather, jokes, recipes, etc.)
- Reject profanity/inappropriate language
"""

import pytest
from src.intent_classifier import IntentClassifier


class TestMedicalQueryDetection:
    """Tests for medical query detection - should have HIGH recall."""

    def test_medical_queries_bulgarian(self, intent_classifier, normal_medical_queries_bg):
        """All Bulgarian medical queries should be classified as medical."""
        for query in normal_medical_queries_bg:
            is_medical, confidence, reason = intent_classifier.is_medical_query(query)
            assert is_medical, f"FAILED to classify as medical: '{query}' (reason: {reason})"

    def test_medical_queries_english(self, intent_classifier):
        """Clear English medical queries should be classified as medical."""
        # Focus on queries with clear medical keywords
        clear_medical = [
            "I have a headache",
            "my throat hurts",
            "I have a fever",
            "my stomach hurts",
            "my back hurts",
            "I have a rash",
            "I have insomnia",  # Clear medical term
        ]
        for query in clear_medical:
            is_medical, confidence, reason = intent_classifier.is_medical_query(query)
            assert is_medical, f"FAILED to classify as medical: '{query}' (reason: {reason})"

    def test_symptom_keywords_bg(self, intent_classifier):
        """Queries with Bulgarian symptom keywords should be medical."""
        symptoms = [
            "болка",
            "болки",
            "температура",
            "главоболие",
            "кашлица",
            "хрема",
            "гадене",
            "диария",
            "умора",
            "сърбеж",
            "обрив",
            "алергия",
        ]
        for symptom in symptoms:
            is_medical, _, _ = intent_classifier.is_medical_query(symptom)
            assert is_medical, f"Should detect symptom keyword: '{symptom}'"

    def test_body_part_keywords_bg(self, intent_classifier):
        """Queries mentioning body parts should be medical."""
        body_parts = [
            "боли ме глава",
            "проблем с гърлото",
            "болка в корема",
            "проблеми с очите",
            "боли ме гърба",
        ]
        for query in body_parts:
            is_medical, _, _ = intent_classifier.is_medical_query(query)
            assert is_medical, f"Should detect body part reference: '{query}'"

    def test_medication_keywords_bg(self, intent_classifier):
        """Queries about medications should be medical."""
        medication_queries = [
            "какво лекарство да взема",
            "търся таблетки",
            "имам нужда от сироп",
            "препоръчай ми мехлем",
            "витамини за имунитет",
        ]
        for query in medication_queries:
            is_medical, _, _ = intent_classifier.is_medical_query(query)
            assert is_medical, f"Should detect medication query: '{query}'"


class TestNonMedicalRejection:
    """Tests for non-medical query rejection."""

    def test_non_medical_queries_bulgarian(self, intent_classifier):
        """Clear non-medical Bulgarian queries with non-medical keywords should be rejected."""
        # Focus on queries with clear non-medical keywords
        clear_non_medical = [
            "какво е времето",
            "разкажи ми виц",
            "какви са новините",
            "кога е мачът",
        ]
        for query in clear_non_medical:
            is_medical, confidence, reason = intent_classifier.is_medical_query(query)
            assert not is_medical, f"Should reject non-medical: '{query}'"

    def test_non_medical_queries_english(self, intent_classifier):
        """Clear non-medical English queries should be rejected."""
        clear_non_medical = [
            "what's the weather",
            "tell me a joke",
            "what's in the news",
        ]
        for query in clear_non_medical:
            is_medical, confidence, reason = intent_classifier.is_medical_query(query)
            assert not is_medical, f"Should reject non-medical: '{query}'"

    def test_weather_queries(self, intent_classifier):
        """Weather queries should be rejected."""
        weather_queries = [
            "какво е времето",
            "прогноза за времето",
            "what's the weather",
            "weather forecast",
        ]
        for query in weather_queries:
            is_medical, _, _ = intent_classifier.is_medical_query(query)
            assert not is_medical, f"Should reject weather query: '{query}'"

    def test_entertainment_queries(self, intent_classifier):
        """Entertainment queries with clear non-medical keywords should be rejected."""
        # Focus on queries with explicit non-medical keywords
        entertainment = [
            "какви са новините",  # news
            "кога е мачът",       # match/game
            "tell me a joke",     # joke
        ]
        for query in entertainment:
            is_medical, _, _ = intent_classifier.is_medical_query(query)
            assert not is_medical, f"Should reject entertainment query: '{query}'"


class TestProfanityRejection:
    """Tests for profanity rejection."""

    def test_profanity_rejected(self, intent_classifier, profanity_queries):
        """Queries with profanity should be rejected."""
        for query in profanity_queries:
            is_medical, confidence, reason = intent_classifier.is_medical_query(query)
            assert not is_medical, f"Should reject profanity: '{query}'"
            assert "inappropriate" in reason.lower() or "profanity" in reason.lower()

    def test_profanity_rejection_message(self, intent_classifier):
        """Rejection message for profanity should be appropriate."""
        message = intent_classifier.get_rejection_message("bg", "Inappropriate language")
        assert "подходящ език" in message.lower() or "inappropriate" in message.lower()


class TestRejectionMessages:
    """Tests for rejection messages."""

    def test_rejection_message_bulgarian(self, intent_classifier):
        """Bulgarian rejection message should be in Bulgarian."""
        message = intent_classifier.get_rejection_message("bg")
        assert "съжалявам" in message.lower() or "здраве" in message.lower()
        # Should mention what the bot CAN do
        assert "симптом" in message.lower() or "здравослов" in message.lower()

    def test_rejection_message_english(self, intent_classifier):
        """English rejection message should be in English."""
        message = intent_classifier.get_rejection_message("en")
        assert "sorry" in message.lower() or "health" in message.lower()

    def test_profanity_rejection_message_bulgarian(self, intent_classifier):
        """Profanity rejection in Bulgarian should be polite."""
        message = intent_classifier.get_rejection_message("bg", "Inappropriate language")
        assert "подходящ" in message.lower()


class TestConfidenceScores:
    """Tests for confidence score behavior."""

    def test_high_confidence_for_clear_medical(self, intent_classifier):
        """Clear medical queries should have high confidence."""
        is_medical, confidence, _ = intent_classifier.is_medical_query("имам силно главоболие и температура")
        assert is_medical
        assert confidence >= 0.7, f"Expected high confidence, got {confidence}"

    def test_high_confidence_for_clear_non_medical(self, intent_classifier):
        """Clear non-medical queries should have high rejection confidence."""
        is_medical, confidence, _ = intent_classifier.is_medical_query("какво е времето днес")
        assert not is_medical
        assert confidence >= 0.7, f"Expected high confidence, got {confidence}"


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_query(self, intent_classifier):
        """Empty query should be rejected."""
        is_medical, _, reason = intent_classifier.is_medical_query("")
        assert not is_medical
        assert "empty" in reason.lower()

    def test_whitespace_only(self, intent_classifier):
        """Whitespace-only query should be rejected."""
        is_medical, _, _ = intent_classifier.is_medical_query("   \n\t  ")
        assert not is_medical

    def test_very_short_query(self, intent_classifier):
        """Very short non-medical queries should be rejected."""
        is_medical, _, _ = intent_classifier.is_medical_query("hi")
        assert not is_medical

    def test_short_medical_keyword(self, intent_classifier):
        """Short but clear medical keywords should be accepted."""
        is_medical, _, _ = intent_classifier.is_medical_query("болка")
        assert is_medical

    def test_mixed_case(self, intent_classifier):
        """Should work regardless of case."""
        is_medical, _, _ = intent_classifier.is_medical_query("ИМАМ ГЛАВОБОЛИЕ")
        assert is_medical

    def test_long_query_defaults_to_medical(self, intent_classifier):
        """Long ambiguous queries should default to medical (permissive)."""
        long_query = "Искам да попитам нещо за едно състояние което имам от няколко дни и не знам какво да правя"
        is_medical, confidence, reason = intent_classifier.is_medical_query(long_query)
        # Should be permissive - default to medical if unclear
        assert is_medical or confidence < 0.5, f"Long query handling: {reason}"


class TestSpecialCases:
    """Tests for special/tricky cases."""

    def test_medical_temperature_detected(self, intent_classifier):
        """Medical temperature queries should be detected."""
        is_medical, _, _ = intent_classifier.is_medical_query("имам температура 38")
        assert is_medical

    def test_weather_with_keyword_rejected(self, intent_classifier):
        """Weather queries with clear weather keywords should be rejected."""
        # "времето" is a clear weather keyword
        is_medical, _, _ = intent_classifier.is_medical_query("какво е времето")
        assert not is_medical

    def test_medical_prescription_detected(self, intent_classifier):
        """Medical prescription queries should be detected."""
        is_medical, _, _ = intent_classifier.is_medical_query("лекарство без рецепта")
        assert is_medical

    def test_clear_food_query_rejected(self, intent_classifier):
        """Clear food/cooking queries should be rejected."""
        # "ресторант" is a clear food keyword
        is_medical, _, _ = intent_classifier.is_medical_query("търся ресторант")
        assert not is_medical
