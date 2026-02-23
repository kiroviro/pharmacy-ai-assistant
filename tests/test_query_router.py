import pytest

from src.pipeline.query_router import (
    extract_catalog_search_term,
    extract_comparison_drugs,
    get_help_clarification_message,
    has_symptom_words,
    is_catalog_query,
    is_comparison_query,
    is_help_clarification_query,
    is_single_drug_name_query,
)


# =============================================================================
# is_catalog_query
# =============================================================================


class TestIsCatalogQuery:
    @pytest.mark.parametrize(
        "query",
        [
            "какви марки ибупрофен имате?",
            "какви марки парацетамол предлагате?",
            "покажи ми витамини",
            "търся крем за лице",
            "имате ли шампоан",
            "предлагате ли слънцезащитен крем",
            "продавате ли термометър",
            "списък с кремове",
            "всички витамини",
            "продукти на Nurofen",
            "заместител на парацетамол",
            "алтернатива на ибупрофен",
            "вместо аспирин",
        ],
    )
    def test_detects_bg_catalog_queries(self, query):
        is_cat, term = is_catalog_query(query)
        assert is_cat is True
        assert len(term) > 0

    @pytest.mark.parametrize(
        "query",
        [
            "show me vitamins",
            "looking for sunscreen",
            "do you have paracetamol",
            "do you sell shampoo",
            "list of supplements",
            "substitute for ibuprofen",
            "instead of aspirin",
            "equivalent to paracetamol",
        ],
    )
    def test_detects_en_catalog_queries(self, query):
        is_cat, term = is_catalog_query(query)
        assert is_cat is True
        assert len(term) > 0

    @pytest.mark.parametrize(
        "query",
        [
            "боли ме главата",
            "имам температура и болка",
            "кашлям от два дни",
            "имам болки в гърба",
        ],
    )
    def test_rejects_symptom_queries(self, query):
        is_cat, term = is_catalog_query(query)
        assert is_cat is False
        assert term == ""

    def test_empty_string(self):
        is_cat, term = is_catalog_query("")
        assert is_cat is False
        assert term == ""

    def test_whitespace_only(self):
        is_cat, term = is_catalog_query("   ")
        assert is_cat is False
        assert term == ""

    def test_category_keyword_without_symptoms_detected(self):
        is_cat, term = is_catalog_query("шампоан за суха коса")
        assert is_cat is True
        assert len(term) > 0

    def test_category_keyword_with_symptoms_rejected(self):
        is_cat, term = is_catalog_query("крем за болка в гърба")
        assert is_cat is False
        assert term == ""


# =============================================================================
# extract_catalog_search_term
# =============================================================================


class TestExtractCatalogSearchTerm:
    def test_strips_bg_filler(self):
        term = extract_catalog_search_term("какви марки ибупрофен имате?")
        assert "ибупрофен" in term
        assert "какви" not in term
        assert "имате" not in term

    def test_strips_en_filler(self):
        term = extract_catalog_search_term("show me vitamins")
        assert "vitamins" in term

    def test_returns_empty_for_short_result(self):
        term = extract_catalog_search_term("имате ли аз")
        assert term == ""

    def test_strips_punctuation(self):
        term = extract_catalog_search_term("покажи ми витамини??!")
        assert "?" not in term
        assert "!" not in term


# =============================================================================
# has_symptom_words
# =============================================================================


class TestHasSymptomWords:
    @pytest.mark.parametrize("text", ["болка в главата", "имам температура", "силна кашлица", "pain in my back"])
    def test_detects_symptoms(self, text):
        assert has_symptom_words(text) is True

    @pytest.mark.parametrize("text", ["витамини", "шампоан", "крем за лице", "sunscreen"])
    def test_no_symptoms(self, text):
        assert has_symptom_words(text) is False


# =============================================================================
# is_comparison_query
# =============================================================================


class TestIsComparisonQuery:
    @pytest.mark.parametrize(
        "query",
        [
            "кое е по-силно ибупрофен или парацетамол",
            "кой е по-добър аспирин или ибупрофен",
            "сравни парацетамол с ибупрофен",
            "разлика между аспирин и парацетамол",
            "ибупрофен vs парацетамол",
            "парацетамол или ибупрофен за главоболие",
            "да взема парацетамол или аспирин",
        ],
    )
    def test_detects_bg_comparison_queries(self, query):
        is_comp, drugs = is_comparison_query(query)
        assert is_comp is True
        assert len(drugs) >= 2

    @pytest.mark.parametrize(
        "query",
        [
            "which is stronger ibuprofen or paracetamol",
            "compare aspirin with ibuprofen",
            "difference between paracetamol and aspirin",
            "ibuprofen vs paracetamol",
            "ibuprofen or paracetamol for headache",
            "should I take aspirin or ibuprofen",
        ],
    )
    def test_detects_en_comparison_queries(self, query):
        is_comp, drugs = is_comparison_query(query)
        assert is_comp is True
        assert len(drugs) >= 2

    def test_single_drug_not_comparison(self):
        is_comp, drugs = is_comparison_query("ибупрофен срещу нещо")
        # Pattern matches but only one drug found in COMMON_DRUG_NAMES
        assert is_comp is False
        assert drugs == []

    def test_no_pattern_match(self):
        is_comp, drugs = is_comparison_query("парацетамол за главоболие")
        assert is_comp is False
        assert drugs == []

    def test_empty_string(self):
        is_comp, drugs = is_comparison_query("")
        assert is_comp is False
        assert drugs == []


# =============================================================================
# extract_comparison_drugs
# =============================================================================


class TestExtractComparisonDrugs:
    def test_extracts_two_drugs(self):
        drugs = extract_comparison_drugs("ибупрофен или парацетамол")
        assert len(drugs) == 2
        assert "ибупрофен" in drugs
        assert "парацетамол" in drugs

    def test_deduplicates_canonical_forms(self):
        drugs = extract_comparison_drugs("nurofen или ибупрофен или парацетамол")
        # nurofen and ибупрофен map to the same canonical form
        assert len(drugs) == 2

    def test_limits_to_two_drugs(self):
        drugs = extract_comparison_drugs("ибупрофен парацетамол аспирин диклофенак")
        assert len(drugs) == 2

    def test_no_drugs_found(self):
        drugs = extract_comparison_drugs("нещо друго")
        assert drugs == []


# =============================================================================
# is_single_drug_name_query
# =============================================================================


class TestIsSingleDrugNameQuery:
    @pytest.mark.parametrize(
        "query",
        [
            "парацетамол",
            "ибупрофен",
            "аспирин",
            "paracetamol",
            "ibuprofen",
            "aspirin",
            "нурофен",
        ],
    )
    def test_detects_single_drug_names(self, query):
        assert is_single_drug_name_query(query) is True

    def test_detects_drug_with_dosage(self):
        assert is_single_drug_name_query("парацетамол 500мг") is True

    def test_rejects_multi_word_queries(self):
        assert is_single_drug_name_query("парацетамол за главоболие при бременност") is False

    def test_rejects_non_drug_words(self):
        assert is_single_drug_name_query("кашлица") is False

    def test_empty_string(self):
        assert is_single_drug_name_query("") is False

    def test_two_word_with_drug(self):
        # Two words max — "аспирин" is a recognized drug, so it should match
        assert is_single_drug_name_query("аспирин таблетки") is True

    def test_two_words_no_drug(self):
        assert is_single_drug_name_query("таблетки хапчета") is False


# =============================================================================
# is_help_clarification_query
# =============================================================================


class TestIsHelpClarificationQuery:
    @pytest.mark.parametrize(
        "query",
        [
            "помощ",
            "помогнете",
            "здравей",
            "здрасти",
            "здравейте",
            "help",
            "hi",
            "hello",
            "привет",
        ],
    )
    def test_detects_help_words(self, query):
        assert is_help_clarification_query(query) is True

    @pytest.mark.parametrize(
        "query",
        [
            "  помощ  ",
            "  HI  ",
            "  Hello  ",
            "ЗДРАВЕЙ",
        ],
    )
    def test_handles_whitespace_and_case(self, query):
        assert is_help_clarification_query(query) is True

    @pytest.mark.parametrize(
        "query",
        [
            "парацетамол",
            "боли ме главата",
            "помощ за лекарство",
            "",
        ],
    )
    def test_rejects_non_help_queries(self, query):
        assert is_help_clarification_query(query) is False


# =============================================================================
# get_help_clarification_message
# =============================================================================


class TestGetHelpClarificationMessage:
    def test_returns_non_empty_string(self):
        msg = get_help_clarification_message()
        assert isinstance(msg, str)
        assert len(msg) > 50

    def test_contains_bulgarian_text(self):
        msg = get_help_clarification_message()
        bulgarian_chars = set("абвгдежзийклмнопрстуфхцчшщъьюя")
        has_bg = any(c in bulgarian_chars for c in msg.lower())
        assert has_bg is True

    def test_stable_return_value(self):
        assert get_help_clarification_message() == get_help_clarification_message()
