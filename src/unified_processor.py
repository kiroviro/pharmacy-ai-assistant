"""
Unified LLM Processor for the ViaPharma OTC Chatbot.

Consolidates intent classification, safety detection, condition extraction,
translation, and medical reasoning into a single LLM call for scalability.

Replaces hard-coded patterns with semantic understanding while maintaining
safety guarantees via hybrid architecture (hard-coded fast-path + LLM).
"""

import hashlib
import json
import re
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Literal, Optional

from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

from src.config import get_settings
from src.logging_config import get_logger
from src.prompts.unified_prompt import build_prompt, UNIFIED_SYSTEM_PROMPT

logger = get_logger("viapharma.unified_processor")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class IntentResult:
    """Intent classification result."""
    is_pharmacy_related: bool
    confidence: float
    rejection_reason: Optional[str] = None


@dataclass
class SafetyResult:
    """Safety detection result from LLM."""
    level: Literal["safe", "warning", "urgent", "emergency"]
    detected_flags: list[str] = field(default_factory=list)
    action: Literal["proceed", "warn_and_proceed", "refer_to_doctor", "call_emergency"] = "proceed"


@dataclass
class ExtractionResult:
    """Extracted information from query."""
    symptoms: list[str] = field(default_factory=list)  # English
    user_conditions: list[str] = field(default_factory=list)  # pregnancy, child, diabetes, etc.
    age_group: Optional[Literal["infant", "child", "adult", "elderly"]] = None
    query_translated: str = ""  # Bulgarian → English translation


@dataclass
class ReasoningResult:
    """Medical reasoning result."""
    treatment_category: str = ""
    explanation: str = ""
    explanation_bg: str = ""  # Bulgarian translation
    self_care_tips: list[str] = field(default_factory=list)
    self_care_tips_bg: list[str] = field(default_factory=list)  # Bulgarian
    warnings: list[str] = field(default_factory=list)
    warnings_bg: list[str] = field(default_factory=list)  # Bulgarian
    see_doctor: bool = False


@dataclass
class UnifiedProcessorResult:
    """
    Complete result from unified LLM processing.

    Consolidates all processing steps into a single structured output:
    - Intent classification (replaces intent_classifier.py)
    - Safety detection (augments safety.py)
    - Information extraction (replaces condition patterns)
    - Translation (replaces translator.py for queries)
    - Medical reasoning (enhances medical_model.py)
    """
    intent: IntentResult
    safety: SafetyResult
    extraction: ExtractionResult
    reasoning: Optional[ReasoningResult] = None

    # Metadata
    processing_time_ms: float = 0.0
    from_cache: bool = False
    raw_response: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "intent": asdict(self.intent),
            "safety": asdict(self.safety),
            "extraction": asdict(self.extraction),
            "reasoning": asdict(self.reasoning) if self.reasoning else None,
            "processing_time_ms": self.processing_time_ms,
            "from_cache": self.from_cache,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UnifiedProcessorResult":
        """Create from dictionary (e.g., from cache)."""
        return cls(
            intent=IntentResult(**data.get("intent", {})),
            safety=SafetyResult(**data.get("safety", {})),
            extraction=ExtractionResult(**data.get("extraction", {})),
            reasoning=ReasoningResult(**data["reasoning"]) if data.get("reasoning") else None,
            processing_time_ms=data.get("processing_time_ms", 0.0),
            from_cache=True,
        )


# =============================================================================
# LRU CACHE
# =============================================================================

class ProcessorCache:
    """LRU cache for unified processor results."""

    def __init__(self, max_size: int = 500):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def _normalize_query(self, query: str) -> str:
        """Normalize query for cache key generation."""
        if not query:
            return ""
        normalized = " ".join(query.lower().split())
        normalized = normalized.rstrip("?!.,;:")
        return normalized

    def _get_cache_key(self, query: str) -> str:
        """Generate cache key from normalized query."""
        normalized = self._normalize_query(query)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def get(self, query: str) -> Optional[UnifiedProcessorResult]:
        """Get cached result if available."""
        cache_key = self._get_cache_key(query)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            self._hits += 1
            logger.debug("Cache HIT", extra={"cache_key": cache_key})
            return UnifiedProcessorResult.from_dict(self._cache[cache_key])
        self._misses += 1
        return None

    def set(self, query: str, result: UnifiedProcessorResult) -> None:
        """Store result in cache."""
        cache_key = self._get_cache_key(query)
        while len(self._cache) >= self._max_size:
            evicted_key, _ = self._cache.popitem(last=False)
            logger.debug("Cache eviction", extra={"evicted_key": evicted_key})
        self._cache[cache_key] = result.to_dict()
        logger.debug("Cache STORE", extra={"cache_key": cache_key, "cache_size": len(self._cache)})

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 2),
        }

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        logger.info("Unified processor cache cleared")


# =============================================================================
# UNIFIED PROCESSOR
# =============================================================================

class UnifiedProcessor:
    """
    Unified LLM processor that consolidates multiple processing steps.

    Replaces:
    - intent_classifier.py (keyword-based → semantic)
    - translator.py (for query translation)
    - Condition extraction patterns in pipeline.py
    - Garbage filtering patterns in pipeline.py

    Augments:
    - safety.py (hard-coded fast-path remains, LLM catches paraphrases)
    - medical_model.py (single call instead of separate reasoning + refinement)
    """

    def __init__(
        self,
        model_path: str = "./models/medgemma-4b-it-bf16",
        cache_size: int = 500,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ):
        self.model_path = model_path
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.model = None
        self.tokenizer = None
        self._loaded = False

        self._cache = ProcessorCache(max_size=cache_size)

    def load(self) -> None:
        """Load the model into memory."""
        if self._loaded:
            return

        logger.info(f"Loading unified processor model from {self.model_path}...")
        start_time = time.perf_counter()
        self.model, self.tokenizer = load(self.model_path)
        self._loaded = True
        duration = time.perf_counter() - start_time
        logger.info("Unified processor model loaded", extra={"load_time_s": round(duration, 2)})

    def _format_prompt(self, user_query: str) -> str:
        """Format the prompt using Gemma chat template."""
        system_prompt = UNIFIED_SYSTEM_PROMPT
        user_prompt = build_prompt(user_query)

        # Gemma 3 format
        prompt = f"<start_of_turn>user\n{system_prompt}\n\n{user_prompt}<end_of_turn>\n<start_of_turn>model\n"
        return prompt

    def process(
        self,
        query: str,
        use_cache: bool = True,
        skip_reasoning: bool = False,
    ) -> UnifiedProcessorResult:
        """
        Process a user query through the unified LLM.

        Args:
            query: User query (Bulgarian or English)
            use_cache: Whether to use caching
            skip_reasoning: If True, only do intent/safety (faster for filtering)

        Returns:
            UnifiedProcessorResult with all processing outputs
        """
        if not query or not query.strip():
            return self._empty_result()

        # Check cache
        if use_cache:
            cached = self._cache.get(query)
            if cached is not None:
                logger.info("Returning cached unified result", extra={"query_preview": query[:50]})
                return cached

        # Load model if needed
        if not self._loaded:
            self.load()

        # Run inference
        start_time = time.perf_counter()
        prompt = self._format_prompt(query)

        sampler = make_sampler(temp=self.temperature)
        response = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=self.max_tokens,
            sampler=sampler,
        )
        inference_time_ms = (time.perf_counter() - start_time) * 1000

        # Parse response
        result = self._parse_response(response.strip(), query)
        result.processing_time_ms = inference_time_ms
        result.raw_response = response

        # Cache result
        if use_cache:
            self._cache.set(query, result)

        logger.info("Unified processing completed", extra={
            "inference_time_ms": round(inference_time_ms, 2),
            "is_pharmacy_related": result.intent.is_pharmacy_related,
            "safety_level": result.safety.level,
            "query_preview": query[:50],
        })

        return result

    def _empty_result(self) -> UnifiedProcessorResult:
        """Return result for empty query."""
        return UnifiedProcessorResult(
            intent=IntentResult(is_pharmacy_related=False, confidence=0.0, rejection_reason="empty_query"),
            safety=SafetyResult(level="safe", detected_flags=[], action="proceed"),
            extraction=ExtractionResult(),
            reasoning=None,
        )

    def _parse_response(self, response: str, original_query: str) -> UnifiedProcessorResult:
        """Parse the LLM JSON response into structured result."""
        # Try to extract JSON from response
        json_data = self._extract_json(response)

        if json_data is None:
            logger.warning("Failed to parse LLM response as JSON, using fallback", extra={"response": response[:200]})
            return self._fallback_result(original_query)

        try:
            return self._build_result_from_json(json_data)
        except Exception as e:
            logger.warning(f"Failed to build result from JSON: {e}", extra={"json_data": json_data})
            return self._fallback_result(original_query)

    def _extract_json(self, response: str) -> Optional[dict]:
        """Extract JSON object from response string."""
        # Try direct parse first
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return None

    def _build_result_from_json(self, data: dict) -> UnifiedProcessorResult:
        """Build UnifiedProcessorResult from parsed JSON."""
        # Intent
        intent_data = data.get("intent", {})
        intent = IntentResult(
            is_pharmacy_related=intent_data.get("is_pharmacy_related", True),
            confidence=float(intent_data.get("confidence", 0.5)),
            rejection_reason=intent_data.get("rejection_reason"),
        )

        # Safety
        safety_data = data.get("safety", {})
        safety = SafetyResult(
            level=safety_data.get("level", "safe"),
            detected_flags=safety_data.get("detected_flags", []),
            action=safety_data.get("action", "proceed"),
        )

        # Extraction
        extraction_data = data.get("extracted", data.get("extraction", {}))
        extraction = ExtractionResult(
            symptoms=extraction_data.get("symptoms", []),
            user_conditions=extraction_data.get("user_conditions", []),
            age_group=extraction_data.get("age_group"),
            query_translated=extraction_data.get("query_translated", ""),
        )

        # Reasoning (optional)
        reasoning = None
        reasoning_data = data.get("recommendation", data.get("reasoning", {}))
        if reasoning_data:
            reasoning = ReasoningResult(
                treatment_category=reasoning_data.get("treatment_category", ""),
                explanation=reasoning_data.get("explanation", ""),
                explanation_bg=reasoning_data.get("explanation_bg", ""),
                self_care_tips=reasoning_data.get("self_care_tips", []),
                self_care_tips_bg=reasoning_data.get("self_care_tips_bg", []),
                warnings=reasoning_data.get("warnings", []),
                warnings_bg=reasoning_data.get("warnings_bg", []),
                see_doctor=reasoning_data.get("see_doctor", False),
            )

        return UnifiedProcessorResult(
            intent=intent,
            safety=safety,
            extraction=extraction,
            reasoning=reasoning,
        )

    def _fallback_result(self, query: str) -> UnifiedProcessorResult:
        """
        Create fallback result when LLM parsing fails.

        Uses simple heuristics to provide a safe default.
        """
        logger.warning("Using fallback result due to LLM parsing failure")

        # Simple heuristics for fallback
        query_lower = query.lower()

        # Check for obvious non-medical queries
        non_medical_indicators = [
            "времето", "прогноза", "новини", "спорт", "рецепта за готвене",
            "weather", "news", "sports", "recipe", "joke",
        ]
        is_pharmacy = not any(indicator in query_lower for indicator in non_medical_indicators)

        # Check for emergency keywords
        emergency_keywords = [
            "не мога да дишам", "болка в гърдите", "загуба на съзнание",
            "can't breathe", "chest pain", "unconscious",
        ]
        is_emergency = any(kw in query_lower for kw in emergency_keywords)

        return UnifiedProcessorResult(
            intent=IntentResult(
                is_pharmacy_related=is_pharmacy,
                confidence=0.3,  # Low confidence for fallback
                rejection_reason=None if is_pharmacy else "non_medical_detected",
            ),
            safety=SafetyResult(
                level="emergency" if is_emergency else "safe",
                detected_flags=["fallback_detection"] if is_emergency else [],
                action="call_emergency" if is_emergency else "proceed",
            ),
            extraction=ExtractionResult(
                symptoms=[],
                user_conditions=[],
                age_group=None,
                query_translated=query,  # Use original as "translation"
            ),
            reasoning=None,  # No reasoning in fallback mode
        )

    def get_cache_stats(self) -> dict:
        """Get cache statistics for monitoring."""
        return self._cache.get_stats()

    def clear_cache(self) -> None:
        """Clear the processor cache."""
        self._cache.clear()


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_unified_processor: Optional[UnifiedProcessor] = None


def get_unified_processor() -> UnifiedProcessor:
    """Get or create the global unified processor instance."""
    global _unified_processor
    if _unified_processor is None:
        settings = get_settings()
        _unified_processor = UnifiedProcessor(
            model_path=settings.medgemma_model_path,
            cache_size=getattr(settings, 'unified_processor_cache_size', 500),
            temperature=getattr(settings, 'unified_processor_temperature', 0.1),
            max_tokens=getattr(settings, 'unified_processor_max_tokens', 800),
        )
    return _unified_processor
