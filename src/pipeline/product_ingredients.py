"""
Product ingredient utilities for the ViaPharma pipeline.

Contains active ingredient recognition patterns, treatment mappings,
and extraction helpers for product composition and contraindications.
"""

import re

# =============================================================================
# ACTIVE INGREDIENT RECOGNITION
# =============================================================================
# Maps canonical ingredient names to recognition patterns (BG/EN/brand names)

INGREDIENT_PATTERNS_GLOBAL = {
    "ibuprofen": ["ибупрофен", "ibuprofen", "нурофен", "бруфен", "advil"],
    "paracetamol": ["парацетамол", "paracetamol", "acetaminophen", "панадол", "ефералган", "tylenol"],
    "aspirin": ["аспирин", "aspirin", "ацетилсалицилова"],
    "diclofenac": ["диклофенак", "diclofenac", "волтарен"],
    "naproxen": ["напроксен", "naproxen", "налгезин"],
    "loratadine": ["лоратадин", "loratadine", "кларитин"],
    "cetirizine": ["цетиризин", "cetirizine", "зиртек"],
    "fexofenadine": ["фексофенадин", "fexofenadine"],
    "omeprazole": ["омепразол", "omeprazole"],
    "pantoprazole": ["пантопразол", "pantoprazole"],
    "dextromethorphan": ["декстрометорфан", "dextromethorphan"],
    "pseudoephedrine": ["псевдоефедрин", "pseudoephedrine", "фенилефрин", "phenylephrine"],
    "loperamide": ["лоперамид", "loperamide", "имодиум"],
    "smectite": ["смектит", "смекта", "smectite", "smecta"],
    "dexpanthenol": ["декспантенол", "dexpanthenol", "пантенол", "panthenol"],
    "metamizole": ["метамизол", "аналгин", "analgin", "metamizole"],
    "azithromycin": ["азитромицин", "azithromycin"],
    "benzydamine": ["бензидамин", "benzydamine", "тантум"],
    "domperidone": ["домперидон", "domperidone", "мотилиум"],
    "guaifenesin": ["гвайфенезин", "guaifenesin"],
}

# Treatment type → recommended active ingredients (pharmacist logic)
# Aspirin and metamizole excluded from default lists (contraindicated for children).
TREATMENT_TO_INGREDIENTS = {
    # Pain relief
    "analgesics": ["paracetamol", "ibuprofen"],
    "pain": ["paracetamol", "ibuprofen"],
    "headache": ["paracetamol", "ibuprofen"],
    "migraine": ["paracetamol", "ibuprofen"],
    "toothache": ["paracetamol", "ibuprofen"],
    # Fever
    "antipyretics": ["paracetamol", "ibuprofen"],
    "fever": ["paracetamol", "ibuprofen"],
    "temperature": ["paracetamol", "ibuprofen"],
    # Respiratory
    "cough": ["dextromethorphan"],
    "decongestants": ["pseudoephedrine"],
    "cold": ["paracetamol", "pseudoephedrine"],
    "flu": ["paracetamol", "pseudoephedrine"],
    "nasal_congestion": ["pseudoephedrine"],
    # Allergy
    "antihistamines": ["loratadine", "cetirizine"],
    "allergy": ["loratadine", "cetirizine"],
    "allergic_rhinitis": ["loratadine", "cetirizine"],
    # Digestive
    "antacids": ["omeprazole", "pantoprazole"],
    "digestive": ["omeprazole", "pantoprazole"],
    "heartburn": ["omeprazole", "pantoprazole"],
    "acid_reflux": ["omeprazole", "pantoprazole"],
    "indigestion": ["omeprazole", "pantoprazole"],
    "antidiarrheal": ["loperamide", "smectite"],
    "diarrhea": ["loperamide", "smectite"],
    # Topical
    "topical": ["dexpanthenol", "diclofenac"],
    "muscle_pain": ["diclofenac"],
    "joint_pain": ["diclofenac"],
    "skin": ["dexpanthenol"],
    # Other
    "throat": [],
    "sore_throat": [],
    "laxatives": [],
    "constipation": [],
    "vitamins": [],
    "supplements": [],
}

# Bulgarian display name for known ingredients (fallback; prefer product's own Състав)
INGREDIENT_BG_NAMES = {
    "paracetamol": "парацетамол",
    "ibuprofen": "ибупрофен",
    "aspirin": "аспирин",
    "diclofenac": "диклофенак",
    "naproxen": "напроксен",
    "loratadine": "лоратадин",
    "cetirizine": "цетиризин",
    "fexofenadine": "фексофенадин",
    "omeprazole": "омепразол",
    "pantoprazole": "пантопразол",
    "dextromethorphan": "декстрометорфан",
    "pseudoephedrine": "псевдоефедрин/фенилефрин",
    "loperamide": "лоперамид",
    "smectite": "смектит",
    "dexpanthenol": "декспантенол",
    "metamizole": "метамизол (аналгин)",
    "azithromycin": "азитромицин",
    "benzydamine": "бензидамин",
    "domperidone": "домперидон",
    "guaifenesin": "гвайфенезин",
}


def _get_product_text(product) -> str:
    """Get combined searchable text from product composition and title."""
    composition = (product.composition or "").lower()
    title = (product.title or "").lower()
    return f"{composition} {title}"


def extract_all_product_ingredients(product) -> list[str]:
    """Extract ALL active ingredients from product (for combination product detection)."""
    combined = _get_product_text(product)
    return [
        ingredient
        for ingredient, patterns in INGREDIENT_PATTERNS_GLOBAL.items()
        if any(pattern in combined for pattern in patterns)
    ]


def extract_product_ingredient(product) -> str:
    """Extract primary active ingredient from product.composition and product.title."""
    ingredients = extract_all_product_ingredients(product)
    return ingredients[0] if ingredients else ""


def is_combination_product(product) -> bool:
    """Check if product contains multiple active ingredients."""
    return len(extract_all_product_ingredients(product)) >= 2


def extract_composition_summary(product) -> str:
    """
    Extract a short composition summary from the product's own Състав field.
    Returns the first meaningful line, cleaned up. Data-driven, not hardcoded.
    """
    comp = (product.composition or "").strip()
    if not comp or len(comp) < 3:
        return ""
    first_sentence = comp.split(".")[0].strip()
    if len(first_sentence) > 150:
        first_sentence = first_sentence[:147] + "..."
    return first_sentence


def extract_contraindication_summary(product) -> str:
    """
    Extract the most important contraindication warning from product's own
    Противопоказания field. Returns a short (max ~200 char) safety excerpt.
    """
    contra = (product.contraindications or "").strip()
    if not contra or len(contra) < 10:
        return ""

    priority_phrases = [
        "не приемайте",
        "не прилагайте",
        "не използвайте",
        "избягвайте",
        "противопоказан",
        "не се препоръчва",
        "алергични",
        "свръхчувствител",
        "бременн",
        "кърм",
        "деца под",
        "не давайте",
        "стомашн",
        "язва",
        "бъбреч",
        "сърдечн",
        "кръвно налягане",
        "черен дроб",
        "диабет",
        "не комбинирайте",
        "не превишавайте",
        "максималн",
    ]

    sentences = re.split(r"[.;!]", contra)
    relevant = []
    for sentence in sentences:
        s = sentence.strip()
        if not s or len(s) < 10:
            continue
        s_lower = s.lower()
        if any(
            skip in s_lower
            for skip in [
                "съхранявайте",
                "срока на годност",
                "недостъпно за деца",
                "сухо и прохладно",
                "слънчева светлина",
                "прочетете внимателно",
            ]
        ):
            continue
        if any(phrase in s_lower for phrase in priority_phrases):
            relevant.append(s)

    if not relevant:
        for sentence in sentences:
            s = sentence.strip()
            if len(s) > 15 and not any(
                skip in s.lower()
                for skip in [
                    "съхранявайте",
                    "срока на годност",
                    "недостъпно",
                ]
            ):
                relevant.append(s)
                break

    if not relevant:
        return ""

    result = ". ".join(relevant[:2])
    if len(result) > 200:
        result = result[:197] + "..."
    return result


def build_ingredient_duplication_warning(product, ingredient: str) -> str:
    """Build ingredient duplication warning using the product's own data."""
    if not ingredient:
        return ""

    comp = (product.composition or "").strip()
    bg_name = INGREDIENT_BG_NAMES.get(ingredient, "")

    if not bg_name:
        for pattern in INGREDIENT_PATTERNS_GLOBAL.get(ingredient, []):
            if pattern in comp.lower():
                bg_name = pattern
                break

    if bg_name:
        return f"Този продукт съдържа **{bg_name}**. Не комбинирайте с други лекарства, съдържащи {bg_name}."
    return ""


def get_recommended_ingredients(treatment_type: str) -> list[str]:
    """Get recommended ingredients for a treatment type."""
    if not treatment_type:
        return []
    tt = treatment_type.lower().strip()

    # Direct match
    if tt in TREATMENT_TO_INGREDIENTS:
        return TREATMENT_TO_INGREDIENTS[tt]

    # Partial match (substring in either direction)
    return next((ingredients for key, ingredients in TREATMENT_TO_INGREDIENTS.items() if key in tt or tt in key), [])
