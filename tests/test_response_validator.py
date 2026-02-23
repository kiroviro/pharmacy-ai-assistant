from unittest.mock import MagicMock

import pytest

from src.pipeline.response_validator import TextValidator, get_text_validator


@pytest.fixture
def validator():
    return TextValidator()


@pytest.fixture
def validator_with_translator():
    translator = MagicMock()
    translator.translate_to_bulgarian = MagicMock(return_value="Пийте повече течности и почивайте.")
    return TextValidator(translator=translator)


# =============================================================================
# contains_garbage
# =============================================================================


class TestContainsGarbage:
    @pytest.mark.parametrize(
        "text",
        [
            "нежелани реакции при продължителна употреба",
            "странични ефекти включват",
            "свръхчувствителност към активното вещество",
            "европейския парламент прие нов регламент",
            "добави в количка",
            "цена с ддс: 15.99",
            "mg/ml разтвор за инжектиране",
            "фармакокинетика на лекарството",
            "atc код: N02BE01",
            "нзок покрива тази терапия",
            "keep baby comfortable and hydrated",
            "seek medical attention immediately",
        ],
    )
    def test_detects_garbage_patterns(self, validator, text):
        assert validator.contains_garbage(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "Парацетамол е подходящ при главоболие и температура.",
            "Пийте повече течности и почивайте.",
            "Ибупрофен помага при болки и възпаление.",
            "Консултирайте се с лекар, ако симптомите продължат.",
        ],
    )
    def test_accepts_valid_bulgarian_text(self, validator, text):
        assert validator.contains_garbage(text) is False

    def test_rejects_empty_string(self, validator):
        assert validator.contains_garbage("") is True

    def test_rejects_none(self, validator):
        assert validator.contains_garbage(None) is True

    def test_rejects_short_string(self, validator):
        assert validator.contains_garbage("ab") is True

    def test_rejects_low_bulgarian_ratio(self, validator):
        assert validator.contains_garbage("This is entirely English text with no Bulgarian at all") is True

    def test_rejects_repeated_words(self, validator):
        assert validator.contains_garbage("болка болка болка болка болка болка") is True

    def test_rejects_two_word_phrase_repetition(self, validator):
        assert validator.contains_garbage("си гол си гол нещо друго") is True

    def test_rejects_artifact_slash_pattern(self, validator):
        assert validator.contains_garbage("нещо/ нещо/ нещо") is True

    def test_rejects_repeated_substring_pattern(self, validator):
        assert validator.contains_garbage("абабабабабаб") is True

    def test_rejects_translation_doubled_prepositions(self, validator):
        assert validator.contains_garbage("Лекарството е в в аптеката") is True

    def test_whitespace_only(self, validator):
        assert validator.contains_garbage("   ") is True


# =============================================================================
# filter_garbage_sentences
# =============================================================================


class TestFilterGarbageSentences:
    def test_keeps_valid_sentences(self, validator):
        text = "Парацетамол помага при температура. Ибупрофен е противовъзпалително средство."
        result = validator.filter_garbage_sentences(text)
        assert "Парацетамол" in result
        assert "Ибупрофен" in result

    def test_removes_garbage_sentences(self, validator):
        text = "Парацетамол помага при температура. Нежелани реакции включват гадене и повръщане."
        result = validator.filter_garbage_sentences(text)
        assert "Парацетамол" in result
        assert "Нежелани реакции" not in result

    def test_returns_empty_for_all_garbage(self, validator):
        text = "Нежелани реакции. Странични ефекти."
        result = validator.filter_garbage_sentences(text)
        assert result == ""

    def test_returns_empty_for_empty_input(self, validator):
        assert validator.filter_garbage_sentences("") == ""

    def test_returns_empty_for_none(self, validator):
        assert validator.filter_garbage_sentences(None) == ""

    def test_returns_empty_for_short_input(self, validator):
        assert validator.filter_garbage_sentences("abc") == ""

    def test_drops_short_sentences(self, validator):
        text = "Добре. Парацетамол помага при температура и главоболие."
        result = validator.filter_garbage_sentences(text)
        assert "Добре" not in result
        assert "Парацетамол" in result

    def test_drops_mostly_uppercase_sentences(self, validator):
        text = "НЕЩО ИЗЦЯЛО С ГЛАВНИ БУКВИ ТУКА. Парацетамол помага при температура."
        result = validator.filter_garbage_sentences(text)
        assert "НЕЩО" not in result
        assert "Парацетамол" in result

    def test_critical_garbage_truncation(self, validator):
        text = "Парацетамол помага при температура. Също зъбни протези се почистват с паста."
        result = validator.filter_garbage_sentences(text)
        assert "зъбни протези" not in result

    def test_long_sentence_with_comma_splits_clauses(self, validator):
        valid_clause = "Парацетамол е подходящ при леко главоболие и температура до тридесет и осем градуса"
        garbage_clause = "нежелани реакции включват гадене и повръщане при продължителна употреба на лекарството"
        text = f"{valid_clause}, {garbage_clause}."
        # The combined sentence is >120 chars with a comma, so clauses are checked individually
        result = validator.filter_garbage_sentences(text)
        assert "нежелани реакции" not in result


# =============================================================================
# calculate_bulgarian_ratio
# =============================================================================


class TestCalculateBulgarianRatio:
    def test_pure_bulgarian(self, validator):
        ratio = validator.calculate_bulgarian_ratio("Здравейте как сте")
        assert ratio > 0.9

    def test_pure_english(self, validator):
        ratio = validator.calculate_bulgarian_ratio("Hello how are you")
        assert ratio == 0.0

    def test_mixed_text(self, validator):
        ratio = validator.calculate_bulgarian_ratio("Здравей hello")
        assert 0.0 < ratio < 1.0

    def test_empty_string(self, validator):
        assert validator.calculate_bulgarian_ratio("") == 0.0

    def test_numbers_only(self, validator):
        assert validator.calculate_bulgarian_ratio("12345") == 0.0

    def test_punctuation_only(self, validator):
        assert validator.calculate_bulgarian_ratio("...!!!???") == 0.0

    def test_returns_float(self, validator):
        result = validator.calculate_bulgarian_ratio("тест")
        assert isinstance(result, float)

    def test_single_bg_char(self, validator):
        assert validator.calculate_bulgarian_ratio("а") == 1.0

    def test_single_en_char(self, validator):
        assert validator.calculate_bulgarian_ratio("a") == 0.0


# =============================================================================
# is_valid_self_care_tip
# =============================================================================


class TestIsValidSelfCareTip:
    @pytest.mark.parametrize(
        "tip",
        [
            "Пийте повече течности и почивайте.",
            "Приложете студен компрес на челото.",
            "Давайте на бебето достатъчно вода.",
            "Избягвайте тежка храна при стомашни оплаквания.",
            "Приемайте повече витамин С за имунитета.",
        ],
    )
    def test_accepts_valid_tips(self, validator, tip):
        assert validator.is_valid_self_care_tip(tip) is True

    @pytest.mark.parametrize(
        "tip",
        [
            "стъпления при тази процедура",
            "заявление за одобряване на продукт",
            "зъбні протези грижа",
            "репелент срещу комари",
            "грижа за зъбні протези",
        ],
    )
    def test_rejects_garbage_tips(self, validator, tip):
        assert validator.is_valid_self_care_tip(tip) is False

    def test_rejects_empty_string(self, validator):
        assert validator.is_valid_self_care_tip("") is False

    def test_rejects_none(self, validator):
        assert validator.is_valid_self_care_tip(None) is False

    def test_rejects_short_tip(self, validator):
        assert validator.is_valid_self_care_tip("вода") is False

    def test_rejects_mostly_uppercase(self, validator):
        assert validator.is_valid_self_care_tip("ПИЙТЕ ПОВЕЧЕ ВОДА И ТЕЧНОСТИ") is False

    def test_rejects_tip_without_valid_keyword(self, validator):
        assert validator.is_valid_self_care_tip("Нещо напълно различно от здраве и медицина тука.") is False


# =============================================================================
# clean_english_leaks
# =============================================================================


class TestCleanEnglishLeaks:
    def test_returns_clean_bulgarian_unchanged(self, validator):
        text = "Парацетамол помага при температура и главоболие."
        assert validator.clean_english_leaks(text) == text

    def test_returns_empty_unchanged(self, validator):
        assert validator.clean_english_leaks("") == ""

    def test_returns_none_unchanged(self, validator):
        assert validator.clean_english_leaks(None) is None

    def test_returns_mostly_english_unchanged(self, validator):
        text = "This is completely English text."
        assert validator.clean_english_leaks(text) == text

    def test_retranslates_with_translator(self, validator_with_translator):
        # BG text with some English leaks (ratio between 0.50 and 0.95)
        text = "Парацетамол е добър при headache и fever."
        result = validator_with_translator.clean_english_leaks(text)
        assert result == "Пийте повече течности и почивайте."

    def test_removes_english_words_when_translation_fails(self):
        translator = MagicMock()
        translator.translate_to_bulgarian = MagicMock(return_value=None)
        v = TextValidator(translator=translator)
        text = "Парацетамол помага при headache добре."
        result = v.clean_english_leaks(text)
        assert "headache" not in result

    def test_no_translator_returns_original(self, validator):
        text = "Парацетамол помага при headache добре."
        result = validator.clean_english_leaks(text)
        assert result == text

    def test_known_ok_words_not_removed(self, validator_with_translator):
        # paracetamol and ibuprofen are in known_ok_lower
        text = "Вземете paracetamol при температура."
        # BG ratio is high enough that this is already "clean"
        result = validator_with_translator.clean_english_leaks(text)
        assert "paracetamol" in result or result == text

    def test_multi_sentence_keeps_clean_sentences(self):
        translator = MagicMock()
        translator.translate_to_bulgarian = MagicMock(return_value="Превод на изречение.")
        v = TextValidator(translator=translator)
        # First sentence is mostly BG, second has English leak
        bg_sent = "Парацетамол е лекарство за температура и болка."
        en_leak_sent = "Please drink fluids and rest today обаче."
        text = f"{bg_sent} {en_leak_sent}"
        result = v.clean_english_leaks(text)
        # The clean BG sentence should be kept
        assert "Парацетамол" in result


# =============================================================================
# has_repetition (static method)
# =============================================================================


class TestHasRepetition:
    def test_detects_repeated_words(self):
        assert TextValidator.has_repetition("болка болка болка нещо") is True

    def test_no_repetition(self):
        assert TextValidator.has_repetition("Парацетамол помага при температура") is False

    def test_short_text_returns_false(self):
        assert TextValidator.has_repetition("да не") is False

    def test_custom_threshold(self):
        # has_repetition requires len(words) >= 4 before checking counts
        assert TextValidator.has_repetition("нещо нещо друго още", threshold=2) is True
        assert TextValidator.has_repetition("нещо нещо друго още", threshold=3) is False

    def test_ignores_short_words(self):
        # Words with len <= 2 are ignored by the "len(w) > 2" check
        assert TextValidator.has_repetition("за за за за нещо друго тука") is False


# =============================================================================
# get_text_validator (singleton)
# =============================================================================


class TestGetTextValidator:
    def test_returns_text_validator_instance(self):
        # Reset singleton for isolated test
        import src.pipeline.response_validator as rv

        rv._text_validator = None
        v = get_text_validator()
        assert isinstance(v, TextValidator)

    def test_returns_same_instance(self):
        import src.pipeline.response_validator as rv

        rv._text_validator = None
        v1 = get_text_validator()
        v2 = get_text_validator()
        assert v1 is v2
