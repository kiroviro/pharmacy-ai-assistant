"""
Constants for the ViaPharma pipeline.

Contains keyword patterns for condition extraction, contraindication detection,
and catalog query identification.
"""

import re

# =============================================================================
# USER CONDITION EXTRACTION PATTERNS
# =============================================================================
# Maps user mentions to standardized condition identifiers

USER_CONDITION_PATTERNS = {
    # Pregnancy
    "pregnancy": [
        "бременна", "бременност", "pregnant", "pregnancy",
        "чакам бебе", "очаквам бебе", "expecting",
    ],
    # Breastfeeding
    "breastfeeding": [
        "кърмя", "кърмене", "кърмеща", "breastfeeding", "nursing",
        "кърмачка", "lactating",
    ],
    # Children
    "child": [
        "дете", "деца", "детето", "бебе", "child", "children", "kid",
        "малък", "малка", "infant", "toddler", "pediatric",
        r"\b[1-9]\s*годин", r"\b[1-9]\s*месец", r"\b[1-9]\s*year",
    ],
    # Elderly
    "elderly": [
        "възрастен", "пенсионер", "elderly", "senior",
        r"\b[789]\d\s*годин", "над 65", "over 65",
    ],
    # Diabetes
    "diabetes": [
        "диабет", "диабетик", "diabetes", "diabetic",
        "кръвна захар", "blood sugar", "инсулин",
    ],
    # Heart conditions
    "heart": [
        "сърце", "сърдечен", "heart", "cardiac",
        "кръвно налягане", "blood pressure", "хипертония", "hypertension",
        "аритмия", "arrhythmia",
    ],
    # Kidney issues
    "kidney": [
        "бъбрек", "бъбречен", "kidney", "renal",
        "бъбречна недостатъчност", "kidney failure",
    ],
    # Liver issues
    "liver": [
        "черен дроб", "чернодробен", "liver", "hepatic",
        "хепатит", "hepatitis",
    ],
    # Allergies
    "allergy": [
        "алергия", "алергичен", "allergy", "allergic",
        "непоносимост", "intolerance",
    ],
    # Stomach/GI issues
    "stomach": [
        "стомах", "язва", "гастрит", "stomach", "ulcer", "gastritis",
        "стомашни проблеми", "киселини",
    ],
    # Asthma
    "asthma": [
        "астма", "asthma", "астматик",
    ],
}


# =============================================================================
# CONTRAINDICATION PATTERNS
# =============================================================================
# Maps conditions to contraindication keywords to look for in product data

CONTRAINDICATION_KEYWORDS = {
    "pregnancy": [
        # Bulgarian variations (all grammatical forms)
        "бременност", "бременни", "бременна", "бременността",
        "през бременност", "по време на бременност",
        "в бременност", "при бременност",
        # English
        "pregnant", "pregnancy",
    ],
    "breastfeeding": [
        # Bulgarian variations
        "кърмене", "кърменето", "кърмачки", "кърмещи", "кърмачка",
        "през кърмене", "по време на кърмене", "при кърмене",
        # English
        "breastfeeding", "lactation", "nursing",
    ],
    "child": [
        # Bulgarian - age restrictions
        "деца под", "деца до", "деца на възраст под",
        "не се препоръчва за деца", "не давайте на деца",
        "под 12 години", "под 6 години", "под 2 години",
        "на възраст под",
        # English
        "children under", "pediatric", "not for children",
    ],
    "elderly": [
        "възрастни хора", "пациенти в старческа възраст",
        "над 65", "elderly", "старческа възраст",
    ],
    "diabetes": [
        "диабет", "диабетици", "захарен диабет",
        "diabetes", "diabetic", "кръвна захар",
    ],
    "heart": [
        "сърдечна недостатъчност", "сърдечни заболявания",
        "сърдечно-съдови", "сърдечен",
        "heart disease", "cardiac", "cardiovascular",
        "хипертония", "високо кръвно", "кръвно налягане",
    ],
    "kidney": [
        "бъбречна недостатъчност", "бъбречни заболявания",
        "бъбречна функция", "бъбречни проблеми",
        "kidney disease", "renal impairment", "renal failure",
    ],
    "liver": [
        "чернодробна недостатъчност", "чернодробни заболявания",
        "чернодробна функция", "чернодробни проблеми",
        "liver disease", "hepatic impairment", "hepatic failure",
    ],
    "allergy": [
        "свръхчувствителност", "алергия към", "алергични реакции",
        "алергични", "непоносимост",
        "hypersensitivity", "allergic to", "allergy",
    ],
    "stomach": [
        "стомашна язва", "пептична язва", "гастрит",
        "язви", "стомашни проблеми", "стомашно-чревни",
        "stomach ulcer", "peptic ulcer", "gastritis", "GI bleeding",
    ],
    "asthma": [
        "астма", "астматик", "бронхоспазъм", "бронхиална астма",
        "asthma", "bronchospasm", "asthmatic",
    ],
}


# =============================================================================
# CATALOG QUERY PATTERNS
# =============================================================================
# Patterns to detect catalog/product listing queries (skip medical reasoning)

CATALOG_PATTERNS_BG = [
    # "What brands of X do you have/offer?"
    re.compile(r'какви\s+марки?\s+.+\s+(имате|предлагате|продавате)', re.IGNORECASE),
    re.compile(r'какви\s+.+\s+марки?\s+(имате|предлагате|продавате)', re.IGNORECASE),
    # "Show me X" / "I'm looking for X"
    re.compile(r'^покажи\s+(ми\s+)?', re.IGNORECASE),
    re.compile(r'^търся\s+', re.IGNORECASE),
    # "Do you have X?"
    re.compile(r'^имате\s+ли\s+', re.IGNORECASE),
    re.compile(r'^предлагате\s+ли\s+', re.IGNORECASE),
    re.compile(r'^продавате\s+ли\s+', re.IGNORECASE),
    # "What X do you have?"
    re.compile(r'^какви?\s+.+\s+(имате|предлагате)\s*\??$', re.IGNORECASE),
    # "List of X" / "All X"
    re.compile(r'^списък\s+(с|на)\s+', re.IGNORECASE),
    re.compile(r'^всички\s+', re.IGNORECASE),
    # Brand-specific queries
    re.compile(r'^продукти\s+(на|от)\s+', re.IGNORECASE),
]

CATALOG_PATTERNS_EN = [
    re.compile(r'what\s+brands?\s+of\s+.+\s+(do you have|do you offer|are available)', re.IGNORECASE),
    re.compile(r'^show\s+me\s+', re.IGNORECASE),
    re.compile(r'^looking\s+for\s+', re.IGNORECASE),
    re.compile(r'^do\s+you\s+(have|sell|offer)\s+', re.IGNORECASE),
    re.compile(r'^list\s+(of\s+)?', re.IGNORECASE),
    re.compile(r'^all\s+.+\s+products', re.IGNORECASE),
]

# Product categories that indicate catalog queries (no symptoms)
CATALOG_CATEGORIES = {
    # Bulgarian - cosmetics/skincare
    'слънцезащитн', 'крем', 'кремове', 'лосион', 'шампоан', 'паста за зъби',
    'дезодорант', 'парфюм', 'козметика', 'грижа за кожа', 'грижа за коса',
    'серум', 'маска за лице', 'балсам', 'гел за душ', 'сапун',
    # Bulgarian - baby/hygiene
    'бебешки продукти', 'памперси', 'мокри кърпички', 'превръзки',
    # Bulgarian - supplements (non-symptom queries)
    'витамини', 'хранителни добавки', 'протеин', 'колаген', 'омега',
    # Bulgarian - medical devices
    'термометър', 'тонометър', 'глюкомер', 'инхалатор',
    # English equivalents
    'sunscreen', 'cream', 'lotion', 'shampoo', 'toothpaste',
    'deodorant', 'perfume', 'cosmetics', 'skincare', 'haircare',
    'diapers', 'wipes', 'bandages', 'vitamins', 'supplements',
}


# =============================================================================
# CHILD-RELATED DETECTION KEYWORDS
# =============================================================================
# Keywords that indicate a query is about children, babies, or pediatric care

CHILD_KEYWORDS = {
    # Bulgarian - babies
    'бебе', 'бебета', 'бебешки', 'бебешка', 'бебето',
    # Bulgarian - children
    'дете', 'деца', 'детски', 'детска', 'детето',
    # Bulgarian - age terms
    'новородено', 'кърмаче', 'малко дете',
    'месечно', 'годишно', 'месеца', 'години',
    # Bulgarian - medical
    'педиатър', 'педиатричен',
    'никнене на зъби', 'зъбки',
    'дозировка за дете', 'доза за дете',
    'за деца', 'за бебета',
    # English
    'baby', 'babies', 'infant', 'infants',
    'child', 'children', 'kid', 'kids',
    'toddler', 'newborn',
    'months old', 'years old',
    'pediatric', 'teething',
}


# =============================================================================
# MEDICATION SAFETY KEYWORDS
# =============================================================================
# Keywords that indicate a query about medication safety, dosage, or interactions

SAFETY_KEYWORDS = {
    # Bulgarian - dosing
    'двойна доза', 'тройна доза', 'предозиране', 'предозирах',
    'максимална доза', 'максималната доза', 'колко мога да взема',
    'прекалено много', 'твърде много',
    # Bulgarian - interactions
    'алкохол с', 'пия алкохол', 'комбинирам', 'смесвам',
    'взема заедно', 'едновременно',
    # Bulgarian - safety questions
    'безопасно ли е', 'опасно ли е', 'вредно ли е',
    'странични ефекти', 'странични действия', 'нежелани реакции',
    'противопоказания', 'да не взема',
    # Bulgarian - pregnancy/breastfeeding
    'по време на бременност', 'бременна', 'кърмене', 'кърмя',
    # English
    'double dose', 'overdose', 'maximum dose',
    'alcohol with', 'combine', 'mix medications',
    'safe to take', 'dangerous', 'harmful',
    'side effects', 'contraindications',
    'during pregnancy', 'pregnant', 'breastfeeding',
}


# =============================================================================
# CHRONIC DISEASE KEYWORDS
# =============================================================================
# Keywords indicating queries about chronic conditions (often require prescriptions)

CHRONIC_DISEASE_KEYWORDS = {
    # Bulgarian - diabetes
    'диабет', 'диабетик', 'захарен диабет', 'инсулин',
    'кръвна захар', 'глюкоза',
    # Bulgarian - thyroid
    'щитовидна', 'щитовидната жлеза', 'тироксин',
    'хипотиреоидизъм', 'хипертиреоидизъм',
    # Bulgarian - cardiovascular
    'хипертония', 'високо кръвно', 'кръвно налягане',
    'сърдечна недостатъчност', 'аритмия',
    'холестерол', 'статини',
    # Bulgarian - respiratory
    'астма', 'бронхиална астма', 'хобб',
    # Bulgarian - neurological
    'епилепсия', 'паркинсон', 'множествена склероза',
    # Bulgarian - mental health
    'антидепресант', 'антипсихотик', 'шизофрения',
    # Bulgarian - autoimmune
    'ревматоиден артрит', 'лупус', 'имуносупресор',
    # English
    'diabetes', 'insulin', 'blood sugar',
    'thyroid', 'hypothyroidism', 'hyperthyroidism',
    'hypertension', 'blood pressure',
    'asthma', 'copd',
    'epilepsy', 'parkinson',
    'antidepressant', 'antipsychotic',
}
