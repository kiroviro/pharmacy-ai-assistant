"""
MedGemma medical reasoning model wrapper.

Uses MLX for efficient inference on Apple Silicon.
Includes LRU caching for repeated queries.
"""

import hashlib
import json
import os
import re
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import asdict, dataclass

from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

from src.config import get_settings
from src.logging_config import get_logger

logger = get_logger("viapharma.medical_model")

# =============================================================================
# CONFIGURATION
# =============================================================================
# Cache size for medical reasoning results (number of unique queries)
REASONING_CACHE_SIZE = 500

# Retry configuration for model inference
MAX_INFERENCE_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 0.5  # Exponential backoff: 0.5s, 1.0s, 2.0s

# Timeout configuration (prevents 49s outliers)
MEDICAL_REASONING_TIMEOUT_SECONDS = 15.0  # Max time for inference

# Thread pool for timeout-protected inference
# Using 1 worker since MLX doesn't support concurrent inference
_inference_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="medgemma-timeout")


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


# System prompt for medical reasoning with JSON output (English)
MEDICAL_SYSTEM_PROMPT = """You are a pharmacy product recommendation system. Analyze symptoms and output JSON.

RULES:
- Output ONLY valid JSON, nothing else
- For infants/children: set see_doctor=true
- For chronic conditions: mention prescription requirement
- For drug interactions: include safety warnings

IMPORTANT - DO NOT MENTION these unrelated topics:
- Personal data protection / защита на личните данни
- Dental prosthetics / зъбні протези
- Mosquito repellents / репеленти / комари (unless specifically asked)
- General protection means / средство за защита
- Any non-medical administrative or legal topics

Focus ONLY on:
- The specific symptoms presented
- OTC medications that treat those symptoms
- Self-care advice for the condition
- When to seek medical attention

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


# System prompt for medical reasoning with JSON output (Bulgarian)
MEDICAL_SYSTEM_PROMPT_BG = """Вие сте система за препоръчване на аптечни продукти. Анализирайте симптомите и изведете JSON на български.

ПРАВИЛА:
- Изведете САМО валиден JSON, нищо друго
- За бебета/деца: задайте see_doctor=true
- За хронични заболявания: споменете изискване за рецепта
- За лекарствени взаимодействия: включете предупреждения за безопасност

ВАЖНО - НЕ СПОМЕНАВАЙТЕ тези несвързани теми:
- Защита на личните данни
- Зъбни протези / грижа за зъбні протези
- Репеленти срещу комари / комари (освен ако не се пита конкретно)
- Общи средства за защита
- Каквито и да е неmedицински административни или правни теми

Фокусирайте се САМО върху:
- Конкретните симптоми, които са представени
- Безрецептурни лекарства, които лекуват тези симптоми
- Съвети за домашна грижа за състоянието
- Кога да потърсите медицинска помощ

JSON формат (всички полета на БЪЛГАРСКИ):
{
  "symptoms": ["симптом1", "симптом2"],
  "likely_cause": "кратко описание на причината",
  "explanation": "какво се случва в тялото и защо",
  "treatment_type": "категория безрецептурни лекарства",
  "how_it_helps": "как лечението помага при симптомите",
  "self_care": ["съвет за домашна грижа 1", "съвет 2"],
  "recovery": "кога да очаквате подобрение",
  "warnings": ["кога да посетите лекар"],
  "see_doctor": false
}

ПРИМЕРИ:

Вход: "главоболие"
Изход: {"symptoms": ["главоболие"], "likely_cause": "напрежение или стрес", "explanation": "Тензионните главоболия се появяват когато мускулите на главата и врата се стягат, често от стрес или лоша стойка.", "treatment_type": "болкоуспокояващи", "how_it_helps": "Болкоуспокояващите блокират болковите сигнали и намаляват възпалението, осигурявайки облекчение за 30-60 минути.", "self_care": ["Почивайте в тиха стая", "Приложете студен компрес", "Хидратирайте се", "Масажирайте слепоочията"], "recovery": "Повечето главоболия се подобряват за 2-4 часа с лечение.", "warnings": ["Вижте лекар ако е внезапно и силно", "Потърсете помощ ако е с температура или вцепенен врат"], "see_doctor": false}

Вход: "бебе на 6 месеца има температура"
Изход: {"symptoms": ["температура", "бебе"], "likely_cause": "вирусна инфекция", "explanation": "Температурата е начин тялото да се бори с инфекцията. Бебетата са податливи докато майчините антитела намаляват.", "treatment_type": "педиатрични жаропонижаващи", "how_it_helps": "Намалява температурата и прави бебето по-комфортно. Използвайте дозиране подходящо за възрастта.", "self_care": ["Облечете бебето леко", "Предлагайте течности често", "Следете мокрите пелени", "Хладка гъба за баня"], "recovery": "Вирусните температури траят 2-3 дни. Подобрение в рамките на 1 час след лекарството.", "warnings": ["Консултирайте се с педиатър за бебета под 1 година", "Спешна помощ ако температурата надвиши 38.5°C"], "see_doctor": true}

Вход: "болки в гърлото с температура 3 дни"
Изход: {"symptoms": ["болки в гърлото", "температура", "3 дни"], "likely_cause": "вирусна инфекция, вероятно грип", "explanation": "Комбинацията предполага вирусна инфекция. Имунната система причинява възпаление и освобождава цитокини, причиняващи температура и болки.", "treatment_type": "жаропонижаващи и таблетки за гърло", "how_it_helps": "Жаропонижаващите намаляват температурата. Таблетките успокояват гърлото и осигуряват лека облага от болката.", "self_care": ["Гаргара със солена вода", "Пийте топли напитки с мед", "Почивайте", "Използвайте овлажнител"], "recovery": "Вирусните инфекции отминават за 7-10 дни. Температурата спада за 3-4 дни.", "warnings": ["Вижте лекар ако температурата продължава над 4 дни", "Затруднено преглъщане или дишане"], "see_doctor": false}

Вход: "мога ли да взема ибупрофен с алкохол"
Изход: {"symptoms": ["запитване за лекарствено взаимодействие"], "likely_cause": "безопасност", "explanation": "И двете дразнят стомашната лигавица. Заедно увеличават риска от стомашно кървене.", "treatment_type": "избягвайте комбинацията", "how_it_helps": "Парацетамолът е по-безопасна алтернатива за случайна употреба с умерен алкохол.", "self_care": ["Изчакайте 24 часа след пиене", "Хидратирайте се", "Помислете за почивка вместо лекарство"], "recovery": "Алкохолът се изчиства от системата за 12-24 часа.", "warnings": ["Никога не вземайте ибупрофен на празен стомах", "Потърсете помощ при стомашна болка или тъмен стол"], "see_doctor": false}

Сега анализирайте и изведете JSON:"""


class MedicalModel:
    """
    Wrapper for MedGemma model inference.

    Provides medical reasoning based on symptom descriptions.
    Includes LRU caching for repeated queries to improve performance.
    """

    def __init__(
        self,
        model_path: str = "./models/medgemma-4b-it-bf16",
        cache_size: int = REASONING_CACHE_SIZE,
        use_bulgarian: bool = False,
        settings=None,
    ):
        """
        Initialize the medical model.

        Args:
            model_path: Path to the MedGemma model directory
            cache_size: Maximum number of cached reasoning results
            use_bulgarian: If True, generate Bulgarian responses directly (skip translation)
            settings: Optional settings instance (uses get_settings() if not provided)
        """
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self._loaded = False
        self.use_bulgarian = use_bulgarian
        self.settings = settings or get_settings()

        # LRU cache for medical reasoning results
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._cache_size = cache_size
        self._cache_hits = 0
        self._cache_misses = 0

    def load(self) -> None:
        """Load the model into memory. Call this once at startup."""
        if self._loaded:
            return

        logger.info(f"Loading MedGemma from {self.model_path}...")
        start_time = time.perf_counter()
        self.model, self.tokenizer = load(self.model_path)
        self._loaded = True
        duration = time.perf_counter() - start_time
        logger.info("MedGemma loaded successfully", extra={"load_time_s": round(duration, 2)})

    # =========================================================================
    # CACHING METHODS
    # =========================================================================

    def _normalize_query(self, query: str) -> str:
        """
        Normalize query for cache key generation.

        Normalizes whitespace, case, and punctuation to improve cache hits
        for semantically equivalent queries.
        """
        if not query:
            return ""
        # Lowercase and normalize whitespace
        normalized = " ".join(query.lower().split())
        # Remove trailing punctuation that doesn't change meaning
        normalized = normalized.rstrip("?!.,;:")
        return normalized

    def _get_cache_key(self, query: str, temperature: float) -> str:
        """
        Generate cache key from normalized query and parameters.

        Args:
            query: The symptom description
            temperature: Sampling temperature (affects output)

        Returns:
            Hash string for cache lookup
        """
        normalized = self._normalize_query(query)
        # Include temperature in key since it affects output
        key_input = f"{normalized}|temp={temperature:.2f}"
        return hashlib.sha256(key_input.encode()).hexdigest()[:16]

    def _get_from_cache(self, cache_key: str) -> MedicalReasoning | None:
        """
        Get cached reasoning result if available.

        Moves accessed item to end (most recently used) for LRU behavior.
        """
        if cache_key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(cache_key)
            self._cache_hits += 1
            cached_data = self._cache[cache_key]
            logger.debug("Cache HIT", extra={"cache_key": cache_key})
            return MedicalReasoning.from_dict(cached_data)
        self._cache_misses += 1
        return None

    def _put_in_cache(self, cache_key: str, reasoning: MedicalReasoning) -> None:
        """
        Store reasoning result in cache.

        Evicts least recently used item if cache is full.
        """
        # Evict oldest if at capacity
        while len(self._cache) >= self._cache_size:
            evicted_key, _ = self._cache.popitem(last=False)
            logger.debug("Cache eviction", extra={"evicted_key": evicted_key})

        self._cache[cache_key] = reasoning.to_dict()
        logger.debug("Cache STORE", extra={"cache_key": cache_key, "cache_size": len(self._cache)})

    def get_cache_stats(self) -> dict:
        """
        Get cache statistics for monitoring.

        Returns:
            Dictionary with cache metrics
        """
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "size": len(self._cache),
            "max_size": self._cache_size,
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 2),
            "total_requests": total_requests,
        }

    def clear_cache(self) -> None:
        """Clear all cached reasoning results."""
        self._cache.clear()
        logger.info("Reasoning cache cleared")

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
            # Use Bulgarian prompt if configured, otherwise English
            system_prompt = MEDICAL_SYSTEM_PROMPT_BG if self.use_bulgarian else MEDICAL_SYSTEM_PROMPT

        # Gemma 3 format: system prompt prepended to first user message
        # <start_of_turn>user\n{system}\n\n{user}<end_of_turn>\n<start_of_turn>model\n
        prompt = f"<start_of_turn>user\n{system_prompt}\n\n{user_message}<end_of_turn>\n<start_of_turn>model\n"
        return prompt

    def _generate_with_retry(
        self,
        prompt: str,
        max_tokens: int,
        sampler,
        operation_name: str = "inference",
    ) -> str:
        """
        Generate model response with automatic retry on transient failures.

        Uses exponential backoff for retries. Handles common failure modes:
        - Memory allocation errors
        - Timeout/resource exhaustion
        - Transient model errors

        Args:
            prompt: The formatted prompt to send to the model
            max_tokens: Maximum tokens to generate
            sampler: The sampler to use for generation
            operation_name: Name of the operation for logging

        Returns:
            Generated response string

        Raises:
            Exception: If all retries fail
        """
        last_error = None

        for attempt in range(MAX_INFERENCE_RETRIES):
            try:
                response = generate(
                    self.model,
                    self.tokenizer,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    sampler=sampler,
                )
                return response

            except Exception as e:
                last_error = e
                error_type = type(e).__name__

                if attempt < MAX_INFERENCE_RETRIES - 1:
                    delay = RETRY_BASE_DELAY_SECONDS * (2**attempt)
                    logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}/{MAX_INFERENCE_RETRIES}), "
                        f"retrying in {delay:.1f}s: {error_type}: {str(e)[:100]}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"{operation_name} failed after {MAX_INFERENCE_RETRIES} attempts: {error_type}: {str(e)[:200]}"
                    )

        # All retries exhausted
        raise last_error

    def get_medical_reasoning(
        self,
        symptoms: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str = None,
        use_cache: bool = True,
        timeout_seconds: float = MEDICAL_REASONING_TIMEOUT_SECONDS,
    ) -> MedicalReasoning:
        """
        Get medical reasoning for the given symptoms with timeout protection.

        Uses LRU caching to avoid redundant inference for repeated queries.
        Adds timeout protection to prevent 49s outliers.

        Args:
            symptoms: Description of symptoms (in English)
            max_tokens: Maximum tokens to generate (uses settings default if None)
            temperature: Sampling temperature (uses settings default if None)
            system_prompt: Optional custom system prompt
            use_cache: Whether to use caching (default True)
            timeout_seconds: Maximum time allowed for inference (default 15s)

        Returns:
            MedicalReasoning object with structured data

        Raises:
            TimeoutError: If inference exceeds timeout_seconds (caught internally, returns fallback)
        """
        # Use settings defaults if not specified
        if max_tokens is None:
            max_tokens = self.settings.medical_reasoning_max_tokens
        if temperature is None:
            temperature = self.settings.medical_reasoning_temperature

        # Check cache first (only for default system prompt)
        cache_key = None
        if use_cache and system_prompt is None:
            cache_key = self._get_cache_key(symptoms, temperature)
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                logger.info(
                    "Returning cached medical reasoning", extra={"cache_key": cache_key, "query_preview": symptoms[:50]}
                )
                return cached_result

        # Load model if needed
        if not self._loaded:
            self.load()

        # Run inference with timeout protection using concurrent.futures
        # This is thread-safe and works in async context
        try:
            future = _inference_executor.submit(
                self._run_inference,
                symptoms,
                max_tokens,
                temperature,
                system_prompt,
                cache_key
            )
            result = future.result(timeout=timeout_seconds)
            return result

        except FuturesTimeoutError:
            logger.warning(
                f"MedGemma inference timeout after {timeout_seconds}s, using fallback reasoning",
                extra={"query_preview": symptoms[:50], "timeout": timeout_seconds}
            )
            # Return simple fallback reasoning instead of failing
            return self._get_fallback_reasoning(symptoms)
        except Exception as e:
            logger.error(f"Error during medical reasoning: {e}", exc_info=True)
            # Return fallback on any error
            return self._get_fallback_reasoning(symptoms)

    def _run_inference(
        self,
        symptoms: str,
        max_tokens: int,
        temperature: float,
        system_prompt: str,
        cache_key: str
    ) -> MedicalReasoning:
        """
        Run the actual inference (called in thread pool for timeout protection).

        Args:
            symptoms: Symptom description
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
            system_prompt: Optional system prompt
            cache_key: Cache key for storing result

        Returns:
            MedicalReasoning object
        """
        start_time = time.perf_counter()
        prompt = self._format_prompt(symptoms, system_prompt)

        sampler = make_sampler(temp=temperature)
        response = self._generate_with_retry(
            prompt=prompt, max_tokens=max_tokens, sampler=sampler, operation_name="medical_reasoning"
        )
        inference_time_ms = (time.perf_counter() - start_time) * 1000

        # Clean up and parse JSON response
        response = response.strip()
        result = self._parse_medical_response(response)

        # Store in cache (only for default system prompt)
        if cache_key is not None:
            self._put_in_cache(cache_key, result)
            logger.info(
                "Medical reasoning completed and cached",
                extra={
                    "cache_key": cache_key,
                    "inference_time_ms": round(inference_time_ms, 2),
                    "query_preview": symptoms[:50],
                },
            )
        else:
            logger.info(
                "Medical reasoning completed (not cached)",
                extra={"inference_time_ms": round(inference_time_ms, 2), "query_preview": symptoms[:50]},
            )

        return result

    def _get_fallback_reasoning(self, symptoms: str) -> MedicalReasoning:
        """
        Provide simple fallback reasoning when MedGemma times out.

        This ensures we always return a response, even if inference is slow.
        The fallback provides generic but safe advice.

        Args:
            symptoms: The original symptom query

        Returns:
            Basic MedicalReasoning with generic recommendations
        """
        logger.info("Using fallback medical reasoning")

        # Extract simple keywords for basic categorization
        symptoms_lower = symptoms.lower()

        # Determine basic treatment category
        if any(word in symptoms_lower for word in ["fever", "temperature", "температура"]):
            treatment_type = "antipyretics"
            likely_cause = "fever"
        elif any(word in symptoms_lower for word in ["pain", "headache", "болка", "главоболие"]):
            treatment_type = "pain relief"
            likely_cause = "pain"
        elif any(word in symptoms_lower for word in ["cough", "кашлица"]):
            treatment_type = "cough suppressants"
            likely_cause = "cough"
        elif any(word in symptoms_lower for word in ["allergy", "алергия"]):
            treatment_type = "antihistamines"
            likely_cause = "allergy"
        else:
            treatment_type = "general OTC treatment"
            likely_cause = "unspecified symptoms"

        return MedicalReasoning(
            symptoms=[symptoms[:100]],  # Truncate long symptoms
            likely_cause=likely_cause,
            treatment_type=treatment_type,
            warnings=["Consult a pharmacist for personalized advice"],
            see_doctor=False,
            explanation=f"Based on your symptoms, over-the-counter {treatment_type} may help.",
            how_treatment_helps="Addresses the symptoms you described",
            self_care_tips=["Rest", "Stay hydrated", "Monitor symptoms"],
            duration_guidance="Consult a healthcare provider if symptoms persist",
        )

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
        """Remove garbage phrases and JSON artifacts from text."""
        if not text:
            return text
        result = text

        # Remove JSON artifacts: leading/trailing quotes, commas, colons (multiple passes)
        # Handle cases like: 'viral infection",' or '"cough"'
        for _ in range(3):  # Multiple passes to handle nested artifacts
            result = result.strip()
            result = re.sub(r'^["\',;:\s]+', "", result)  # Leading artifacts
            result = re.sub(r'["\',;:\s]+$', "", result)  # Trailing artifacts

        # Remove escaped quotes within text
        result = result.replace('\\"', "").replace("\\'", "")

        # Remove garbage phrases
        for phrase in self.GARBAGE_PHRASES:
            result = result.replace(phrase, "").strip()

        # Clean up double spaces and punctuation
        result = re.sub(r"\s+", " ", result)
        result = re.sub(r"[,;:]+\s*[,;:]+", "", result)

        return result.strip()

    def _sanitize_reasoning(self, reasoning: MedicalReasoning) -> MedicalReasoning:
        """Sanitize all fields in MedicalReasoning to remove garbage text."""
        # Sanitize symptoms - filter out sentences and keep only symptom words
        sanitized_symptoms = []
        for s in reasoning.symptoms:
            s = self._sanitize_text(s)
            if s and self._is_valid_symptom(s):
                sanitized_symptoms.append(s)

        # Sanitize treatment_type - if it contains recovery info, move it
        treatment = self._sanitize_text(reasoning.treatment_type)
        duration = self._sanitize_text(reasoning.duration_guidance)

        # Check if treatment_type contains recovery info (common MedGemma error)
        if treatment and self._looks_like_recovery_info(treatment):
            if not duration:
                duration = treatment
            treatment = ""

        return MedicalReasoning(
            symptoms=sanitized_symptoms,
            likely_cause=self._sanitize_text(reasoning.likely_cause),
            treatment_type=treatment,
            warnings=[self._sanitize_text(w) for w in reasoning.warnings if self._sanitize_text(w)],
            see_doctor=reasoning.see_doctor,
            explanation=self._sanitize_text(reasoning.explanation),
            how_treatment_helps=self._sanitize_text(reasoning.how_treatment_helps),
            self_care_tips=[self._sanitize_text(t) for t in (reasoning.self_care_tips or []) if self._sanitize_text(t)],
            duration_guidance=duration,
        )

    def _is_valid_symptom(self, text: str) -> bool:
        """Check if text is a valid symptom (not a sentence or garbage)."""
        if not text:
            return False
        # Symptoms should be short (max 5-6 words typically)
        word_count = len(text.split())
        if word_count > 8:
            return False
        # Symptoms shouldn't contain these sentence indicators
        sentence_indicators = [
            " is ",
            " are ",
            " the ",
            " that ",
            " which ",
            " when ",
            " because ",
            " affecting ",
            " common ",
            " symptoms of ",
            "typically",
            "usually",
            "often",
            " or ",
            "worsen",
        ]
        text_lower = text.lower()
        if any(indicator in text_lower for indicator in sentence_indicators):
            return False
        return True

    def _looks_like_recovery_info(self, text: str) -> bool:
        """Check if text looks like recovery/duration info rather than treatment type."""
        if not text:
            return False
        recovery_indicators = [
            "days",
            "hours",
            "week",
            "resolve",
            "improvement",
            "typically",
            "usually",
            "within",
            "дни",
            "часа",
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in recovery_indicators)

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
            json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
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
        lines = response.split("\n")
        for line in lines:
            line_lower = line.lower()
            if "symptom" in line_lower or "симптом" in line_lower:
                # Extract symptoms
                parts = line.split(":", 1)
                if len(parts) > 1:
                    symptoms = [s.strip() for s in parts[1].split(",") if s.strip()]
            elif "cause" in line_lower or "причина" in line_lower:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    likely_cause = parts[1].strip()
            elif "treatment" in line_lower or "лечение" in line_lower:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    treatment_type = parts[1].strip()
            elif "warning" in line_lower or "предупрежден" in line_lower:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    warnings = [parts[1].strip()]
            elif "doctor" in line_lower or "лекар" in line_lower:
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
        self, user_query: str, medical_reasoning: str, candidate_products: list, max_products: int = 3
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
            name = getattr(product, "title", None) or getattr(product, "name", "Unknown")

            # Include similarity score to help LLM factor in search confidence
            score = getattr(product, "score", 0.0)
            relevance = "high" if score >= 0.5 else "medium" if score >= 0.35 else "low"
            product_info = f"{i}. [{relevance} relevance] {name}"

            # Add description/indications (expanded)
            desc = getattr(product, "description", None) or getattr(product, "indications", None)
            if desc:
                product_info += f"\n   Description: {desc[:200]}"

            # Add composition (active ingredients)
            composition = getattr(product, "composition", None)
            if composition:
                product_info += f"\n   Composition: {composition[:150]}"

            # Add contraindications (full for safety)
            contra = getattr(product, "contraindications", None)
            if contra:
                product_info += f"\n   Contraindications: {contra[:200]}"

            product_list.append(product_info)

        products_str = "\n".join(product_list)

        refinement_prompt = f"""You are a virtual pharmacist. Select the {max_products} most clinically appropriate products.

Customer query: {user_query}

Medical analysis: {medical_reasoning}

Available products (with details):
{products_str}

Selection criteria (in priority order):
1. PREFER products with proven active pharmaceutical ingredients (paracetamol, ibuprofen, cetirizine, etc.) over homeopathic or herbal products
2. For single symptoms, PREFER simple single-ingredient products over combination cold/flu products
3. Active ingredients must match the treatment type (e.g., antipyretics → paracetamol/ibuprofen, NOT cough suppressants)
4. Avoid products whose contraindications match the user's conditions
5. Prefer high/medium relevance over low

CRITICAL: A "fever only" query should get a pure antipyretic (paracetamol or ibuprofen), NOT a combination cold/flu product and NOT homeopathy.

Respond with ONLY valid JSON in this exact format: {{"selected": [1, 3, 5]}}
Replace the numbers with your chosen product numbers. Output nothing else.
"""

        prompt = self._format_prompt(refinement_prompt)

        sampler = make_sampler(temp=0.0)  # Fully deterministic for product selection
        response = self._generate_with_retry(
            prompt=prompt, max_tokens=50, sampler=sampler, operation_name="product_selection"
        )

        # Parse the response to get product indices
        selected_indices = self._parse_product_selection(response, len(candidate_products), max_products)

        return [candidate_products[i] for i in selected_indices]

    def _parse_product_selection(self, response: str, num_candidates: int, max_products: int) -> list[int]:
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
            json_match = re.search(r"\{[^{}]*\}", response_stripped)
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
                            extra={"selected_indices": selected_indices, "response": response_stripped},
                        )
                        return selected_indices
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug(f"JSON parsing failed: {e}", extra={"response": response_stripped})

        # Attempt 2: Extract numbers at start of response (e.g., "1, 3, 5")
        # Only look at first 20 chars to avoid extracting numbers from product descriptions
        first_part = response_stripped[:20]
        try:
            numbers = re.findall(r"\d+", first_part)
            for num in numbers:
                idx = int(num) - 1
                if 0 <= idx < num_candidates and idx not in selected_indices:
                    selected_indices.append(idx)
                if len(selected_indices) >= max_products:
                    break
            if selected_indices:
                logger.warning(
                    "Product selection used regex fallback (JSON parsing failed)",
                    extra={"selected_indices": selected_indices, "response": response_stripped},
                )
                return selected_indices
        except (ValueError, TypeError) as e:
            logger.debug(f"Regex extraction failed: {e}")

        # Fallback: return first N products
        logger.warning(
            "Product selection fallback to first N products - LLM response could not be parsed",
            extra={"response": response_stripped, "fallback_count": max_products},
        )
        return list(range(min(max_products, num_candidates)))


# Global model instance (lazy loaded)
_medical_model: MedicalModel | None = None


def get_medical_model(
    model_path: str | None = None,
    cache_size: int | None = None,
    use_bulgarian: bool | None = None,
    use_singleton: bool = True,
) -> MedicalModel:
    """
    Get or create a medical model instance with optional dependency injection.

    Args:
        model_path: Optional path to MedGemma model (uses settings default if None)
        cache_size: Optional cache size (uses default if None)
        use_bulgarian: Optional flag for Bulgarian generation (uses settings if None)
        use_singleton: If True (default), returns cached singleton when no params provided.
                       If False or params provided, creates new instance.

    Returns:
        MedicalModel instance

    Examples:
        # Production: Use singleton
        model = get_medical_model()

        # Testing: Create fresh instance
        model = get_medical_model(use_singleton=False)

        # Testing: Inject specific config
        model = get_medical_model(model_path="/custom/path", use_singleton=False)
    """
    global _medical_model
    from src.config import get_settings

    settings = get_settings()

    # If any parameters provided, create new instance (bypass singleton)
    if any(p is not None for p in [model_path, cache_size, use_bulgarian]) or not use_singleton:
        model_path = model_path or os.environ.get("MEDGEMMA_MODEL_PATH", settings.medgemma_model_path)
        use_bulgarian = use_bulgarian if use_bulgarian is not None else settings.generate_bulgarian_directly
        return MedicalModel(model_path=model_path, cache_size=cache_size or REASONING_CACHE_SIZE, use_bulgarian=use_bulgarian)

    # Otherwise use singleton pattern
    if _medical_model is None:
        model_path = os.environ.get("MEDGEMMA_MODEL_PATH", settings.medgemma_model_path)
        use_bulgarian = settings.generate_bulgarian_directly
        _medical_model = MedicalModel(model_path=model_path, use_bulgarian=use_bulgarian)
    return _medical_model


def reset_medical_model() -> None:
    """Reset the global medical model singleton (useful for testing)."""
    global _medical_model
    _medical_model = None
