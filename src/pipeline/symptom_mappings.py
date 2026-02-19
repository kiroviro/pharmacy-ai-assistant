"""
Centralized symptom to treatment type mappings.

This module provides the single source of truth for mapping Bulgarian/English
symptom keywords to treatment categories. Used across:
- MedicalReasoningService (symptom validation)
- ProductMatcher (treatment type extraction)
- ProductStore (category-aware search)
- MedicalModel (fallback reasoning)

Adding a new symptom? Update the mappings here, not in individual modules.
"""

# Bulgarian symptom keywords → treatment type mapping
# Used to validate/correct LLM treatment_type and extract from queries
BG_SYMPTOM_TO_TREATMENT = {
    # Digestive/GI symptoms - HIGH PRIORITY (often misclassified as cold/flu)
    "диария": "antidiarrheal",
    "диарея": "antidiarrheal",
    "разстройство": "antidiarrheal",
    "гадене": "digestive",
    "повръщане": "digestive",
    "стомах": "digestive",
    "стомашни": "digestive",
    "коремна болка": "digestive",
    "киселини": "antacids",
    "запек": "laxatives",
    "чревни": "digestive",
    "рефлукс": "antacids",
    "стомашен сок": "antacids",
    # Pain
    "болка": "analgesics",
    "главоболие": "analgesics",
    "мигрена": "analgesics",
    "болки": "analgesics",
    # Fever
    "температура": "antipyretics",
    "треска": "antipyretics",
    # Respiratory/Cold
    "кашлица": "cough",
    "хрема": "decongestants",
    "настинка": "cough",
    "простуда": "cough",
    "грип": "antipyretics",
    # Throat
    "гърло": "throat",
    # Allergy
    "алергия": "antihistamines",
    "кихане": "antihistamines",
    "сърбеж": "antihistamines",
}

# English symptom keywords → treatment type mapping
# Used for translated queries and English symptom matching
EN_SYMPTOM_TO_TREATMENT = {
    # Digestive/GI
    "diarrhea": "antidiarrheal",
    "nausea": "digestive",
    "vomiting": "digestive",
    "stomach": "digestive",
    "heartburn": "antacids",
    "reflux": "antacids",
    "constipation": "laxatives",
    # Pain
    "pain": "analgesics",
    "headache": "analgesics",
    "migraine": "analgesics",
    # Fever
    "fever": "antipyretics",
    "temperature": "antipyretics",
    # Respiratory/Cold
    "cough": "cough",
    "runny nose": "decongestants",
    "cold": "cough",
    "flu": "antipyretics",
    # Throat
    "sore throat": "throat",
    "throat pain": "throat",
    # Allergy
    "allergy": "antihistamines",
    "sneezing": "antihistamines",
    "itching": "antihistamines",
}

# Combined mapping (Bulgarian + English)
SYMPTOM_TO_TREATMENT = {**BG_SYMPTOM_TO_TREATMENT, **EN_SYMPTOM_TO_TREATMENT}


def extract_treatment_from_query(query: str) -> str:
    """
    Extract treatment type from query by matching symptom keywords.

    Prioritizes GI symptoms (high misclassification rate) and uses exact
    keyword matching for reliability.

    Args:
        query: User query in Bulgarian or English

    Returns:
        Treatment type (e.g., "analgesics", "antidiarrheal") or empty string
    """
    query_lower = query.lower()

    # Priority 1: GI symptoms (often misclassified as cold/flu by LLM)
    gi_keywords = [
        "диария", "диарея", "diarrhea", "разстройство", "стомах",
        "коремна болка", "повръщане", "гадене", "nausea", "vomiting"
    ]
    if any(kw in query_lower for kw in gi_keywords):
        return "antidiarrheal"

    # Priority 2: Specific conditions
    if any(kw in query_lower for kw in ["запек", "constipation"]):
        return "laxatives"

    if any(kw in query_lower for kw in ["киселини", "heartburn", "рефлукс", "reflux", "стомашен сок"]):
        return "antacids"

    # Priority 3: General mapping (loop through all symptoms)
    for keyword, treatment in SYMPTOM_TO_TREATMENT.items():
        if keyword in query_lower:
            return treatment

    return ""


def get_symptom_keywords_for_treatment(treatment_type: str) -> list[str]:
    """
    Get all symptom keywords associated with a treatment type.

    Args:
        treatment_type: Treatment category (e.g., "analgesics")

    Returns:
        List of Bulgarian symptom keywords for this treatment
    """
    return [
        symptom
        for symptom, treatment in BG_SYMPTOM_TO_TREATMENT.items()
        if treatment == treatment_type
    ]


def is_symptom_keyword(word: str) -> bool:
    """
    Check if a word is a recognized symptom keyword.

    Args:
        word: Word to check

    Returns:
        True if word is in symptom mappings
    """
    return word.lower() in SYMPTOM_TO_TREATMENT
