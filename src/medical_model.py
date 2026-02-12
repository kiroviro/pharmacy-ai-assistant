"""
MedGemma medical reasoning model wrapper.

Uses MLX for efficient inference on Apple Silicon.
"""

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Optional

from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

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
    # User conditions for contraindication filtering
    user_conditions: list[str] = None  # Pregnancy, allergies, age, chronic diseases

    def __post_init__(self):
        if self.self_care_tips is None:
            self.self_care_tips = []
        if self.user_conditions is None:
            self.user_conditions = []

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MedicalReasoning":
        return cls(
            symptoms=_ensure_list(data.get("symptoms")),
            likely_cause=str(data.get("likely_cause", "") or ""),
            treatment_type=str(data.get("treatment_type", "") or ""),
            warnings=_ensure_list(data.get("warnings")),
            see_doctor=bool(data.get("see_doctor", False)),
            explanation=str(data.get("explanation", "") or ""),
            how_treatment_helps=str(data.get("how_treatment_helps", "") or data.get("how_it_helps", "") or ""),
            self_care_tips=_ensure_list(data.get("self_care_tips") or data.get("self_care")),
            duration_guidance=str(data.get("duration_guidance", "") or data.get("recovery", "") or ""),
            user_conditions=_ensure_list(data.get("user_conditions") or data.get("conditions")),
        )


def _ensure_list(value, default: list | None = None) -> list:
    """Ensure value is a list, converting from string if needed."""
    if default is None:
        default = []
    if value is None:
        return default
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        if "," in value:
            return [s.strip() for s in value.split(",") if s.strip()]
        return [value] if value.strip() else default
    return default

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
MEDICAL_SYSTEM_PROMPT = """You are a pharmacy product recommendation system. Analyze symptoms and output JSON.

RULES:
- Output ONLY valid JSON, nothing else
- For infants/children: set see_doctor=true
- For chronic conditions: mention prescription requirement
- For drug interactions: include safety warnings

JSON format:
{
  "symptoms": ["symptom1", "symptom2"],
  "likely_cause": "brief cause description",
  "explanation": "what is happening in the body and why",
  "treatment_type": "OTC category",
  "how_it_helps": "how the treatment addresses symptoms",
  "self_care": ["home care tip 1", "tip 2"],
  "recovery": "when to expect improvement",
  "warnings": ["when to see doctor"],
  "see_doctor": false
}

EXAMPLES:

Input: "headache"
Output: {"symptoms": ["headache"], "likely_cause": "tension or stress", "explanation": "Tension headaches occur when muscles in head and neck tighten, often from stress or poor posture.", "treatment_type": "analgesics", "how_it_helps": "Pain relievers block pain signals and reduce inflammation, providing relief in 30-60 minutes.", "self_care": ["Rest in quiet room", "Apply cold compress", "Stay hydrated", "Massage temples"], "recovery": "Most headaches improve within 2-4 hours with treatment.", "warnings": ["See doctor if sudden and severe", "Seek help if with fever or stiff neck"], "see_doctor": false}

Input: "baby 6 months has fever"
Output: {"symptoms": ["fever", "infant"], "likely_cause": "viral infection", "explanation": "Fever is the body fighting infection. Infants are susceptible as maternal antibodies wane.", "treatment_type": "pediatric antipyretics", "how_it_helps": "Reduces fever and makes baby comfortable. Use age-appropriate dosing.", "self_care": ["Keep baby lightly dressed", "Offer fluids frequently", "Monitor wet diapers", "Lukewarm sponge bath"], "recovery": "Viral fevers last 2-3 days. Improvement within 1 hour of medication.", "warnings": ["Consult pediatrician for infants under 1 year", "Immediate care if fever exceeds 38.5C"], "see_doctor": true}

Input: "sore throat with fever 3 days"
Output: {"symptoms": ["sore throat", "fever", "3 days"], "likely_cause": "viral infection, possibly flu", "explanation": "Combination suggests viral infection. Immune system causes inflammation and releases cytokines causing fever and aches.", "treatment_type": "antipyretics and throat lozenges", "how_it_helps": "Antipyretics reduce fever. Lozenges soothe throat and provide mild pain relief.", "self_care": ["Gargle salt water", "Drink warm liquids with honey", "Rest", "Use humidifier"], "recovery": "Viral infections resolve in 7-10 days. Fever breaks within 3-4 days.", "warnings": ["See doctor if fever persists beyond 4 days", "Difficulty swallowing or breathing"], "see_doctor": false}

Input: "can I take ibuprofen with alcohol"
Output: {"symptoms": ["drug interaction query"], "likely_cause": "safety concern", "explanation": "Both irritate stomach lining. Together they increase risk of gastric bleeding.", "treatment_type": "avoid combination", "how_it_helps": "Paracetamol is safer alternative for occasional use with moderate alcohol.", "self_care": ["Wait 24 hours after drinking", "Stay hydrated", "Consider rest instead of medication"], "recovery": "Alcohol clears system in 12-24 hours.", "warnings": ["Never take ibuprofen on empty stomach", "Seek help for stomach pain or dark stools"], "see_doctor": false}

Now analyze and output JSON:"""


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

        sampler = make_sampler(temp=temperature)
        response = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=sampler,
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
        reasoning = self._try_parse_json(response)
        if reasoning is None:
            reasoning = self._parse_unstructured_response(response)
        return self._sanitize_reasoning(reasoning)

    def _try_parse_json(self, response: str) -> MedicalReasoning | None:
        """Try to extract and parse JSON from response."""
        try:
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return MedicalReasoning.from_dict(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse JSON response: {e}")
        return None

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

        # Build product list for prompt with similarity scores and full details
        product_list = []
        for i, product in enumerate(candidate_products, 1):
            # Support both old (name) and new (title) field names
            name = getattr(product, 'title', None) or getattr(product, 'name', 'Unknown')

            # Include similarity score to help LLM factor in search confidence
            score = getattr(product, 'score', 0.0)
            relevance = "high" if score >= 0.5 else "medium" if score >= 0.35 else "low"
            product_info = f"{i}. [{relevance} relevance] {name}"

            # Add description/indications (expanded)
            desc = getattr(product, 'description', None) or getattr(product, 'indications', None)
            if desc:
                product_info += f"\n   Description: {desc[:200]}"

            # Add composition (active ingredients)
            composition = getattr(product, 'composition', None)
            if composition:
                product_info += f"\n   Composition: {composition[:150]}"

            # Add contraindications (full for safety)
            contra = getattr(product, 'contraindications', None)
            if contra:
                product_info += f"\n   Contraindications: {contra[:200]}"

            product_list.append(product_info)

        products_str = "\n".join(product_list)

        refinement_prompt = f"""Based on the customer's symptoms and the medical analysis, select the {max_products} most appropriate products.

Customer query: {user_query}

Medical analysis: {medical_reasoning}

Available products (with details):
{products_str}

Select the {max_products} best products by their numbers. Consider:
- Product relevance level (prefer high/medium over low)
- How well the product matches the symptoms
- Active ingredients in composition
- Any contraindications mentioned (CRITICAL: avoid products with contraindications matching user conditions)
- Effectiveness for the condition

Respond with ONLY valid JSON in this exact format: {{"selected": [1, 3, 5]}}
Replace the numbers with your chosen product numbers. Output nothing else.
"""

        prompt = self._format_prompt(refinement_prompt)

        sampler = make_sampler(temp=0.0)  # Fully deterministic for product selection
        response = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=50,
            sampler=sampler,
        )

        # Parse the response to get product indices
        selected_indices = self._parse_product_selection(
            response, len(candidate_products), max_products
        )

        return [candidate_products[i] for i in selected_indices]

    def _parse_product_selection(
        self,
        response: str,
        num_candidates: int,
        max_products: int
    ) -> list[int]:
        """
        Parse product selection from LLM response.

        Attempts JSON parsing first, then falls back to regex extraction.
        Logs all fallback scenarios for debugging.

        Args:
            response: Raw LLM response
            num_candidates: Number of candidate products available
            max_products: Maximum products to select

        Returns:
            List of 0-indexed product indices
        """
        selected_indices = []
        response_stripped = response.strip()

        # Attempt 1: JSON parsing (preferred)
        try:
            json_match = re.search(r'\{[^{}]*\}', response_stripped)
            if json_match:
                data = json.loads(json_match.group())
                if "selected" in data and isinstance(data["selected"], list):
                    for num in data["selected"]:
                        idx = int(num) - 1  # Convert to 0-indexed
                        if 0 <= idx < num_candidates and idx not in selected_indices:
                            selected_indices.append(idx)
                        if len(selected_indices) >= max_products:
                            break
                    if selected_indices:
                        logger.debug(
                            "Product selection parsed via JSON",
                            extra={"selected_indices": selected_indices, "response": response_stripped}
                        )
                        return selected_indices
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug(f"JSON parsing failed: {e}", extra={"response": response_stripped})

        # Attempt 2: Extract numbers at start of response (e.g., "1, 3, 5")
        # Only look at first 20 chars to avoid extracting numbers from product descriptions
        first_part = response_stripped[:20]
        try:
            numbers = re.findall(r'\d+', first_part)
            for num in numbers:
                idx = int(num) - 1
                if 0 <= idx < num_candidates and idx not in selected_indices:
                    selected_indices.append(idx)
                if len(selected_indices) >= max_products:
                    break
            if selected_indices:
                logger.warning(
                    "Product selection used regex fallback (JSON parsing failed)",
                    extra={"selected_indices": selected_indices, "response": response_stripped}
                )
                return selected_indices
        except (ValueError, TypeError) as e:
            logger.debug(f"Regex extraction failed: {e}")

        # Fallback: return first N products
        logger.warning(
            "Product selection fallback to first N products - LLM response could not be parsed",
            extra={"response": response_stripped, "fallback_count": max_products}
        )
        return list(range(min(max_products, num_candidates)))


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
