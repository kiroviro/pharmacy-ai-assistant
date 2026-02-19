"""
Medical Reasoning Service.

Handles all medical analysis and reasoning logic:
- Medical reasoning extraction and validation
- Query classification (pregnancy, drug combination, substitute, etc.)
- Symptom validation and treatment type extraction
- Recommended ingredients and treatment actions
"""

from src.logging_config import get_logger
from src.medical_model import MedicalReasoning
from src.pipeline.product_ingredients import get_recommended_ingredients
from src.unified_processor import UnifiedProcessorResult

logger = get_logger("viapharma.services.medical_reasoning")


class MedicalReasoningService:
    """
    Service for medical reasoning and analysis.

    Responsibilities:
    - Extract and validate medical reasoning from text
    - Classify query types (pregnancy, drug combination, substitute)
    - Validate symptoms against original query
    - Provide treatment recommendations and ingredients
    """

    # Bulgarian symptom keywords → treatment type mapping
    # Used to validate/correct MedGemma's treatment_type
    BG_SYMPTOM_TO_TREATMENT = {
        # Digestive/GI symptoms - HIGH PRIORITY (often misclassified as cold/flu)
        "диария": "antidiarrheal",
        "разстройство": "antidiarrheal",
        "гадене": "digestive",
        "повръщане": "digestive",
        "стомах": "digestive",
        "стомашни": "digestive",
        "киселини": "antacids",
        "запек": "laxatives",
        "чревни": "digestive",
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

    # Brief action descriptions per treatment type (what the ingredients DO)
    TREATMENT_ACTION_TEXTS = {
        "analgesics": "Те блокират болковите сигнали и намаляват възпалението.",
        "antipyretics": "Те намаляват температурата и облекчават дискомфорта.",
        "cough": "Потиска кашличния рефлекс за спокоен сън.",
        "decongestants": "Намаляват отока на носната лигавица и улесняват дишането.",
        "antihistamines": "Блокират хистамина и намаляват алергичните реакции.",
        "antacids": "Намаляват стомашната киселинност и облекчават киселините.",
        "digestive": "Подобряват храносмилането и облекчават стомашния дискомфорт.",
        "antidiarrheal": "Забавят чревната перисталтика и намаляват загубата на течности.",
        "topical": "Действат локално за облекчаване на болката и възпалението.",
    }

    def __init__(self, medical_model=None, user_condition_patterns=None):
        """
        Initialize MedicalReasoningService.

        Args:
            medical_model: Optional medical model instance (defaults to singleton)
            user_condition_patterns: Optional user condition patterns (defaults to constants)
        """
        self.medical_model = medical_model
        self.user_condition_patterns = user_condition_patterns or {}

    def get_medical_reasoning(self, text: str) -> MedicalReasoning:
        """
        Use MedGemma to understand symptoms and suggest treatment categories.

        Includes fallback strategy for graceful degradation if model fails.

        Args:
            text: User input text

        Returns:
            MedicalReasoning object with symptoms, treatment type, etc.
        """
        if not self.medical_model:
            logger.warning("No medical model available, using fallback reasoning")
            return self.create_fallback_reasoning(text)

        try:
            return self.medical_model.get_medical_reasoning(text)
        except Exception as e:
            logger.error(f"MedGemma inference failed: {e}", exc_info=True)
            return self.create_fallback_reasoning(text)

    def create_fallback_reasoning(self, text: str) -> MedicalReasoning:
        """
        Create a safe fallback MedicalReasoning when MedGemma fails.

        Returns a conservative response that recommends consulting a pharmacist.

        Args:
            text: Original user input

        Returns:
            Fallback MedicalReasoning object
        """
        logger.warning("Using fallback medical reasoning due to model failure")

        # Extract basic symptoms from text using simple keyword detection
        symptom_keywords = {
            "headache": ["главоболие", "headache", "болка в главата"],
            "fever": ["температура", "fever", "треска"],
            "cough": ["кашлица", "cough"],
            "pain": ["болка", "pain", "боли"],
            "cold": ["настинка", "cold", "простуда"],
            "stomach": ["стомах", "stomach", "корем"],
            "throat": ["гърло", "throat"],
        }

        detected_symptoms = []
        text_lower = text.lower()
        for symptom, keywords in symptom_keywords.items():
            if any(kw in text_lower for kw in keywords):
                detected_symptoms.append(symptom)

        return MedicalReasoning(
            symptoms=detected_symptoms if detected_symptoms else ["described symptoms"],
            likely_cause="Unable to perform detailed analysis",
            treatment_type="general wellness products",
            warnings=[
                "Automated analysis unavailable - please consult a pharmacist",
                "If symptoms persist or worsen, see a doctor",
            ],
            see_doctor=False,
            explanation="Our medical analysis system is temporarily limited. "
            "We can show you general wellness products that may help.",
            how_treatment_helps="",
            self_care_tips=["Rest and stay hydrated", "Monitor your symptoms"],
            duration_guidance="Consult a pharmacist for personalized advice",
            user_conditions=[],
        )

    def build_medical_reasoning_from_unified(
        self, llm_result: UnifiedProcessorResult
    ) -> MedicalReasoning:
        """
        Convert UnifiedProcessorResult to MedicalReasoning for compatibility.

        Args:
            llm_result: Result from unified processor

        Returns:
            MedicalReasoning object
        """
        reasoning = llm_result.reasoning
        if not reasoning:
            return MedicalReasoning(
                symptoms=llm_result.extraction.symptoms,
                likely_cause="",
                treatment_type="",
                warnings=[],
                see_doctor=False,
            )

        return MedicalReasoning(
            symptoms=llm_result.extraction.symptoms,
            likely_cause=reasoning.explanation,
            treatment_type=reasoning.treatment_category,
            warnings=reasoning.warnings,
            see_doctor=reasoning.see_doctor,
            explanation=reasoning.explanation,
            how_treatment_helps="",
            self_care_tips=reasoning.self_care_tips,
            duration_guidance="",
            user_conditions=llm_result.extraction.user_conditions,
        )

    def is_refusal_response(self, reasoning: MedicalReasoning) -> bool:
        """
        Check if medical reasoning is a refusal (model declined to answer).

        Args:
            reasoning: MedicalReasoning object

        Returns:
            True if this is a refusal response
        """
        if not reasoning:
            return False

        # Check for refusal indicators
        refusal_keywords = {
            "cannot",
            "can't",
            "unable to",
            "not possible",
            "beyond my scope",
            "consult a doctor",
            "see a doctor immediately",
            "medical professional",
        }

        explanation_lower = (reasoning.explanation or "").lower()
        return any(keyword in explanation_lower for keyword in refusal_keywords)

    def is_pregnancy_related_query(self, text: str) -> bool:
        """
        Check if query mentions pregnancy or breastfeeding.

        Args:
            text: User input text

        Returns:
            True if query is pregnancy-related
        """
        text_lower = text.lower()
        pregnancy_patterns = self.user_condition_patterns.get("pregnancy", [])
        breastfeeding_patterns = self.user_condition_patterns.get("breastfeeding", [])
        all_patterns = pregnancy_patterns + breastfeeding_patterns
        return any(kw in text_lower for kw in all_patterns if not kw.startswith(r"\b"))

    def is_drug_combination_query(self, text: str) -> bool:
        """
        Check if query is about combining/taking multiple medications together.

        These are valid OTC questions like "Can I take ibuprofen with paracetamol?"

        Args:
            text: User input text

        Returns:
            True if query is about drug combinations
        """
        text_lower = text.lower()

        # Keywords indicating drug combination questions
        combination_keywords = {
            # Bulgarian
            "заедно с",
            "едновременно",
            "комбинирам",
            "комбиниране",
            "смесвам",
            "да взема с",
            "взема с",
            "приемам с",
            "може ли да взема",
            "мога ли да взема",
            "може ли да приема",
            "мога ли да приема",
            "да пия с",
            "пия с",
            "съчетавам",
            "съчетание",
            # English
            "together with",
            "at the same time",
            "combine",
            "combining",
            "mix",
            "mixing",
            "take with",
            "can i take",
            "can i combine",
        }

        return any(kw in text_lower for kw in combination_keywords)

    def is_substitute_query(self, text: str) -> bool:
        """
        Check if query is asking for a substitute/alternative/generic for a drug.

        These are valid questions like "Generic substitute for Aulin" or
        "Алтернатива на нимезулид" - user wants OTC options instead of prescription drug.

        Args:
            text: User input text

        Returns:
            True if query is about substitutes/alternatives
        """
        text_lower = text.lower()

        substitute_keywords = {
            # Bulgarian
            "заместител",
            "заместител на",
            "замести",
            "заместя",
            "алтернатива",
            "алтернатива на",
            "алтернативен",
            "генеричен",
            "генерик",
            "вместо",
            "подобен на",
            "подобно на",
            "като",
            "еквивалент",
            "аналог",
            "аналогичен",
            # English
            "substitute",
            "substitute for",
            "substitution",
            "alternative",
            "alternative to",
            "instead of",
            "generic",
            "generic for",
            "equivalent",
            "similar to",
            "like",
            "analog",
            "replacement",
        }

        return any(kw in text_lower for kw in substitute_keywords)

    def validate_symptoms_against_query(
        self, symptoms: list[str], original_query: str
    ) -> list[str]:
        """
        Validate detected symptoms against the original query.

        Filters out phantom symptoms that don't have any relation to the query.
        This prevents showing symptoms like "кашлица, хрема" for a query like "помощ".

        Args:
            symptoms: List of symptom strings (in English or Bulgarian)
            original_query: The original Bulgarian user query

        Returns:
            Filtered list of symptoms that are likely valid
        """
        if not symptoms or not original_query:
            return symptoms

        query_lower = original_query.lower()

        # If query has no recognizable symptom keywords, symptoms are likely phantom
        if not self.query_has_symptom_keywords(query_lower):
            # Only keep symptoms if they match known Bulgarian symptom words
            # This catches cases where the query IS about symptoms but uses different words
            valid_symptoms = []
            for symptom in symptoms:
                symptom_lower = symptom.lower()
                # Check if any keyword from our mapping appears in either the query or symptom
                for keyword in self.BG_SYMPTOM_TO_TREATMENT.keys():
                    if keyword in symptom_lower and keyword in query_lower:
                        valid_symptoms.append(symptom)
                        break
            return valid_symptoms

        # Query has symptom keywords, so keep all detected symptoms
        return symptoms

    def query_has_symptom_keywords(self, query: str) -> bool:
        """
        Check if the original query contains any recognizable symptom keywords.

        Used to validate whether MedGemma's detected symptoms are phantom or real.

        Args:
            query: Original query (should be lowercase)

        Returns:
            True if query contains symptom keywords
        """
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in self.BG_SYMPTOM_TO_TREATMENT.keys())

    def extract_treatment_from_query(self, query: str) -> str | None:
        """
        Extract treatment type from original Bulgarian query keywords.

        Used to validate/correct MedGemma's treatment_type when there's
        a mismatch between detected symptoms and recommended treatment.

        Args:
            query: Original Bulgarian query

        Returns:
            Treatment type string or None if no match
        """
        query_lower = query.lower()

        # Count symptom matches by treatment type
        treatment_scores = {}
        for keyword, treatment in self.BG_SYMPTOM_TO_TREATMENT.items():
            if keyword in query_lower:
                treatment_scores[treatment] = treatment_scores.get(treatment, 0) + 1

        if not treatment_scores:
            return None

        # Return treatment with highest score (most keyword matches)
        return max(treatment_scores, key=treatment_scores.get)

    def get_recommended_ingredients(self, treatment_type: str) -> list[str]:
        """
        Get recommended active ingredients for a treatment type.

        Args:
            treatment_type: Treatment type (e.g., "analgesics")

        Returns:
            List of recommended ingredient names
        """
        return get_recommended_ingredients(treatment_type)

    def get_treatment_action_text(self, treatment_type: str) -> str:
        """
        Get a brief explanation of what the recommended ingredients do.

        Args:
            treatment_type: Treatment type (e.g., "analgesics")

        Returns:
            Bulgarian text explaining how the treatment works
        """
        if not treatment_type:
            return ""

        tt = treatment_type.lower().strip()

        # Direct match
        if tt in self.TREATMENT_ACTION_TEXTS:
            return self.TREATMENT_ACTION_TEXTS[tt]

        # Partial match
        for key, text in self.TREATMENT_ACTION_TEXTS.items():
            if key in tt or tt in key:
                return text

        return ""


# Singleton instance
_medical_reasoning_service = None


def get_medical_reasoning_service(medical_model=None, user_condition_patterns=None) -> MedicalReasoningService:
    """
    Get or create the MedicalReasoningService singleton.

    Args:
        medical_model: Optional medical model instance
        user_condition_patterns: Optional user condition patterns

    Returns:
        MedicalReasoningService instance
    """
    global _medical_reasoning_service
    if _medical_reasoning_service is None:
        _medical_reasoning_service = MedicalReasoningService(
            medical_model=medical_model,
            user_condition_patterns=user_condition_patterns
        )
    return _medical_reasoning_service
