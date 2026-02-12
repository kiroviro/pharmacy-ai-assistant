"""
MedGemma medical reasoning model wrapper.

Uses MLX for efficient inference on Apple Silicon.
"""

import json
import os
import re
import time
from dataclasses import dataclass, asdict
from typing import Optional
from mlx_lm import load, generate

from src.logging_config import get_logger

logger = get_logger("viapharma.medical_model")


@dataclass
class MedicalReasoning:
    """Structured medical reasoning output."""
    symptoms: list[str]  # List of identified symptoms
    likely_cause: str  # Probable condition/cause
    treatment_type: str  # Recommended OTC treatment category
    warnings: list[str]  # Important cautions
    see_doctor: bool = False  # Whether to recommend seeing a doctor
    # Extended fields for richer analysis
    explanation: str = ""  # Detailed explanation of what's happening
    how_treatment_helps: str = ""  # Why the treatment works
    self_care_tips: list[str] = None  # Home care suggestions
    duration_guidance: str = ""  # Expected recovery timeline

    def __post_init__(self):
        if self.self_care_tips is None:
            self.self_care_tips = []

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MedicalReasoning":
        # Helper to ensure list fields are actually lists
        def ensure_list(value, default=None):
            if default is None:
                default = []
            if value is None:
                return default
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                # If it's a comma-separated string, split it
                if "," in value:
                    return [s.strip() for s in value.split(",") if s.strip()]
                return [value] if value.strip() else default
            return default

        return cls(
            symptoms=ensure_list(data.get("symptoms")),
            likely_cause=str(data.get("likely_cause", "") or ""),
            treatment_type=str(data.get("treatment_type", "") or ""),
            warnings=ensure_list(data.get("warnings")),
            see_doctor=bool(data.get("see_doctor", False)),
            explanation=str(data.get("explanation", "") or ""),
            how_treatment_helps=str(data.get("how_treatment_helps", "") or ""),
            self_care_tips=ensure_list(data.get("self_care_tips")),
            duration_guidance=str(data.get("duration_guidance", "") or ""),
        )

    def format_english(self) -> str:
        """Format the reasoning in English for translation."""
        parts = []

        if self.symptoms:
            symptoms_str = ", ".join(self.symptoms)
            parts.append(f"Identified symptoms: {symptoms_str}.")

        if self.likely_cause:
            parts.append(f"Probable cause: {self.likely_cause}.")

        if self.explanation:
            parts.append(f"What is happening: {self.explanation}")

        if self.treatment_type:
            parts.append(f"Recommended treatment: {self.treatment_type}.")

        if self.how_treatment_helps:
            parts.append(f"How treatment helps: {self.how_treatment_helps}")

        if self.self_care_tips:
            tips_str = "; ".join(self.self_care_tips)
            parts.append(f"Self-care tips: {tips_str}.")

        if self.duration_guidance:
            parts.append(f"Expected recovery: {self.duration_guidance}")

        if self.warnings:
            warnings_str = "; ".join(self.warnings)
            parts.append(f"Important warnings: {warnings_str}.")

        if self.see_doctor:
            parts.append("We recommend consulting a doctor.")

        return " ".join(parts)

    def format_bulgarian(self, translated_text: str = None) -> str:
        """
        Format the reasoning in Bulgarian for display.

        Args:
            translated_text: Optional pre-translated text to use instead of raw fields
        """
        if translated_text:
            # Use the translated text and add formatting
            parts = translated_text.split(". ")
            formatted = []
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                # Add bullet points and bold headers for key sections
                if part.lower().startswith("идентифицирани симптоми") or part.lower().startswith("симптоми"):
                    formatted.append(f"**{part}**")
                elif part.lower().startswith("вероятна причина") or part.lower().startswith("причина"):
                    formatted.append(f"**{part}**")
                elif part.lower().startswith("препоръчано лечение") or part.lower().startswith("лечение"):
                    formatted.append(f"**{part}**")
                elif part.lower().startswith("предупрежден") or part.lower().startswith("внимание"):
                    formatted.append(f"⚠️ **{part}**")
                elif "консултация" in part.lower() or "лекар" in part.lower():
                    formatted.append(f"\n⚠️ **{part}**")
                else:
                    formatted.append(part)
            return "\n\n".join(formatted) if formatted else translated_text

        # Fallback: format with English content but Bulgarian labels
        parts = []

        if self.symptoms:
            symptoms_str = ", ".join(self.symptoms)
            parts.append(f"**Идентифицирани симптоми:** {symptoms_str}")

        if self.likely_cause:
            parts.append(f"**Вероятна причина:** {self.likely_cause}")

        if self.explanation:
            parts.append(f"**Какво се случва:** {self.explanation}")

        if self.treatment_type:
            parts.append(f"**Препоръчано лечение:** {self.treatment_type}")

        if self.how_treatment_helps:
            parts.append(f"**Как помага лечението:** {self.how_treatment_helps}")

        if self.self_care_tips:
            tips_formatted = "\n".join(f"• {tip}" for tip in self.self_care_tips)
            parts.append(f"**Съвети за домашна грижа:**\n{tips_formatted}")

        if self.duration_guidance:
            parts.append(f"**Очаквано възстановяване:** {self.duration_guidance}")

        if self.warnings:
            warnings_str = "; ".join(self.warnings)
            parts.append(f"⚠️ **Предупреждения:** {warnings_str}")

        if self.see_doctor:
            parts.append("\n🏥 **Препоръчваме консултация с лекар.**")

        return "\n\n".join(parts)


# System prompt for medical reasoning with JSON output
MEDICAL_SYSTEM_PROMPT = """You are a pharmacy medical advisor. Analyze symptoms and provide detailed medical reasoning in JSON format.

IMPORTANT RULES:
- DO NOT ask follow-up questions
- DO NOT have a conversation
- ALWAYS provide a thorough analysis based on the symptoms given
- Output ONLY valid JSON, nothing else
- For infants/children: ALWAYS set see_doctor=true and include pediatric warning
- For chronic conditions: ALWAYS mention prescription requirement
- For drug interactions: ALWAYS include safety warnings

Respond with this JSON format:
{
  "symptoms": ["symptom1", "symptom2"],
  "likely_cause": "most probable cause",
  "explanation": "detailed explanation of why these symptoms occur and what is happening in the body",
  "treatment_type": "OTC category (analgesics, antipyretics, etc.)",
  "how_treatment_helps": "explanation of how the recommended treatment addresses the symptoms",
  "self_care_tips": ["tip1", "tip2", "tip3"],
  "duration_guidance": "expected recovery time and when improvement should be noticed",
  "warnings": ["warning1", "warning2"],
  "see_doctor": false
}

EXAMPLES:

Example 1 - Simple symptom:
Input: "headache"
Output: {"symptoms": ["headache"], "likely_cause": "tension headache from stress or muscle tension", "explanation": "Tension headaches occur when muscles in the head, neck and scalp contract and tighten. This is often caused by stress, poor posture, eye strain, or lack of sleep. The pain is usually a dull, constant ache on both sides of the head.", "treatment_type": "analgesics", "how_treatment_helps": "Pain relievers like paracetamol or ibuprofen block pain signals and reduce inflammation, providing relief within 30-60 minutes.", "self_care_tips": ["Rest in a quiet, dark room", "Apply a cold or warm compress to your forehead", "Stay hydrated and avoid caffeine", "Gently massage your temples and neck"], "duration_guidance": "Most tension headaches improve within 2-4 hours with treatment. If headaches occur more than 15 days per month, consult a doctor.", "warnings": ["See doctor if headache is sudden and severe", "Seek help if accompanied by confusion, fever, or stiff neck"], "see_doctor": false}

Example 2 - Child/infant:
Input: "my 6 month old baby has fever"
Output: {"symptoms": ["fever", "infant 6 months"], "likely_cause": "viral infection (most common in infants)", "explanation": "Fever in infants is usually the body's natural response to fighting infection. At 6 months, babies are losing maternal antibodies and becoming more susceptible to common viruses. The immune system raises body temperature to create an unfavorable environment for pathogens.", "treatment_type": "pediatric antipyretics (infant paracetamol)", "how_treatment_helps": "Infant paracetamol reduces fever by acting on the brain's temperature control center, making the baby more comfortable. Always use age-appropriate dosing based on weight.", "self_care_tips": ["Keep baby lightly dressed", "Offer frequent breastfeeding or formula to prevent dehydration", "Monitor wet diapers (at least 4-6 per day)", "Use a lukewarm sponge bath if fever is high"], "duration_guidance": "Viral fevers typically last 2-3 days. You should see improvement within 1 hour of giving medication.", "warnings": ["ALWAYS consult pediatrician for infants under 1 year", "Seek immediate care if fever exceeds 38.5°C", "Watch for signs of dehydration, lethargy, or rash"], "see_doctor": true}

Example 3 - Multiple symptoms:
Input: "sore throat with fever and body aches for 3 days"
Output: {"symptoms": ["sore throat", "fever", "body aches", "3 days duration"], "likely_cause": "viral upper respiratory infection, possibly influenza", "explanation": "The combination of sore throat, fever, and body aches strongly suggests a viral infection. Your immune system is actively fighting the virus, causing inflammation in the throat and releasing chemicals called cytokines that cause the fever and muscle aches. The 3-day duration is typical for the acute phase.", "treatment_type": "antipyretics, throat lozenges, and pain relievers", "how_treatment_helps": "Antipyretics reduce fever and relieve body aches. Throat lozenges coat and soothe the irritated throat lining, while some contain mild anesthetics for pain relief. Combined treatment addresses multiple symptoms.", "self_care_tips": ["Gargle with warm salt water 3-4 times daily", "Drink warm liquids like tea with honey", "Get plenty of rest to support immune function", "Use a humidifier to keep throat moist"], "duration_guidance": "Most viral infections resolve within 7-10 days. Fever should break within 3-4 days. Sore throat may linger for up to a week.", "warnings": ["See doctor if fever persists beyond 4 days", "Seek help if you have difficulty swallowing or breathing", "Watch for white patches on tonsils (may indicate strep)"], "see_doctor": false}

Example 4 - Drug interaction:
Input: "can I take ibuprofen with alcohol"
Output: {"symptoms": ["drug interaction query"], "likely_cause": "safety concern about combining substances", "explanation": "Ibuprofen and alcohol both irritate the stomach lining. Together, they significantly increase the risk of gastric bleeding and ulcers. Alcohol also affects how your liver processes ibuprofen, potentially increasing its concentration in your blood.", "treatment_type": "avoid combination - use alternatives", "how_treatment_helps": "Paracetamol (acetaminophen) is a safer alternative for occasional use with moderate alcohol, though it should not be used regularly with heavy alcohol consumption due to liver concerns.", "self_care_tips": ["Wait at least 24 hours after drinking before taking ibuprofen", "If you need pain relief after drinking, use paracetamol sparingly", "Stay hydrated to reduce hangover symptoms naturally", "Consider non-medication approaches like rest and hydration"], "duration_guidance": "Alcohol is typically cleared from your system within 12-24 hours depending on amount consumed.", "warnings": ["Never take ibuprofen on an empty stomach", "Risk increases with higher doses and frequent use", "Seek help if you experience stomach pain, dark stools, or vomiting blood"], "see_doctor": false}

Now analyze the symptoms and output JSON:"""


class MedicalModel:
    """
    Wrapper for MedGemma model inference.

    Provides medical reasoning based on symptom descriptions.
    """

    def __init__(self, model_path: str = "./models/medgemma-4b-it-bf16"):
        """
        Initialize the medical model.

        Args:
            model_path: Path to the MedGemma model directory
        """
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self._loaded = False

    def load(self) -> None:
        """Load the model into memory. Call this once at startup."""
        if self._loaded:
            return

        logger.info(f"Loading MedGemma from {self.model_path}...")
        start_time = time.perf_counter()
        self.model, self.tokenizer = load(self.model_path)
        self._loaded = True
        duration = time.perf_counter() - start_time
        logger.info(f"MedGemma loaded successfully", extra={"load_time_s": round(duration, 2)})

    def _format_prompt(self, user_message: str, system_prompt: str = None) -> str:
        """
        Format the prompt using Gemma chat template.

        Args:
            user_message: The user's symptom description
            system_prompt: Optional custom system prompt

        Returns:
            Formatted prompt string
        """
        if system_prompt is None:
            system_prompt = MEDICAL_SYSTEM_PROMPT

        # Gemma 3 format: system prompt prepended to first user message
        # <start_of_turn>user\n{system}\n\n{user}<end_of_turn>\n<start_of_turn>model\n
        prompt = f"<start_of_turn>user\n{system_prompt}\n\n{user_message}<end_of_turn>\n<start_of_turn>model\n"
        return prompt

    def get_medical_reasoning(
        self,
        symptoms: str,
        max_tokens: int = 200,
        temperature: float = 0.3,
        system_prompt: str = None
    ) -> MedicalReasoning:
        """
        Get medical reasoning for the given symptoms.

        Args:
            symptoms: Description of symptoms (in English)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
            system_prompt: Optional custom system prompt

        Returns:
            MedicalReasoning object with structured data
        """
        if not self._loaded:
            self.load()

        prompt = self._format_prompt(symptoms, system_prompt)

        response = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
        )

        # Clean up and parse JSON response
        response = response.strip()

        return self._parse_medical_response(response)

    # Garbage phrases that should not appear in output (from product side effects, etc.)
    GARBAGE_PHRASES = [
        "с неизвестна честота",
        "неизвестна честота",
        "unknown frequency",
        "нежелани реакции",
        "странични ефекти",
        "side effects",
    ]

    def _sanitize_text(self, text: str) -> str:
        """Remove garbage phrases from text."""
        if not text:
            return text
        result = text
        for phrase in self.GARBAGE_PHRASES:
            result = result.replace(phrase, "").strip()
        # Clean up double spaces and punctuation
        result = re.sub(r'\s+', ' ', result)
        result = re.sub(r'[,;:]+\s*[,;:]+', '', result)
        return result.strip()

    def _sanitize_reasoning(self, reasoning: MedicalReasoning) -> MedicalReasoning:
        """Sanitize all fields in MedicalReasoning to remove garbage text."""
        return MedicalReasoning(
            symptoms=[self._sanitize_text(s) for s in reasoning.symptoms if self._sanitize_text(s)],
            likely_cause=self._sanitize_text(reasoning.likely_cause),
            treatment_type=self._sanitize_text(reasoning.treatment_type),
            warnings=[self._sanitize_text(w) for w in reasoning.warnings if self._sanitize_text(w)],
            see_doctor=reasoning.see_doctor,
            explanation=self._sanitize_text(reasoning.explanation),
            how_treatment_helps=self._sanitize_text(reasoning.how_treatment_helps),
            self_care_tips=[self._sanitize_text(t) for t in (reasoning.self_care_tips or []) if self._sanitize_text(t)],
            duration_guidance=self._sanitize_text(reasoning.duration_guidance),
        )

    def _parse_medical_response(self, response: str) -> MedicalReasoning:
        """
        Parse the JSON response from MedGemma into a MedicalReasoning object.

        Args:
            response: Raw response from the model

        Returns:
            MedicalReasoning object (sanitized)
        """
        reasoning = None
        try:
            # Try to extract JSON from response
            # Sometimes the model adds text before/after JSON
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
                reasoning = MedicalReasoning.from_dict(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse JSON response: {e}")

        # Fallback: try to parse unstructured response
        if reasoning is None:
            reasoning = self._parse_unstructured_response(response)

        # Sanitize to remove garbage text
        return self._sanitize_reasoning(reasoning)

    def _parse_unstructured_response(self, response: str) -> MedicalReasoning:
        """
        Fallback parser for non-JSON responses.

        Args:
            response: Raw unstructured response

        Returns:
            MedicalReasoning object with best-effort parsing
        """
        symptoms = []
        likely_cause = ""
        treatment_type = ""
        warnings = []
        see_doctor = False

        # Check for refusal
        response_lower = response.lower()
        refusal_phrases = ["i cannot", "i can't", "не мога", "not able to"]
        if any(phrase in response_lower for phrase in refusal_phrases):
            return MedicalReasoning(
                symptoms=[],
                likely_cause="Заявката не може да бъде обработена",
                treatment_type="",
                warnings=[],
                see_doctor=False,
            )

        # Try to extract structured info from text
        lines = response.split('\n')
        for line in lines:
            line_lower = line.lower()
            if 'symptom' in line_lower or 'симптом' in line_lower:
                # Extract symptoms
                parts = line.split(':', 1)
                if len(parts) > 1:
                    symptoms = [s.strip() for s in parts[1].split(',') if s.strip()]
            elif 'cause' in line_lower or 'причина' in line_lower:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    likely_cause = parts[1].strip()
            elif 'treatment' in line_lower or 'лечение' in line_lower:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    treatment_type = parts[1].strip()
            elif 'warning' in line_lower or 'предупрежден' in line_lower:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    warnings = [parts[1].strip()]
            elif 'doctor' in line_lower or 'лекар' in line_lower:
                see_doctor = True

        # If nothing parsed, use a generic Bulgarian message
        if not symptoms and not likely_cause and not treatment_type:
            likely_cause = "Общо неразположение"
            treatment_type = "симптоматично лечение"

        return MedicalReasoning(
            symptoms=symptoms,
            likely_cause=likely_cause,
            treatment_type=treatment_type,
            warnings=warnings,
            see_doctor=see_doctor,
        )

    def refine_product_selection(
        self,
        user_query: str,
        medical_reasoning: str,
        candidate_products: list,
        max_products: int = 3
    ) -> list:
        """
        Use LLM to refine product selection from candidates.

        This implements Stage 2 of the Perplexity-style two-stage retrieval.

        Args:
            user_query: Original user query
            medical_reasoning: Medical analysis from get_medical_reasoning()
            candidate_products: List of Product objects from vector search
            max_products: Maximum number of products to return

        Returns:
            List of best-matching Product objects
        """
        if not self._loaded:
            self.load()

        if not candidate_products:
            return []

        # Build product list for prompt
        product_list = []
        for i, product in enumerate(candidate_products, 1):
            # Support both old (name) and new (title) field names
            name = getattr(product, 'title', None) or getattr(product, 'name', 'Unknown')
            product_info = f"{i}. {name}"

            # Add description/indications
            desc = getattr(product, 'description', None) or getattr(product, 'indications', None)
            if desc:
                product_info += f" - {desc[:100]}"

            # Add contraindications
            contra = getattr(product, 'contraindications', None)
            if contra:
                product_info += f" (Avoid if: {contra[:80]})"

            product_list.append(product_info)

        products_str = "\n".join(product_list)

        refinement_prompt = f"""Based on the customer's symptoms and the medical analysis, select the {max_products} most appropriate products.

Customer query: {user_query}

Medical analysis: {medical_reasoning}

Available products:
{products_str}

Select the {max_products} best products by their numbers. Consider:
- How well the product matches the symptoms
- Any contraindications mentioned
- Effectiveness for the condition

Respond with ONLY the product numbers separated by commas (e.g., "1, 3, 5").
"""

        prompt = self._format_prompt(refinement_prompt)

        response = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=50,
        )

        # Parse the response to get product indices
        selected_indices = []
        try:
            # Extract numbers from response
            numbers = re.findall(r'\d+', response)
            for num in numbers:
                idx = int(num) - 1  # Convert to 0-indexed
                if 0 <= idx < len(candidate_products):
                    selected_indices.append(idx)
                if len(selected_indices) >= max_products:
                    break
        except Exception:
            # Fallback: return first N products
            selected_indices = list(range(min(max_products, len(candidate_products))))

        # If no valid indices found, return first N
        if not selected_indices:
            selected_indices = list(range(min(max_products, len(candidate_products))))

        return [candidate_products[i] for i in selected_indices]


# Global model instance (lazy loaded)
_medical_model: Optional[MedicalModel] = None


def get_medical_model() -> MedicalModel:
    """Get or create the global medical model instance."""
    global _medical_model
    if _medical_model is None:
        model_path = os.environ.get(
            "MEDGEMMA_MODEL_PATH",
            "./models/medgemma-4b-it-bf16"
        )
        _medical_model = MedicalModel(model_path)
    return _medical_model
