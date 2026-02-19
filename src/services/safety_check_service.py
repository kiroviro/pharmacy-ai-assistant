"""
Safety Check Service.

Handles safety validation and warning generation:
- Red-flag symptom detection requiring professional medical attention
- Safety layer integration for emergency detection
- Query-specific safety handling (child, pregnancy, drug interactions)
- User condition management and contraindication filtering
"""

from src.logging_config import get_logger
from src.medical_model import MedicalReasoning

logger = get_logger("viapharma.services.safety_check")


class SafetyCheckService:
    """
    Service for safety checking and warning generation.

    Responsibilities:
    - Check for red-flag symptoms requiring professional care
    - Integrate with SafetyLayer for emergency detection
    - Handle query-specific safety concerns (child, pregnancy, etc.)
    - Manage user conditions and contraindications
    """

    # Condition name translations for user-friendly messages
    CONDITION_NAMES_BG = {
        "pregnancy": "бременност",
        "breastfeeding": "кърмене",
        "child": "деца",
        "elderly": "възрастни хора",
        "diabetes": "диабет",
        "heart": "сърдечни заболявания",
        "kidney": "бъбречни проблеми",
        "liver": "чернодробни проблеми",
        "allergy": "алергии",
        "stomach": "стомашни проблеми",
        "asthma": "астма",
    }

    def __init__(
        self,
        safety_layer=None,
        safety_validator=None,
        medical_reasoning_service=None,
    ):
        """
        Initialize SafetyCheckService.

        Args:
            safety_layer: Optional SafetyLayer instance for emergency detection
            safety_validator: Optional SafetyValidator instance for filtering
            medical_reasoning_service: Optional MedicalReasoningService for query classification
        """
        self.safety_layer = safety_layer
        self.safety_validator = safety_validator
        self.medical_reasoning_service = medical_reasoning_service

    def check_safety(
        self,
        original_query: str,
        translated_query: str,
        medical_reasoning: MedicalReasoning,
    ) -> tuple[bool, str]:
        """
        Check for red-flag symptoms requiring professional medical attention.

        Checks both original Bulgarian and translated English text for safety patterns,
        plus MedGemma's see_doctor recommendation.

        Args:
            original_query: Original Bulgarian user query
            translated_query: Translated English query
            medical_reasoning: MedicalReasoning object from medical model

        Returns:
            Tuple of (is_red_flag, message):
            - is_red_flag=True means STOP and return safety message (no products)
            - is_red_flag=False means CONTINUE with product search (may still add warnings later)
        """
        if not self.safety_layer:
            logger.warning("SafetyLayer not available, skipping safety checks")
            return False, ""

        # Check original Bulgarian text for actual emergencies
        result = self.safety_layer.check_safety(original_query)
        if result.is_red_flag:
            logger.warning(
                f"Red flag detected in original query: {original_query[:50]}..."
            )
            return True, result.message

        # Check translated English text for actual emergencies
        result_en = self.safety_layer.check_safety(translated_query)
        if result_en.is_red_flag:
            logger.warning(
                f"Red flag detected in translated query: {translated_query[:50]}..."
            )
            return True, result_en.message

        # For MedGemma's see_doctor recommendation, handle differently based on query type
        if medical_reasoning.see_doctor:
            # For child-related queries, DON'T block - continue to find products
            # but add pediatric warnings (handled by add_child_disclaimer later)
            if self.is_child_query(original_query):
                logger.info(
                    "Child query with see_doctor=True - proceeding with pediatric warnings"
                )
                return False, ""  # Continue to product search

            # For pregnancy-related queries, DON'T block - continue with warnings
            if self.is_pregnancy_query(original_query):
                logger.info(
                    "Pregnancy query with see_doctor=True - proceeding with warnings"
                )
                return False, ""  # Continue to product search

            # For drug combination/interaction queries, DON'T block - these are valid OTC questions
            # (e.g., "Can I take ibuprofen with paracetamol?")
            if self.is_drug_combination_query(original_query):
                logger.info(
                    "Drug combination query with see_doctor=True - proceeding with info"
                )
                return False, ""  # Continue to provide helpful information

            # For substitute/alternative queries, DON'T block - search for OTC alternatives
            # (e.g., "Generic substitute for Aulin", "Алтернатива на нимезулид")
            if self.is_substitute_query(original_query):
                logger.info(
                    "Substitute query with see_doctor=True - proceeding to find OTC alternatives"
                )
                return False, ""  # Continue to find OTC alternatives

            # For other queries, use the generic doctor recommendation
            logger.info(
                "General see_doctor=True - returning doctor recommendation message"
            )
            return True, (
                "⚠️ **Препоръчваме консултация с лекар.**\n\n"
                "Базирано на вашите симптоми, препоръчваме да се консултирате "
                "с медицински специалист за правилна диагноза и лечение."
            )

        # No red flags detected
        return False, ""

    def is_child_query(self, text: str) -> bool:
        """
        Check if query is child-related.

        Delegates to SafetyValidator if available.

        Args:
            text: User query text

        Returns:
            True if query is child-related
        """
        if self.safety_validator:
            return self.safety_validator.is_child_related_query(text)

        # Fallback to basic keyword check
        text_lower = text.lower()
        child_keywords = ["дете", "бебе", "child", "baby", "деца"]
        return any(kw in text_lower for kw in child_keywords)

    def is_pregnancy_query(self, text: str) -> bool:
        """
        Check if query is pregnancy-related.

        Delegates to MedicalReasoningService if available.

        Args:
            text: User query text

        Returns:
            True if query is pregnancy-related
        """
        if self.medical_reasoning_service:
            return self.medical_reasoning_service.is_pregnancy_related_query(text)

        # Fallback to basic keyword check
        text_lower = text.lower()
        pregnancy_keywords = ["бременна", "кърмене", "pregnancy", "breastfeeding"]
        return any(kw in text_lower for kw in pregnancy_keywords)

    def is_drug_combination_query(self, text: str) -> bool:
        """
        Check if query is about drug combinations.

        Delegates to MedicalReasoningService if available.

        Args:
            text: User query text

        Returns:
            True if query is about drug combinations
        """
        if self.medical_reasoning_service:
            return self.medical_reasoning_service.is_drug_combination_query(text)

        # Fallback to basic keyword check
        text_lower = text.lower()
        combination_keywords = ["заедно с", "together with", "може ли да взема"]
        return any(kw in text_lower for kw in combination_keywords)

    def is_substitute_query(self, text: str) -> bool:
        """
        Check if query is about substitutes/alternatives.

        Delegates to MedicalReasoningService if available.

        Args:
            text: User query text

        Returns:
            True if query is about substitutes
        """
        if self.medical_reasoning_service:
            return self.medical_reasoning_service.is_substitute_query(text)

        # Fallback to basic keyword check
        text_lower = text.lower()
        substitute_keywords = ["заместител", "алтернатива", "substitute", "alternative"]
        return any(kw in text_lower for kw in substitute_keywords)

    def get_condition_name_bulgarian(self, condition_key: str) -> str:
        """
        Get Bulgarian translation for condition name.

        Args:
            condition_key: Condition key (e.g., "pregnancy", "diabetes")

        Returns:
            Bulgarian translation or original key if not found
        """
        return self.CONDITION_NAMES_BG.get(condition_key, condition_key)

    def add_contraindication_warning(
        self,
        response: str,
        contraindicated_products: list[tuple],
        user_conditions: list[str],
    ) -> str:
        """
        Add contraindication warning to response.

        Note: Contraindication info is now part of the product card warnings
        and the safety block in the main template. No extra block appended.

        Args:
            response: Original response text
            contraindicated_products: List of (product, condition) tuples
            user_conditions: List of user medical conditions

        Returns:
            Response (unchanged - warnings are in template)
        """
        # Contraindication info is now part of the product card warnings
        # and the safety block in the main template. No extra block appended.
        return response


# Singleton instance
_safety_check_service = None


def get_safety_check_service(
    safety_layer=None,
    safety_validator=None,
    medical_reasoning_service=None,
) -> SafetyCheckService:
    """
    Get or create the SafetyCheckService singleton.

    Args:
        safety_layer: Optional SafetyLayer instance
        safety_validator: Optional SafetyValidator instance
        medical_reasoning_service: Optional MedicalReasoningService instance

    Returns:
        SafetyCheckService instance
    """
    global _safety_check_service
    if _safety_check_service is None:
        _safety_check_service = SafetyCheckService(
            safety_layer=safety_layer,
            safety_validator=safety_validator,
            medical_reasoning_service=medical_reasoning_service,
        )
    return _safety_check_service
