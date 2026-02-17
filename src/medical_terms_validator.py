"""
Medical terminology validator for Bulgarian responses.

Detects and corrects common medical term translation issues:
- Gibberish translations (e.g., "сантиментални нарушения")
- Bad transliterations (e.g., "Гидит" instead of "Гингивит")
- Nonsensical medical phrases
"""

import re

from src.logging_config import get_logger

logger = get_logger("viapharma.medical_validator")


# Medical term glossary: English -> Correct Bulgarian
MEDICAL_TERMS_GLOSSARY = {
    # Common conditions
    "gingivitis": "гингивит",
    "periodontitis": "пародонтит",
    "pharyngitis": "фарингит",
    "laryngitis": "ларингит",
    "bronchitis": "бронхит",
    "sinusitis": "синузит",
    "otitis": "отит",
    "conjunctivitis": "конюнктивит",
    "dermatitis": "дерматит",
    "gastritis": "гастрит",
    # Symptoms
    "headache": "главоболие",
    "fever": "температура",
    "cough": "кашлица",
    "pain": "болка",
    "inflammation": "възпаление",
    "infection": "инфекция",
    "allergy": "алергия",
    # Common terms
    "viral infection": "вирусна инфекция",
    "bacterial infection": "бактериална инфекция",
    "allergic reaction": "алергична реакция",
    "gum disease": "заболяване на венците",
    "periodontal disease": "пародонтоза",
    "tooth decay": "зъбен кариес",
}

# Known bad translations to fix
BAD_TRANSLATIONS = {
    # Bad -> Correct
    "гидит": "гингивит",
    "фарингит": "фарингит",  # This is correct, but sometimes gets mangled
    "синусит": "синузит",
}

# Gibberish patterns to detect and remove
GIBBERISH_PATTERNS = [
    # Nonsensical combinations
    r"сантиментални?\s+\w+",  # "sentimental X"
    r"емоционални?\s+нарушения",  # "emotional disorders" (in wrong context)
    r"психологически\s+проблеми",  # "psychological problems" (when discussing physical symptoms)
    # Garbled words (detect patterns of mixed Latin/Cyrillic)
    r"\b[а-яА-Я]*[a-zA-Z]+[а-яА-Я]+\b",  # Mixed scripts in one word
    r"\b[a-zA-Z]+[а-яА-Я]+[a-zA-Z]+\b",
]

# Suspicious phrases that indicate hallucination
SUSPICIOUS_PHRASES = [
    "сантиментални нарушения",
    "емоционални разстройства",
    "психологически симптоми",
    "ментални проблеми",
    # Add more as discovered
]


class MedicalTermsValidator:
    """Validates and corrects medical terminology in Bulgarian responses."""

    def __init__(self):
        self.corrections_made = 0
        self.warnings_logged = 0

    def validate_and_correct(self, text: str, context: str = "response") -> tuple[str, list[str]]:
        """
        Validate medical terms in text and correct if possible.

        Args:
            text: Bulgarian text to validate
            context: Context for logging (e.g., "likely_cause", "explanation")

        Returns:
            Tuple of (corrected_text, list_of_issues_found)
        """
        if not text:
            return text, []

        issues = []
        corrected = text

        # Step 1: Fix known bad translations
        for bad, good in BAD_TRANSLATIONS.items():
            if bad in corrected.lower():
                # Case-insensitive replacement while preserving case
                pattern = re.compile(re.escape(bad), re.IGNORECASE)
                before = corrected
                corrected = pattern.sub(good, corrected)
                if before != corrected:
                    issues.append(f"Corrected '{bad}' → '{good}'")
                    self.corrections_made += 1
                    logger.info(f"Medical term corrected in {context}: '{bad}' → '{good}'")

        # Step 2: Detect suspicious phrases
        for phrase in SUSPICIOUS_PHRASES:
            if phrase.lower() in corrected.lower():
                issues.append(f"Suspicious medical phrase detected: '{phrase}'")
                self.warnings_logged += 1
                logger.warning(f"Suspicious phrase in {context}: '{phrase}'")

                # Try to remove nonsensical phrases
                # Remove the phrase and surrounding punctuation
                pattern = re.compile(r"[,;]?\s*" + re.escape(phrase) + r"\s*[,;]?", re.IGNORECASE)
                before = corrected
                corrected = pattern.sub("", corrected)

                # Clean up double spaces and punctuation
                corrected = re.sub(r"\s+", " ", corrected)
                corrected = re.sub(r"\s*,\s*,\s*", ", ", corrected)  # Double commas
                corrected = re.sub(r"^\s*,\s*", "", corrected)  # Leading comma
                corrected = re.sub(r"\s*,\s*$", "", corrected)  # Trailing comma

                if before != corrected:
                    issues.append(f"Removed suspicious phrase: '{phrase}'")
                    logger.info(f"Removed suspicious phrase from {context}: '{phrase}'")

        # Step 3: Detect gibberish patterns
        for pattern in GIBBERISH_PATTERNS:
            matches = re.findall(pattern, corrected, re.IGNORECASE)
            if matches:
                for match in matches:
                    issues.append(f"Potential gibberish detected: '{match}'")
                    self.warnings_logged += 1
                    logger.warning(f"Potential gibberish in {context}: '{match}'")

        # Step 4: Check for mixed script (Latin + Cyrillic in medical terms)
        # This often indicates translation failure
        mixed_script = re.findall(r"\b[а-яА-Я]+[a-zA-Z]+\b|\b[a-zA-Z]+[а-яА-Я]+\b", corrected)
        if mixed_script:
            for word in mixed_script:
                # Exclude intentional mixed words (brand names, etc.)
                if len(word) > 3 and not self._is_brand_name(word):
                    issues.append(f"Mixed script word (possible error): '{word}'")
                    logger.warning(f"Mixed script in {context}: '{word}'")

        # Final cleanup
        corrected = corrected.strip()

        return corrected, issues

    def _is_brand_name(self, word: str) -> bool:
        """Check if word is likely a brand name (intentional mixed script)."""
        # Common patterns for brand names
        brand_patterns = [
            r"^[A-Z][a-z]+$",  # Capitalized Latin word (e.g., Aspirin)
            r"^\d+",  # Starts with number
        ]
        for pattern in brand_patterns:
            if re.match(pattern, word):
                return True
        return False

    def validate_medical_reasoning(self, reasoning_dict: dict) -> dict:
        """
        Validate all text fields in medical reasoning dictionary.

        Args:
            reasoning_dict: Dictionary with medical reasoning fields

        Returns:
            Corrected dictionary with issues logged
        """
        if not reasoning_dict:
            return reasoning_dict

        corrected = reasoning_dict.copy()
        all_issues = []

        # Fields to validate
        text_fields = [
            "likely_cause",
            "explanation",
            "treatment_type",
            "how_it_helps",
            "duration_guidance",
        ]

        for field in text_fields:
            if field in corrected and corrected[field]:
                corrected_text, issues = self.validate_and_correct(corrected[field], context=field)
                corrected[field] = corrected_text
                if issues:
                    all_issues.extend([(field, issue) for issue in issues])

        # Validate lists
        list_fields = [
            "symptoms",
            "warnings",
            "self_care_tips",
        ]

        for field in list_fields:
            if field in corrected and corrected[field]:
                corrected_list = []
                for i, item in enumerate(corrected[field]):
                    corrected_text, issues = self.validate_and_correct(item, context=f"{field}[{i}]")
                    corrected_list.append(corrected_text)
                    if issues:
                        all_issues.extend([(f"{field}[{i}]", issue) for issue in issues])
                corrected[field] = corrected_list

        # Log summary if issues found
        if all_issues:
            logger.info(
                f"Medical validation completed: {len(all_issues)} issues found/corrected", extra={"issues": all_issues}
            )

        return corrected

    def get_stats(self) -> dict:
        """Get validation statistics."""
        return {
            "corrections_made": self.corrections_made,
            "warnings_logged": self.warnings_logged,
        }


# Global validator instance
_validator: MedicalTermsValidator | None = None


def get_medical_validator() -> MedicalTermsValidator:
    """Get or create the global medical terms validator."""
    global _validator
    if _validator is None:
        _validator = MedicalTermsValidator()
    return _validator
