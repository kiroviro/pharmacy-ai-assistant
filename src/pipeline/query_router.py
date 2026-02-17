"""
Query routing logic for the ViaPharma pipeline.

Detects query type (catalog, comparison, help, single-drug) and extracts
relevant search terms or drug names for downstream processing.
"""

import re

from src.logging_config import get_logger
from src.pipeline.constants import (
    CATALOG_CATEGORIES,
    CATALOG_PATTERNS_BG,
    CATALOG_PATTERNS_EN,
    CATALOG_REMOVE_PATTERNS,
    COMMON_DRUG_NAMES,
    COMPARISON_CANONICAL_MAP,
    COMPARISON_PATTERNS_BG,
    COMPARISON_PATTERNS_EN,
    HELP_CLARIFICATION_WORDS,
    SYMPTOM_WORDS,
)

logger = get_logger("viapharma.pipeline")

HELP_CLARIFICATION_MESSAGE = (
    "Здравейте! 👋 Аз съм вашият аптечен асистент.\n\n"
    "Мога да ви помогна с:\n"
    "• Препоръки за продукти при симптоми (главоболие, настинка, болки и др.)\n"
    "• Информация за лекарства без рецепта\n"
    "• Търсене на продукти в каталога\n\n"
    "**Какво ви притеснява? Опишете си симптомите на български.**"
    "\n---\n"
    "*Това е информационна услуга. Консултирайте се с фармацевт за персонална препоръка.*"
)


def is_catalog_query(text: str) -> tuple[bool, str]:
    """
    Detect if query is a product catalog inquiry (not a medical symptom query).

    Returns:
        Tuple of (is_catalog, search_term)
    """
    text_lower = text.lower().strip()

    def check_patterns(patterns: list, pattern_type: str) -> tuple[bool, str]:
        """Check patterns and return search term if matched."""
        for pattern in patterns:
            if pattern.search(text_lower):
                search_term = extract_catalog_search_term(text)
                if search_term:
                    logger.debug(f"Catalog query detected ({pattern_type})", extra={"search_term": search_term})
                    return True, search_term
        return False, ""

    # Check Bulgarian patterns
    result = check_patterns(CATALOG_PATTERNS_BG, "BG pattern")
    if result[0]:
        return result

    # Check English patterns
    result = check_patterns(CATALOG_PATTERNS_EN, "EN pattern")
    if result[0]:
        return result

    # Check category keywords without symptoms
    has_category = any(cat in text_lower for cat in CATALOG_CATEGORIES)
    if has_category and not has_symptom_words(text_lower):
        search_term = extract_catalog_search_term(text)
        if search_term:
            logger.debug("Catalog query detected (category keyword)", extra={"search_term": search_term})
            return True, search_term

    return False, ""


def extract_catalog_search_term(text: str) -> str:
    """Extract the product category/search term from a catalog query."""
    result = text.lower()
    for pattern in CATALOG_REMOVE_PATTERNS:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    result = result.strip(' ?.,!').strip()
    return result if len(result) > 2 else ""


def has_symptom_words(text: str) -> bool:
    """Check if text contains symptom-related words."""
    return any(symptom in text for symptom in SYMPTOM_WORDS)


def is_comparison_query(text: str) -> tuple[bool, list[str]]:
    """
    Detect if query is a medication comparison question.

    Returns:
        Tuple of (is_comparison, drug_names)
    """
    text_lower = text.lower().strip()
    all_patterns = [
        (COMPARISON_PATTERNS_BG, "BG"),
        (COMPARISON_PATTERNS_EN, "EN"),
    ]

    for patterns, lang in all_patterns:
        for pattern in patterns:
            if pattern.search(text_lower):
                drugs = extract_comparison_drugs(text_lower)
                if len(drugs) >= 2:
                    logger.debug(f"Comparison query detected ({lang})", extra={"drugs": drugs})
                    return True, drugs

    return False, []


def extract_comparison_drugs(text: str) -> list[str]:
    """Extract drug names from a comparison query."""
    text_lower = text.lower()
    found_drugs = []

    for drug in COMMON_DRUG_NAMES:
        if drug in text_lower and drug not in found_drugs:
            found_drugs.append(drug)

    seen_canonical = set()
    unique_drugs = []
    for drug in found_drugs:
        canonical = COMPARISON_CANONICAL_MAP.get(drug, drug)
        if canonical not in seen_canonical:
            seen_canonical.add(canonical)
            unique_drugs.append(drug)

    return unique_drugs[:2]


def is_single_drug_name_query(text: str) -> bool:
    """Check if query is a single drug/product name."""
    words = text.strip().lower().split()
    if len(words) > 2:
        return False
    for w in words:
        clean = re.sub(r'[\dмгmgl\s]+', '', w)
        if clean and clean in COMMON_DRUG_NAMES:
            return True
        if w in COMMON_DRUG_NAMES:
            return True
    return False


def is_help_clarification_query(text: str) -> bool:
    """Check if query is ambiguous help/greeting."""
    return text.strip().lower() in HELP_CLARIFICATION_WORDS


def get_help_clarification_message() -> str:
    """Return friendly message asking user to clarify their needs."""
    return HELP_CLARIFICATION_MESSAGE
