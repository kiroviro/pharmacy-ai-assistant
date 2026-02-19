"""
Pipeline orchestrator for the ViaPharma OTC Chatbot.

Pipeline follows the Perplexity two-stage retrieval pattern:
1. Vector DB returns top-K candidates (fast, cheap)
2. LLM refines and picks best matches (accurate)
"""

import re
import time

from src.config import get_settings
from src.logging_config import get_logger
from src.medical_model import MedicalReasoning, get_medical_model
from src.medical_terms_validator import get_medical_validator
from src.common.contraindications import (
    extract_user_conditions,
    filter_by_contraindications,
)
from src.pipeline.constants import (
    CHILD_KEYWORDS,
    CHRONIC_DISEASE_KEYWORDS,
    SAFETY_KEYWORDS,
    USER_CONDITION_PATTERNS,
)

# Import from pipeline submodules
from src.common.models import PipelineResult, Product
from src.pipeline.ingredient_analyzer import IngredientAnalyzer
from src.pipeline.product_ingredients import (
    INGREDIENT_BG_NAMES,
    INGREDIENT_PATTERNS_GLOBAL,
    build_ingredient_duplication_warning,
    extract_all_product_ingredients,
    extract_composition_summary,
    extract_contraindication_summary,
    extract_product_ingredient,
    is_combination_product,
)
from src.pipeline.product_matcher import ProductMatcher
from src.pipeline.query_router import (
    get_help_clarification_message,
    is_catalog_query,
    is_comparison_query,
    is_help_clarification_query,
    is_single_drug_name_query,
)
from src.pipeline.response_builder import ResponseBuilder
from src.pipeline.response_validator import TextValidator, get_text_validator
from src.pipeline.safety_validator import SafetyValidator
from src.product_store import get_product_store
from src.safety import get_safety_layer

# Service layer imports (Phase 5)
from src.services import (
    MedicalReasoningService,
    ProductRecommendationService,
    SafetyCheckService,
)

from src.translator import get_translator
from src.unified_processor import UnifiedProcessorResult, get_unified_processor

logger = get_logger("viapharma.pipeline")


class Pipeline:
    """
    Main pipeline that orchestrates all processing steps.

    Uses Perplexity-style two-stage retrieval:
    - Stage 1: Fast vector search for candidates
    - Stage 2: LLM refinement for best matches
    """

    def __init__(
        self,
        lazy_load: bool = True,
        # Dependency injection (backward compatible - defaults to singletons)
        safety_layer=None,
        medical_validator=None,
        response_builder=None,
        product_store=None,
        medical_model=None,
        translator=None,
        unified_processor=None,
        settings=None,
        product_matcher=None,
        safety_validator=None,
        ingredient_analyzer=None,
        text_validator=None,
        # Service layer (Phase 5)
        medical_reasoning_service=None,
        product_recommendation_service=None,
        safety_check_service=None,
    ):
        """
        Initialize the pipeline with dependency injection.

        Args:
            lazy_load: If True, models are loaded on first use. If False, load immediately.
            safety_layer: Optional SafetyLayer instance (defaults to singleton)
            medical_validator: Optional MedicalValidator instance (defaults to singleton)
            response_builder: Optional ResponseBuilder instance (defaults to new instance)
            product_store: Optional ProductStore instance (defaults to singleton)
            medical_model: Optional MedicalModel instance (defaults to singleton)
            translator: Optional Translator instance (defaults to singleton)
            unified_processor: Optional UnifiedProcessor instance (defaults to singleton)
            settings: Optional Settings instance (defaults to singleton)
            product_matcher: Optional ProductMatcher instance (defaults to new instance)
            safety_validator: Optional SafetyValidator instance (defaults to new instance)
            ingredient_analyzer: Optional IngredientAnalyzer instance (defaults to new instance)
            text_validator: Optional TextValidator instance (defaults to new instance)
        """
        # Initialize dependencies (use provided or fall back to singletons)
        self.safety_layer = safety_layer or get_safety_layer()
        self.medical_validator = medical_validator or get_medical_validator()
        self.response_builder = response_builder or ResponseBuilder()

        # Product store (can be provided or lazy loaded)
        self._product_store = product_store
        self._product_store_provided = product_store is not None

        # Models (can be provided or lazy loaded)
        self._medical_model = medical_model
        self._medical_model_provided = medical_model is not None

        self._translator = translator
        self._translator_provided = translator is not None

        self._unified_processor = unified_processor
        self._unified_processor_provided = unified_processor is not None

        self._lazy_load = lazy_load

        # Feature flags
        settings = settings or get_settings()
        self._generate_bulgarian_directly = getattr(settings, "generate_bulgarian_directly", False)

        # Product matcher (uses product_store and medical_model via properties)
        self.product_matcher = product_matcher or ProductMatcher(
            product_store=self.product_store,
            medical_model=self.medical_model
        )

        # Safety validator (handles age filtering, severity filtering, disclaimers)
        self.safety_validator = safety_validator or SafetyValidator()

        # Ingredient analyzer (handles ingredient extraction and display)
        self.ingredient_analyzer = ingredient_analyzer or IngredientAnalyzer()

        # Text validator (handles garbage detection, Bulgarian ratio, English leaks)
        self.text_validator = text_validator or get_text_validator(translator=self.translator)

        # Service layer (Phase 5) - orchestrates business logic
        self.medical_reasoning_service = medical_reasoning_service or MedicalReasoningService(
            medical_model=self.medical_model,
            user_condition_patterns=USER_CONDITION_PATTERNS
        )

        self.product_recommendation_service = product_recommendation_service or ProductRecommendationService(
            product_matcher=self.product_matcher,
            safety_validator=self.safety_validator,
            safety_layer=self.safety_layer,
            medical_reasoning_service=self.medical_reasoning_service
        )

        self.safety_check_service = safety_check_service or SafetyCheckService(
            safety_layer=self.safety_layer,
            safety_validator=self.safety_validator,
            medical_reasoning_service=self.medical_reasoning_service
        )

        if not lazy_load:
            self._load_translator()
            self._load_product_store()
            self._load_unified_processor()

    @property
    def product_store(self):
        """Get the product store, loading lazily if necessary."""
        if self._product_store is None:
            self._product_store = get_product_store()
        return self._product_store

    @property
    def translator(self):
        """Get the translator, loading lazily if necessary."""
        if self._translator is None:
            self._translator = get_translator()
        return self._translator

    @property
    def medical_model(self):
        """Get the medical model, loading lazily if necessary."""
        if self._medical_model is None:
            self._medical_model = get_medical_model()
            if not self._medical_model_provided:  # Only call load() if we created it
                self._medical_model.load()
        return self._medical_model

    @property
    def unified_processor(self):
        """Get the unified processor, loading lazily if necessary."""
        if self._unified_processor is None:
            self._unified_processor = get_unified_processor()
            if not self._unified_processor_provided:  # Only call load() if we created it
                self._unified_processor.load()
        return self._unified_processor

    def _load_unified_processor(self):
        """Load the unified processor."""
        if self._unified_processor is None:
            self._unified_processor = get_unified_processor()
        if not self._unified_processor_provided:
            self._unified_processor.load()

    def _load_product_store(self):
        """Load the product store."""
        if self._product_store is None:
            self._product_store = get_product_store()

    def _load_translator(self):
        """Load the translator models."""
        if self._translator is None:
            self._translator = get_translator()
        if not self._translator_provided:
            self._translator.load_all()

    def _load_medical_model(self):
        """Load the MedGemma model."""
        if self._medical_model is None:
            self._medical_model = get_medical_model()
        if not self._medical_model_provided:
            self._medical_model.load()

    # =========================================================================
    # Catalog & Comparison Processing
    # =========================================================================
    def _process_comparison_query(self, user_input: str, drug_names: list[str]) -> PipelineResult:
        """
        Process a medication comparison query.

        Instead of trying to recommend products, provide educational information
        about the compared medications and show products for each drug.
        """
        start_time = time.perf_counter()
        logger.info("Processing comparison query", extra={"drugs": drug_names})

        # Search for products containing each drug
        all_products = []
        products_by_drug = {}

        for drug in drug_names:
            results = self.product_store.hybrid_search(drug, n_results=6)
            products = self._convert_to_products(results)
            products = self.safety_layer.filter_otc_only(products)

            # Filter to only products that actually contain the drug name
            filtered = []
            drug_lower = drug.lower()
            for p in products:
                title_lower = p.title.lower() if hasattr(p, "title") else ""
                desc_lower = p.description.lower() if hasattr(p, "description") else ""
                if drug_lower in title_lower or drug_lower in desc_lower:
                    filtered.append(p)

            products_by_drug[drug] = filtered[:3]  # Max 3 per drug
            all_products.extend(filtered[:3])

        # Format the comparison response
        response = self.response_builder.format_comparison_response(drug_names, products_by_drug)

        # Validate response for garbage text
        if self.text_validator.contains_garbage(response):
            cleaned_response = self.text_validator.filter_garbage_sentences(response)
            if cleaned_response:
                logger.info("Comparison response cleaned")
                response = cleaned_response

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Comparison query completed",
            extra={"duration_ms": round(duration_ms, 2), "drugs": drug_names, "products_found": len(all_products)},
        )

        return PipelineResult(
            response=response,
            is_medical=True,
            is_red_flag=False,
            original_text=user_input,
            candidate_products=all_products[:6],
        )

    # Generic terms that shouldn't be used for strict filtering
    _GENERIC_TERMS = {
        "мг",
        "mg",
        "мл",
        "ml",
        "капсули",
        "таблетки",
        "сироп",
        "капки",
        "крем",
        "гел",
        "разтвор",
        "суспензия",
        "за",
        "при",
        "х",
        "g",
        "гр",
    }

    def _process_catalog_query(self, user_input: str, search_term: str) -> PipelineResult:
        """
        Process a catalog query without medical reasoning.

        This is the fast path for "What brands of X do you have?" type queries.
        Now uses hybrid search for better brand/product name matching.
        """
        start_time = time.perf_counter()
        logger.info("Processing catalog query", extra={"search_term": search_term})

        # Direct product search - no medical reasoning needed
        if self.product_store.collection.count() == 0:
            logger.warning("Product store is empty")
            return PipelineResult(
                response="Съжалявам, каталогът с продукти не е зареден.", is_medical=True, original_text=user_input
            )

        # Use hybrid search for better brand/product name matching
        results = self.product_store.hybrid_search(search_term, n_results=12)  # Get more for filtering
        products = self._convert_to_products(results)

        # Filter OTC only
        products = self.safety_layer.filter_otc_only(products)

        # For catalog queries, filter to products that actually contain the key search terms
        # This prevents matching on generic terms like "мг", "капсули", etc.
        products = self.product_matcher.filter_by_name_match(products, search_term)

        # Format catalog response with VP template (safety, triage, footer)
        response = self.response_builder.format_catalog_response(search_term, products, user_input)

        # Validate response for garbage text
        if self.text_validator.contains_garbage(response):
            cleaned_response = self.text_validator.filter_garbage_sentences(response)
            if cleaned_response:
                logger.info("Catalog response cleaned")
                response = cleaned_response

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Catalog query completed", extra={"duration_ms": round(duration_ms, 2), "products_found": len(products)}
        )

        return PipelineResult(
            response=response,
            is_medical=True,  # Still pharmacy-related
            is_red_flag=False,
            original_text=user_input,
            candidate_products=products,
            selected_products=products[:3],
        )

    # Standard OTC disclaimer for all responses
    _OTC_DISCLAIMER = (
        "\n---\n⚠️ *Тази информация е само за справка. Консултирайте се с фармацевт или лекар за персонална препоръка.*"
    )

    # Issue 8: Response length standardization - consistent UX
    _MAX_EXPLANATION_LEN = 350
    _MAX_HOW_HELPS_LEN = 200
    _MAX_TIP_LEN = 120
    _MAX_WARNING_LEN = 150
    _MAX_DURATION_LEN = 120

    def _truncate_for_display(self, text: str, max_len: int, suffix: str = "...") -> str:
        """Truncate text to max length, preserving word boundary."""
        if not text or len(text) <= max_len:
            return text
        truncated = text[: max_len - len(suffix)]
        last_space = truncated.rfind(" ")
        if last_space > max_len // 2:
            truncated = truncated[:last_space]
        return truncated.rstrip(".,;:") + suffix

    def process(self, user_input: str) -> PipelineResult:
        """
        Process user input through the unified LLM processor.

        The unified processor handles all steps in a single LLM call:
        - Intent classification
        - Safety assessment
        - Medical reasoning
        - Product extraction and recommendation

        Fast-path safety checks (emergencies) and catalog queries are handled first.
        """
        start_time = time.perf_counter()
        logger.info(
            "Processing query",
            extra={
                "query_length": len(user_input),
                "query_preview": user_input[:50] + "..." if len(user_input) > 50 else user_input,
            },
        )

        # Step 0: Hard-coded safety fast-path (ALWAYS runs - non-negotiable)
        fast_safety = self.safety_layer.check_safety(user_input)
        if fast_safety.severity == "emergency":
            logger.warning("Emergency detected by fast-path safety check")
            return PipelineResult(
                response=fast_safety.message,
                is_medical=True,
                is_red_flag=True,
                original_text=user_input,
            )

        # Step 0b: Check for catalog queries (skip medical reasoning)
        is_catalog, search_term = is_catalog_query(user_input)
        if is_catalog:
            return self._process_catalog_query(user_input, search_term)

        # Step 0c: Check for medication comparison queries
        is_comparison, drug_names = is_comparison_query(user_input)
        if is_comparison:
            return self._process_comparison_query(user_input, drug_names)

        # Step 0d: Single drug/product name - "аспирин", "парацетамол" etc. → catalog search
        if is_single_drug_name_query(user_input):
            try:
                products = self.product_store.hybrid_search(user_input, n_results=8)
                products = self._convert_to_products(products)
                products = self.safety_layer.filter_otc_only(products)
                if products:
                    logger.info(
                        "Single drug name matched catalog", extra={"query": user_input, "products_found": len(products)}
                    )
                    return self._process_catalog_query(user_input, user_input)
            except Exception as e:
                logger.debug(f"Catalog search for drug name failed: {e}")

        # Step 0e: Ambiguous help/clarification queries - "помощ", "здравей"
        if is_help_clarification_query(user_input):
            return PipelineResult(response=get_help_clarification_message(), is_medical=False, original_text=user_input)

        # Route to unified processor
        return self._process_with_unified_processor(user_input, start_time)

    # =========================================================================
    # UNIFIED PROCESSOR PATH (LLM-driven)
    # =========================================================================

    def _process_with_unified_processor(self, user_input: str, start_time: float) -> PipelineResult:
        """
        Process query using the unified LLM processor.

        This replaces the legacy multi-step flow with a single LLM call that handles:
        - Intent classification
        - Safety detection (augments hard-coded fast-path)
        - Condition extraction
        - Translation
        - Medical reasoning

        Args:
            user_input: User query (Bulgarian or English)
            start_time: Start time for duration tracking

        Returns:
            PipelineResult
        """
        logger.info("Using unified LLM processor")

        # Get unified processing result
        llm_result = self.unified_processor.process(user_input)

        # Check intent (replaces intent_classifier)
        if not llm_result.intent.is_pharmacy_related:
            logger.debug(
                "Query rejected by unified processor",
                extra={
                    "confidence": llm_result.intent.confidence,
                    "reason": llm_result.intent.rejection_reason,
                },
            )
            rejection_message = (
                "Съжалявам, но мога да помагам само със здравни въпроси, лекарства и аптечни продукти. "
                "Моля, попитайте нещо свързано със здраве."
            )
            return PipelineResult(
                response=rejection_message,
                is_medical=False,
                original_text=user_input,
            )

        # Hybrid safety check (hard-coded + LLM)
        safety_result = self.safety_layer.check_safety_with_llm_result(
            text=user_input,
            llm_safety_level=llm_result.safety.level,
            llm_detected_flags=llm_result.safety.detected_flags,
        )

        if safety_result.is_red_flag:
            logger.warning(
                "Red flag detected by hybrid safety check",
                extra={
                    "severity": safety_result.severity,
                    "matched": safety_result.matched_symptoms,
                },
            )
            return PipelineResult(
                response=safety_result.message,
                is_medical=True,
                is_red_flag=True,
                original_text=user_input,
                translated_text=llm_result.extraction.query_translated,
            )

        # Build MedicalReasoning from unified result (for compatibility)
        medical_reasoning = self.medical_reasoning_service.build_medical_reasoning_from_unified(llm_result)

        # Product retrieval (uses vector DB + age filtering)
        candidate_products = self.product_matcher.retrieve_candidates(medical_reasoning, user_input)
        candidate_products = self.safety_layer.filter_otc_only(candidate_products)
        candidate_products = self.safety_validator.filter_by_age_appropriateness(candidate_products, user_input)

        # Filter by contraindications
        contraindicated_products = []
        if llm_result.extraction.user_conditions:
            candidate_products, contraindicated_products = filter_by_contraindications(
                products=candidate_products,
                user_conditions=llm_result.extraction.user_conditions,
                strict=True,
            )

        # Product refinement (uses existing LLM-based refinement)
        # Step 1: Pharmacological reranking
        reranked_products = self.product_matcher.pharmacological_rerank(
            candidate_products, medical_reasoning.treatment_type
        )

        # Step 2: LLM-based refinement
        refined_products = self.product_matcher.refine_selection(
            reranked_products, medical_reasoning, max_products=5  # Get extra for deduplication
        )

        # Step 3: Deduplicate by ingredient
        selected_products = self.product_matcher.deduplicate_by_ingredient(
            refined_products, max_products=3
        )

        # Format response using unified result's Bulgarian translations
        final_response = self._format_response_from_unified(llm_result, selected_products, user_input)

        # Add disclaimers based on conditions detected by LLM
        if "child" in llm_result.extraction.user_conditions or llm_result.extraction.age_group in ("infant", "child"):
            final_response = self.safety_validator.add_child_disclaimer(final_response)

        if llm_result.reasoning and llm_result.reasoning.see_doctor:
            # Add general doctor recommendation if not already in response
            if "консултация с лекар" not in final_response.lower():
                final_response = self.safety_layer.add_safety_disclaimer(final_response, safety_result)

        if contraindicated_products:
            final_response = self._add_contraindication_warning(
                final_response,
                contraindicated_products,
                llm_result.extraction.user_conditions,
            )

        # Garbage text validation INTENTIONALLY DISABLED (Issue #17 - Phase 1)
        # Investigation (Code Quality Review Issue #7):
        # - filter_garbage_sentences() destroyed 77% of valid content (2748 → 627 chars)
        # - Too aggressive: removes sentences <10 chars, splits on commas (breaks markdown),
        #   filters >40% uppercase (breaks product names/medical terms)
        # - E2E regression test in test_e2e_regression.py verifies this stays disabled
        # DECISION: Keep disabled. Upstream LLM quality is good enough.
        # if self.text_validator.contains_garbage(final_response):
        #     cleaned_response = self.text_validator.filter_garbage_sentences(final_response)
        #     if cleaned_response:
        #         final_response = cleaned_response

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Unified processor pipeline completed",
            extra={
                "duration_ms": round(duration_ms, 2),
                "llm_time_ms": round(llm_result.processing_time_ms, 2),
                "candidates": len(candidate_products),
                "selected": len(selected_products),
                "conditions": llm_result.extraction.user_conditions,
            },
        )

        return PipelineResult(
            response=final_response,
            is_medical=True,
            is_red_flag=False,
            original_text=user_input,
            translated_text=llm_result.extraction.query_translated,
            medical_reasoning=medical_reasoning,
            candidate_products=candidate_products,
            selected_products=selected_products,
            user_conditions=llm_result.extraction.user_conditions,
            contraindicated_products=contraindicated_products,
        )

    def _format_response_from_unified(
        self,
        llm_result: UnifiedProcessorResult,
        products: list,
        original_query: str = "",
    ) -> str:
        """
        Format response using the unified processor's Bulgarian output.

        Updated template (Feb 2026):
        🔍 Info → 💊 Ingredients → 💧 Tip → 🛡️ Safety (small) →
        🛒 Products (prominent) → ⚠️ Triage → ℹ️ Footer
        """
        parts = []
        reasoning = llm_result.reasoning

        if not reasoning:
            parts.append("## 🔍 Информация\n")
            parts.append("*Не можах да анализирам запитването.*")
            return "\n".join(parts)

        medical_reasoning = self.medical_reasoning_service.build_medical_reasoning_from_unified(llm_result)

        # ── SECTION 1: Symptom info header ──────────────────────────────
        symptom_label = self._build_symptom_header(llm_result.extraction.symptoms, original_query)
        parts.append(f"## 🔍 Информация при симптом: {symptom_label}\n")

        # Explanation (prefer _bg, filter garbage sentences, clean English leaks)
        expl_text = None
        if reasoning.explanation_bg and self.text_validator.calculate_bulgarian_ratio(reasoning.explanation_bg) >= 0.65:
            expl_text = reasoning.explanation_bg
        elif reasoning.explanation:
            # If generating Bulgarian directly, explanation is already in Bulgarian
            if self._generate_bulgarian_directly:
                expl_text = reasoning.explanation
            else:
                translated = self.translator.translate_to_bulgarian(reasoning.explanation)
                if translated and self.text_validator.calculate_bulgarian_ratio(translated) > 0.3:
                    expl_text = translated
        if expl_text:
            filtered = self.text_validator.filter_garbage_sentences(expl_text)
            if filtered:
                parts.append(self.text_validator.clean_english_leaks(filtered))

        parts.append("")

        # ── SECTION 2: Active ingredients ───────────────────────────────
        # ALWAYS show this section when products are present (Issue #18)
        parts.append("---")
        treatment_type = reasoning.treatment_category or ""
        recommended_ingredients = self.ingredient_analyzer.get_recommended_ingredients(treatment_type)
        # Fallback: derive from products when LLM omits (P3 improvement)
        if not recommended_ingredients and products:
            seen = set()
            for p in products[:5]:
                for ing in extract_all_product_ingredients(p):
                    seen.add(ing)
            recommended_ingredients = list(seen)[:5]
        symptom_count = len(llm_result.extraction.symptoms) if llm_result.extraction.symptoms else 1

        # Show ingredients section if we have products (even if ingredient extraction failed)
        if products:
            parts.append("## 💊 Подходящи активни съставки\n")
            if recommended_ingredients:
                ingredient_names_bg = [INGREDIENT_BG_NAMES.get(ing, ing) for ing in recommended_ingredients]
                for name_bg in ingredient_names_bg:
                    parts.append(f"• **{name_bg}**")
                action_text = self.ingredient_analyzer.get_treatment_action_text(treatment_type)
                if action_text:
                    parts.append(f"\n{action_text}")
            else:
                # Fallback when ingredient extraction fails (Issue #18)
                parts.append("*Проверете активните съставки и дозировката в листовката на продукта.*")

        # Self-care tip (inline, one line with 💧) — filter garbage from LLM
        tips_bg = reasoning.self_care_tips_bg or []
        tips_bg = [
            t
            for t in tips_bg[:3]
            if t and self.text_validator.calculate_bulgarian_ratio(t) >= 0.65 and self.text_validator.is_valid_self_care_tip(t)
        ]
        if not tips_bg and reasoning.self_care_tips:
            for tip in reasoning.self_care_tips[:3]:
                # If generating Bulgarian directly, tips are already in Bulgarian
                if self._generate_bulgarian_directly:
                    if self.text_validator.is_valid_self_care_tip(tip):
                        tips_bg.append(tip)
                else:
                    translated = self.translator.translate_to_bulgarian(tip)
                    if translated and self.text_validator.calculate_bulgarian_ratio(translated) > 0.3:
                        if self.text_validator.is_valid_self_care_tip(translated):
                            tips_bg.append(translated)
        if tips_bg:
            parts.append(f"\n💧 {tips_bg[0]}")
            for extra in tips_bg[1:2]:  # max 2 tips
                parts.append(f"💧 {extra}")

        parts.append("")

        # ── SECTION 3: Safety block (compact, small text) ──────────────
        parts.append("---")
        safety_block = self.response_builder.build_safety_block(medical_reasoning, products, original_query)
        if safety_block:
            parts.append(safety_block)
            parts.append("")

        # ── SECTION 4: Products (prominent, with separators) ───────────
        parts.append("---")
        parts.append("## 🛒 Подходящи продукти\n")
        if products:
            displayed_products = self.safety_validator.filter_by_severity(products, symptom_count)
            # Add combo note when showing cold/flu combo products
            any_combo = any(
                len(extract_all_product_ingredients(p)) >= 2
                or "грип" in (p.title or "").lower()
                or "настинка" in (p.title or "").lower()
                or "простуд" in (p.title or "").lower()
                for p in displayed_products
            )
            if any_combo:
                if symptom_count <= 1:
                    # Single symptom - explain why combo might be shown
                    parts.append(
                        "*Комбиниран продукт за грип/настинка. При единствен симптом (напр. само температура) по-подходящ е продукт само с една активна съставка.*\n"
                    )
                else:
                    # Multiple symptoms - explain that combo addresses multiple symptoms
                    parts.append(
                        "*Комбиниран продукт, подходящ при няколко симптома едновременно (температура, кашлица, хрема и др.).*\n"
                    )
            for i, product in enumerate(displayed_products, 1):
                if i > 1:
                    parts.append("---")
                product_block = self.response_builder.format_product_card(product, i, treatment_type, medical_reasoning)
                parts.append(product_block)
        else:
            parts.append("*Съжалявам, не намерих подходящи продукти в каталога.*")

        parts.append("")

        # ── SECTION 5: Triage (always shown) ───────────────────────────
        parts.append("---")
        parts.append("## ⚠️ Потърсете лекар ако:\n")
        triage_items = self._collect_triage_items_unified(reasoning, medical_reasoning, products, original_query)
        for item in triage_items:
            parts.append(f"• {item}")
        parts.append("")

        # ── SECTION 6: Footer ──────────────────────────────────────────
        parts.append("---")
        parts.append("ℹ️ **Важна информация**")
        parts.append("Информацията има общ характер и не замества консултация с лекар или фармацевт.")
        parts.append("Преди употреба прочетете листовката.")

        response = "\n".join(parts)
        # Final garbage cleanup pass (Issue #17)
        return self.response_builder._final_garbage_cleanup(response)

    def _collect_triage_items_unified(self, reasoning, medical_reasoning, products, original_query) -> list[str]:
        """Collect triage bullet points for the unified path."""
        items = []
        seen = set()

        # LLM-generated warnings (prefer Bulgarian)
        warnings_bg = reasoning.warnings_bg or []
        warnings_bg = [w for w in warnings_bg[:3] if w and self.text_validator.calculate_bulgarian_ratio(w) >= 0.65]
        if not warnings_bg and reasoning.warnings:
            for warning in reasoning.warnings[:3]:
                # If generating Bulgarian directly, warnings are already in Bulgarian
                if self._generate_bulgarian_directly:
                    warnings_bg.append(warning)
                else:
                    translated = self.translator.translate_to_bulgarian(warning)
                    if translated and self.text_validator.calculate_bulgarian_ratio(translated) > 0.3:
                        warnings_bg.append(translated)

        # Filter garbage from LLM-generated warnings (Issue #17)
        for w in warnings_bg:
            w_lower = w.lower()
            # Skip warnings containing garbage patterns
            has_garbage = any(
                pattern in w_lower
                for pattern in [
                    "зъбні протези",
                    "грижа за зъбні протези",
                    "защита на личните",
                    "средство за защита",
                    "репелент",
                    "комар",
                    "комари",
                    "пластмасов",
                    "ламарин",
                    "металокерамика",
                ]
            )
            if not has_garbage:
                items.append(w)
                seen.add(w[:20])
            else:
                logger.warning(f"Filtered garbage from triage warning: {w[:100]}")

        # Data-driven triage from products
        if products:
            for item in self.response_builder.build_triage_defaults(medical_reasoning, products, original_query):
                if item[:20] not in seen:
                    items.append(item)
                    seen.add(item[:20])

        if reasoning.see_doctor and "консултация" not in " ".join(items).lower():
            items.append("🏥 Препоръчваме консултация с лекар за вашите симптоми.")

        # Sensible defaults if nothing
        if not items:
            items = [
                "Симптомите продължават повече от 3 дни",
                "Състоянието се влошава или се появяват нови симптоми",
                "Имате висока температура (>39°C)",
            ]
        return items

    def _translate_to_bulgarian(self, text: str) -> str:
        """Translate English to Bulgarian."""
        return self.translator.translate_to_bulgarian(text)

    def _convert_to_products(self, results: list) -> list:
        """Convert ChromaDB results to Product objects."""
        products = []
        for result in results:
            try:
                products.append(Product.from_chromadb(result))
            except Exception as e:
                logger.warning("Failed to parse product", extra={"error": str(e)})
        return products

    # Condition name translations for user-friendly messages
    _CONDITION_NAMES_BG = {
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

    def _add_contraindication_warning(
        self, response: str, contraindicated_products: list[tuple], user_conditions: list[str]
    ) -> str:
        """Contraindication info is now part of the product card warnings
        and the safety block in the main template. No extra block appended."""
        return response

    def _format_response(
        self,
        medical_reasoning: MedicalReasoning,
        products: list,
        translate_reasoning: bool = True,
        original_query: str = "",
    ) -> str:
        """Format response using the updated template (Feb 2026).

        🔍 Info → 💊 Ingredients → 💧 Tip → 🛡️ Safety (compact) →
        🛒 Products (prominent, separated) → ⚠️ Triage → ℹ️ Footer
        """
        parts = []

        # Collect all texts to translate in one batch for efficiency
        if translate_reasoning:
            texts_to_translate = self._collect_texts_for_translation(medical_reasoning)
            translated_texts = self._batch_translate_texts(texts_to_translate)

            # Validate and correct medical terms in translated text
            validated_texts = {}
            for key, text in translated_texts.items():
                if text:
                    corrected_text, issues = self.medical_validator.validate_and_correct(text, context=key)
                    validated_texts[key] = corrected_text
                else:
                    validated_texts[key] = text
            translated_texts = validated_texts
        else:
            translated_texts = {}

        def get_translated(key: str, original: str, min_length: int = 3) -> str | None:
            if not original or len(original) <= min_length:
                return None

            # If generating Bulgarian directly, text is already in Bulgarian - no translation needed
            if self._generate_bulgarian_directly:
                if self.text_validator.contains_garbage(original):
                    return None
                return self.text_validator.clean_english_leaks(original)

            if not translate_reasoning:
                return self.text_validator.clean_english_leaks(original)
            translated = translated_texts.get(key, original)
            if self.text_validator.contains_garbage(translated):
                return None
            # Reject text with too much English (< 60% Bulgarian chars)
            if self.text_validator.calculate_bulgarian_ratio(translated) < 0.60:
                fresh = self.translator.translate_to_bulgarian(original)
                if fresh and self.text_validator.calculate_bulgarian_ratio(fresh) >= 0.60:
                    return self.text_validator.clean_english_leaks(fresh)
                return None
            return self.text_validator.clean_english_leaks(translated)

        # ── SECTION 1: Symptom info header ──────────────────────────────
        symptom_label = self._build_symptom_header(medical_reasoning.symptoms, original_query)
        parts.append(f"## 🔍 Информация при симптом: {symptom_label}\n")

        # Explanation
        if cause := get_translated("likely_cause", medical_reasoning.likely_cause):
            parts.append(cause)
        if explanation := get_translated("explanation", medical_reasoning.explanation, min_length=10):
            explanation = self._truncate_for_display(explanation, self._MAX_EXPLANATION_LEN)
            parts.append(explanation)

        # Recovery timeline (inline)
        if medical_reasoning.duration_guidance:
            duration = get_translated("duration_guidance", medical_reasoning.duration_guidance)
            if duration and not any(bad in duration.lower() for bad in ["intron", "интрон", "лечение с", "терапия с"]):
                duration = self._truncate_for_display(duration, self._MAX_DURATION_LEN)
                if len(duration) >= 5:
                    parts.append(duration)

        parts.append("")

        # ── SECTION 2: Active ingredients ───────────────────────────────
        # ALWAYS show this section when products are present (Issue #18)
        parts.append("---")
        treatment_type = medical_reasoning.treatment_type or ""
        recommended_ingredients = self.ingredient_analyzer.get_recommended_ingredients(treatment_type)
        # Fallback: derive from products when LLM omits
        if not recommended_ingredients and products:
            seen = set()
            for p in products[:5]:
                for ing in extract_all_product_ingredients(p):
                    seen.add(ing)
            recommended_ingredients = list(seen)[:5]
        symptom_count = len(medical_reasoning.symptoms) if medical_reasoning.symptoms else 1

        # Show ingredients section if we have products (even if ingredient extraction failed)
        if products:
            parts.append("## 💊 Подходящи активни съставки\n")
            if recommended_ingredients:
                ingredient_names_bg = [INGREDIENT_BG_NAMES.get(ing, ing) for ing in recommended_ingredients]
                for name_bg in ingredient_names_bg:
                    parts.append(f"• **{name_bg}**")
                action_text = self.ingredient_analyzer.get_treatment_action_text(treatment_type)
                if action_text:
                    parts.append(f"\n{action_text}")
            else:
                # Fallback when ingredient extraction fails (Issue #18)
                parts.append("*Проверете активните съставки и дозировката в листовката на продукта.*")

        # Self-care tips (inline 💧, max 2) — filter garbage from LLM (Issue #17)
        if medical_reasoning.self_care_tips:
            for i, tip in enumerate(medical_reasoning.self_care_tips[:2]):
                if not tip or len(tip) < 5:
                    continue
                translated_tip = get_translated(f"tip_{i}", tip, min_length=5)
                if translated_tip:
                    translated_tip = self._truncate_for_display(translated_tip, self._MAX_TIP_LEN)
                    # Validate self-care tip and filter garbage patterns
                    if len(translated_tip) >= 5 and self.text_validator.is_valid_self_care_tip(translated_tip):
                        parts.append(f"\n💧 {translated_tip}")
                    elif len(translated_tip) >= 5:
                        logger.warning(f"Filtered garbage from self-care tip: {translated_tip[:100]}")

        parts.append("")

        # ── SECTION 3: Safety block (compact, smaller text) ────────────
        parts.append("---")
        safety_block = self.response_builder.build_safety_block(medical_reasoning, products, original_query)
        if safety_block:
            parts.append(safety_block)
            parts.append("")

        # ── SECTION 4: Products (prominent, with separators) ───────────
        parts.append("---")
        parts.append("## 🛒 Подходящи продукти\n")
        if products:
            displayed_products = self.safety_validator.filter_by_severity(products, symptom_count)
            for i, product in enumerate(displayed_products, 1):
                if i > 1:
                    parts.append("---")
                product_block = self.response_builder.format_product_card(product, i, treatment_type, medical_reasoning)
                parts.append(product_block)
        else:
            parts.append("*Съжалявам, не намерих подходящи продукти в каталога.*")

        parts.append("")

        # ── SECTION 5: Triage (always shown) ───────────────────────────
        parts.append("---")
        parts.append("## ⚠️ Потърсете лекар ако:\n")
        triage_items = self._collect_triage_items_legacy(medical_reasoning, products, original_query, get_translated)
        for item in triage_items:
            parts.append(f"• {item}")
        parts.append("")

        # ── SECTION 6: Footer ──────────────────────────────────────────
        parts.append("---")
        parts.append("ℹ️ **Важна информация**")
        parts.append("Информацията има общ характер и не замества консултация с лекар или фармацевт.")
        parts.append("Преди употреба прочетете листовката.")

        response = "\n".join(parts)
        # Final garbage cleanup pass (Issue #17)
        return self.response_builder._final_garbage_cleanup(response)

    def _collect_triage_items_legacy(self, medical_reasoning, products, original_query, get_translated) -> list[str]:
        """Collect triage bullet points for the legacy path."""
        items = []
        seen = set()

        # Model-generated warnings
        if medical_reasoning.warnings:
            for i, warning in enumerate(medical_reasoning.warnings):
                translated = get_translated(f"warning_{i}", warning, min_length=10)
                if translated:
                    translated = self._truncate_for_display(translated, self._MAX_WARNING_LEN)
                    if len(translated) >= 10:
                        # Filter garbage from warnings (Issue #17)
                        translated_lower = translated.lower()
                        has_garbage = any(
                            pattern in translated_lower
                            for pattern in [
                                "зъбні протези",
                                "грижа за зъбні протези",
                                "защита на личните",
                                "средство за защита",
                                "репелент",
                                "комар",
                                "комари",
                                "пластмасов",
                                "ламарин",
                                "металокерамика",
                            ]
                        )
                        if not has_garbage:
                            items.append(translated)
                            seen.add(translated[:20])
                        else:
                            logger.warning(f"Filtered garbage from triage warning: {translated[:100]}")

        # Data-driven triage
        if products:
            for item in self.response_builder.build_triage_defaults(medical_reasoning, products, original_query):
                if item[:20] not in seen:
                    items.append(item)
                    seen.add(item[:20])

        if medical_reasoning.see_doctor and "консултация" not in " ".join(items).lower():
            items.append("🏥 Препоръчваме консултация с лекар за вашите симптоми.")

        if not items:
            items = [
                "Симптомите продължават повече от 3 дни",
                "Състоянието се влошава или се появяват нови симптоми",
                "Имате висока температура (>39°C)",
            ]
        return items

    def _build_symptom_header(self, symptoms: list | None, original_query: str) -> str:
        """Build the symptom label for the header, e.g. 'Температура (38°C)'.

        Uses the original Bulgarian query to extract the most natural phrasing.
        Falls back to translating the first English symptom.
        """
        query = (original_query or "").strip()

        # Try to extract a clean symptom phrase from the original BG query
        if query:
            # Common BG symptom patterns
            q_lower = query.lower()
            for prefix in ["имам ", "имам силна ", "имам лека ", "чувствам "]:
                if q_lower.startswith(prefix):
                    label = query[len(prefix) :].strip().rstrip(".!?")
                    if label and len(label) < 60:
                        return label.capitalize()
            # If query is short enough, use it directly
            if len(query) < 50:
                return query.rstrip(".!?")

        # Fallback: translate first symptom
        if symptoms:
            for symptom in symptoms[:2]:
                translated = self.translator.translate_symptom(symptom)
                if translated and not self.text_validator.contains_garbage(translated):
                    return translated.capitalize()

        return "вашите симптоми"

    def _collect_texts_for_translation(self, medical_reasoning: MedicalReasoning) -> dict[str, str]:
        """Collect all texts from MedicalReasoning that need translation."""
        texts = {}

        # Symptoms
        if medical_reasoning.symptoms:
            for symptom in medical_reasoning.symptoms:
                if symptom and len(symptom) < 40:
                    texts[f"symptom_{symptom}"] = symptom

        if medical_reasoning.likely_cause:
            texts["likely_cause"] = medical_reasoning.likely_cause
        if medical_reasoning.explanation:
            texts["explanation"] = medical_reasoning.explanation
        if medical_reasoning.treatment_type:
            texts["treatment_type"] = medical_reasoning.treatment_type
        if medical_reasoning.how_treatment_helps:
            texts["how_treatment_helps"] = medical_reasoning.how_treatment_helps
        if medical_reasoning.duration_guidance:
            texts["duration_guidance"] = medical_reasoning.duration_guidance

        # Self-care tips
        if medical_reasoning.self_care_tips:
            for i, tip in enumerate(medical_reasoning.self_care_tips):
                if tip:
                    texts[f"tip_{i}"] = tip

        # Warnings
        if medical_reasoning.warnings:
            for i, warning in enumerate(medical_reasoning.warnings):
                if warning:
                    texts[f"warning_{i}"] = warning

        return texts

    def _batch_translate_texts(self, texts: dict[str, str]) -> dict[str, str]:
        """Batch translate all texts in one call for efficiency."""
        if not texts:
            return {}

        keys = list(texts.keys())
        values = list(texts.values())

        try:
            translated_values = self.translator.translate_batch_to_bulgarian(values)
            return dict(zip(keys, translated_values, strict=False))
        except Exception as e:
            logger.warning(f"Batch translation failed, falling back to originals: {e}")
            return texts


# Global pipeline instance (singleton for production use)
_pipeline: Pipeline | None = None


def get_pipeline(
    product_store=None,
    medical_model=None,
    translator=None,
    unified_processor=None,
    use_singleton: bool = True,
) -> Pipeline:
    """
    Get or create a pipeline instance with optional dependency injection.

    Args:
        product_store: Optional ProductStore instance (loads default if None)
        medical_model: Optional MedicalModel instance (loads default if None)
        translator: Optional Translator instance (loads default if None)
        unified_processor: Optional UnifiedProcessor instance (loads default if None)
        use_singleton: If True (default), returns cached singleton instance when
                       no dependencies are provided. If False or dependencies are
                       provided, creates a new instance.

    Returns:
        Pipeline instance

    Examples:
        # Production: Use singleton
        pipeline = get_pipeline()

        # Testing: Inject mocks
        pipeline = get_pipeline(
            product_store=mock_store,
            medical_model=mock_model,
            use_singleton=False
        )
    """
    global _pipeline

    # If dependencies are provided, always create new instance (bypass singleton)
    if any([product_store, medical_model, translator, unified_processor]):
        return Pipeline(
            product_store=product_store,
            medical_model=medical_model,
            translator=translator,
            unified_processor=unified_processor,
        )

    # If use_singleton=False, create new instance
    if not use_singleton:
        return Pipeline()

    # Otherwise use singleton pattern
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline


def reset_pipeline() -> None:
    """Reset the global pipeline singleton (useful for testing)."""
    global _pipeline
    _pipeline = None
