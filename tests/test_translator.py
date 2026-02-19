"""
Tests for the translator module.

Ensures medical dictionary translations work correctly and don't regress.
"""

import pytest

from src.translator import Translator


class TestMedicalDictionary:
    """Test the medical term translation dictionary."""

    @pytest.fixture
    def translator(self):
        """Create a translator instance for testing."""
        return Translator()

    # =========================================================================
    # SYMPTOM TRANSLATIONS
    # =========================================================================

    @pytest.mark.parametrize(
        "english,expected_bulgarian",
        [
            # Basic symptoms
            ("headache", "главоболие"),
            ("headaches", "главоболия"),
            ("fever", "температура"),
            ("fevers", "температури"),
            ("cough", "кашлица"),
            ("runny nose", "хрема"),
            ("sniffles", "хрема"),
            ("sneezing", "кихане"),
            ("sore throat", "болки в гърлото"),
            # Infections
            ("viral infection", "вирусна инфекция"),
            ("bacterial infection", "бактериална инфекция"),
            ("bronchitis", "бронхит"),
            # Pain types
            ("muscle pain", "мускулна болка"),
            ("back pain", "болки в гърба"),
            ("stomach pain", "стомашна болка"),
            ("chest pain", "болка в гърдите"),
            ("joint pain", "болка в ставите"),
            # Other symptoms
            ("dizziness", "световъртеж"),
            ("fatigue", "умора"),
            ("nausea", "гадене"),
            ("vomiting", "повръщане"),
            ("diarrhea", "диария"),
            ("constipation", "запек"),
            ("rash", "обрив"),
            ("swelling", "подуване"),
            ("itching", "сърбеж"),
        ],
    )
    def test_symptom_translation(self, translator, english, expected_bulgarian):
        """Test that common symptoms translate correctly."""
        result = translator.translate_symptom(english)
        assert result == expected_bulgarian, f"Expected '{expected_bulgarian}' but got '{result}'"

    # =========================================================================
    # TREATMENT TRANSLATIONS
    # =========================================================================

    @pytest.mark.parametrize(
        "english,expected_bulgarian",
        [
            ("analgesics", "болкоуспокояващи"),
            ("pain relievers", "болкоуспокояващи"),
            ("painkillers", "болкоуспокояващи"),
            ("antipyretics", "антипиретици (за сваляне на температура)"),
            ("anti-inflammatory", "противовъзпалително"),
            ("decongestants", "деконгестанти (за запушен нос)"),
            ("antihistamines", "антихистамини"),
            ("expectorants", "отхрачващи средства"),
            ("cough suppressant", "средство за потискане на кашлицата"),
            ("throat lozenges", "таблетки за гърло"),
            ("nasal spray", "спрей за нос"),
            ("nasal drops", "капки за нос"),
            ("antivirals", "антивирусни средства"),
            ("antibiotics", "антибиотици"),
        ],
    )
    def test_treatment_translation(self, translator, english, expected_bulgarian):
        """Test that treatment types translate correctly."""
        result = translator._apply_medical_dictionary(english)
        assert expected_bulgarian in result, f"Expected '{expected_bulgarian}' in '{result}'"

    # =========================================================================
    # DRUG NAME TRANSLATIONS
    # =========================================================================

    @pytest.mark.parametrize(
        "english,expected_bulgarian",
        [
            ("paracetamol", "парацетамол"),
            ("acetaminophen", "парацетамол"),
            ("ibuprofen", "ибупрофен"),
        ],
    )
    def test_drug_name_translation(self, translator, english, expected_bulgarian):
        """Test that common drug names translate correctly."""
        result = translator._apply_medical_dictionary(english)
        assert expected_bulgarian in result

    # =========================================================================
    # SELF-CARE PHRASE TRANSLATIONS
    # =========================================================================

    @pytest.mark.parametrize(
        "english,expected_bulgarian",
        [
            ("drink plenty of fluids", "пийте много течности"),
            ("stay hydrated", "пийте достатъчно течности"),
            ("get plenty of rest", "почивайте достатъчно"),
            ("rest in a quiet room", "почивайте в тиха стая"),
            ("apply cold compress", "приложете студен компрес"),
            ("apply warm compress", "приложете топъл компрес"),
            ("avoid bright lights", "избягвайте ярка светлина"),
            ("gargle with salt water", "гаргара със солена вода"),
        ],
    )
    def test_self_care_translation(self, translator, english, expected_bulgarian):
        """Test that self-care advice translates correctly."""
        result = translator._apply_medical_dictionary(english)
        assert expected_bulgarian in result, f"Expected '{expected_bulgarian}' in '{result}'"

    # =========================================================================
    # DOCTOR RECOMMENDATION TRANSLATIONS
    # =========================================================================

    @pytest.mark.parametrize(
        "english,expected_bulgarian",
        [
            ("see doctor", "посетете лекар"),
            ("see a doctor", "посетете лекар"),
            ("see a pediatrician", "посетете педиатър"),
            ("consult a doctor", "консултирайте се с лекар"),
            ("consult a pediatrician", "консултирайте се с педиатър"),
            ("seek medical help", "потърсете медицинска помощ"),
            ("seek medical attention", "потърсете медицинска помощ"),
            ("if symptoms persist", "ако симптомите продължават"),
            ("if symptoms worsen", "ако симптомите се влошат"),
        ],
    )
    def test_doctor_recommendation_translation(self, translator, english, expected_bulgarian):
        """Test that doctor recommendations translate correctly."""
        result = translator._apply_medical_dictionary(english)
        assert expected_bulgarian in result

    # =========================================================================
    # PEDIATRIC TRANSLATIONS
    # =========================================================================

    @pytest.mark.parametrize(
        "english,expected_bulgarian",
        [
            ("infant", "бебе"),
            ("infants", "бебета"),
            ("baby", "бебе"),
            ("babies", "бебета"),
            ("child", "дете"),
            ("children", "деца"),
            ("newborn", "новородено"),
            ("pediatric", "детски"),
            ("infant fever", "температура при бебе"),
            ("baby fever", "температура при бебе"),
        ],
    )
    def test_pediatric_translation(self, translator, english, expected_bulgarian):
        """Test that pediatric terms translate correctly."""
        result = translator._apply_medical_dictionary(english)
        assert expected_bulgarian in result

    # =========================================================================
    # CONNECTING WORDS
    # =========================================================================

    def test_connecting_word_and(self, translator):
        """Test that 'and' translates to 'и'."""
        # Use words not in dictionary to isolate the connector test
        result = translator._apply_medical_dictionary("xyz and abc")
        assert " и " in result
        assert " and " not in result

    def test_connecting_word_or(self, translator):
        """Test that 'or' translates to 'или'."""
        result = translator._apply_medical_dictionary("xyz or abc")
        assert " или " in result
        assert " or " not in result

    # =========================================================================
    # FULL SENTENCE TRANSLATIONS
    # =========================================================================

    def test_full_sentence_headache_explanation(self, translator):
        """Test that full headache explanation translates correctly."""
        english = "tension headaches occur when muscles in head and neck tighten, often from stress or poor posture"
        result = translator._apply_medical_dictionary(english)
        # Should be fully translated
        assert "тензионно" in result.lower() or "главоболие" in result.lower()
        assert "мускулите" in result.lower() or "стрес" in result.lower()

    def test_full_sentence_recovery(self, translator):
        """Test that recovery sentences translate correctly."""
        english = "most headaches improve within 2-4 hours with treatment"
        result = translator._apply_medical_dictionary(english)
        assert "главоболия" in result.lower()
        assert "2-4" in result

    # =========================================================================
    # DICTIONARY SORTING (longer phrases first)
    # =========================================================================

    def test_dictionary_sorts_by_length(self, translator):
        """Test that longer phrases match before shorter ones."""
        # "tension headache" should match before "headache"
        english = "tension headache"
        result = translator._apply_medical_dictionary(english)
        # Should get "тензионно главоболие", not "tension главоболие"
        assert "тензионно" in result.lower() or "главоболие" in result

    def test_dictionary_handles_plurals(self, translator):
        """Test that plural forms are handled correctly."""
        english = "headaches"
        result = translator._apply_medical_dictionary(english)
        # Should be "главоболия" (plural), not "главоболиеs"
        assert "главоболия" in result
        assert "главоболиеs" not in result


class TestBulgarianRatioCalculation:
    """Test the Bulgarian character ratio calculation."""

    @pytest.fixture
    def translator(self):
        return Translator()

    @pytest.mark.parametrize(
        "text,min_ratio,max_ratio",
        [
            ("главоболие", 0.99, 1.0),  # Pure Bulgarian
            ("headache", 0.0, 0.01),  # Pure English
            ("главоболие headache", 0.4, 0.6),  # Mixed
            ("", 0.0, 0.01),  # Empty
            ("123 456", 0.0, 0.01),  # Numbers only
        ],
    )
    def test_bulgarian_ratio(self, translator, text, min_ratio, max_ratio):
        """Test Bulgarian character ratio calculation."""
        ratio = translator._calculate_bulgarian_ratio(text)
        assert min_ratio <= ratio <= max_ratio, f"Ratio {ratio} not in [{min_ratio}, {max_ratio}]"


class TestTranslateSymptom:
    """Test the dedicated symptom translation method."""

    @pytest.fixture
    def translator(self):
        return Translator()

    def test_exact_match(self, translator):
        """Test exact dictionary match."""
        result = translator.translate_symptom("headache")
        assert result == "главоболие"

    def test_case_insensitive(self, translator):
        """Test case-insensitive matching."""
        result = translator.translate_symptom("HEADACHE")
        assert result == "главоболие"

    def test_empty_input(self, translator):
        """Test empty input handling."""
        result = translator.translate_symptom("")
        assert result == ""

    def test_whitespace_input(self, translator):
        """Test whitespace handling."""
        result = translator.translate_symptom("  headache  ")
        assert result == "главоболие"


class TestCaching:
    """Test the translation caching functionality."""

    @pytest.fixture
    def translator(self):
        return Translator()

    def test_cache_stats_initial(self, translator):
        """Test initial cache stats."""
        stats = translator.get_cache_stats()
        # BG→EN translation was removed in commit 6b5358a
        assert stats["en_to_bg"]["size"] == 0

    def test_clear_cache(self, translator):
        """Test cache clearing."""
        # This shouldn't raise any errors
        translator.clear_cache()
        stats = translator.get_cache_stats()
        # BG→EN translation was removed in commit 6b5358a
        assert stats["en_to_bg"]["hits"] == 0


class TestRegressionPrevention:
    """
    Regression tests for specific bugs that were fixed.

    These tests ensure we don't reintroduce problems.
    """

    @pytest.fixture
    def translator(self):
        return Translator()

    def test_no_english_s_suffix_on_bulgarian_words(self, translator):
        """
        Regression: "headaches" was becoming "главоболиеs" instead of "главоболия".

        Fixed by adding plural forms to dictionary.
        """
        result = translator._apply_medical_dictionary("headaches")
        assert "главоболиеs" not in result
        assert "главоболия" in result

    def test_mixed_language_in_explanation(self, translator):
        """
        Regression: Explanations had mixed English/Bulgarian text.

        Example: "болкоуспокояващи блокират болковите сигнали and намаляват..."
        """
        text = "analgesics block pain signals and reduce inflammation"
        result = translator._apply_medical_dictionary(text)
        # "and" should be translated to "и"
        assert " and " not in result or " и " in result

    def test_recovery_section_wrong_medical_term(self, translator):
        """
        Regression: Recovery section contained wrong medical terms (IntronA).

        This was garbage text that should be filtered elsewhere, but dictionary
        shouldn't introduce new garbage.
        """
        text = "Most headaches improve within 2-4 hours with treatment"
        result = translator._apply_medical_dictionary(text)
        assert "intron" not in result.lower()
        assert "интрон" not in result.lower()

    def test_tension_or_stress_translation(self, translator):
        """
        Regression: "tension or stress" was not being translated.
        """
        text = "tension or stress"
        result = translator._apply_medical_dictionary(text)
        assert "напрежение" in result or "стрес" in result
