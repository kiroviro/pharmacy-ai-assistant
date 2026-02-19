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
from src.pipeline.conditions import (
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
from src.pipeline.models import PipelineResult, Product
from src.pipeline.product_ingredients import (
    INGREDIENT_BG_NAMES,
    INGREDIENT_PATTERNS_GLOBAL,
    build_ingredient_duplication_warning,
    extract_all_product_ingredients,
    extract_composition_summary,
    extract_contraindication_summary,
    extract_product_ingredient,
    get_recommended_ingredients,
    is_combination_product,
)
from src.pipeline.query_router import (
    get_help_clarification_message,
    is_catalog_query,
    is_comparison_query,
    is_help_clarification_query,
    is_single_drug_name_query,
)
from src.pipeline.response_builder import ResponseBuilder
from src.pipeline.response_validator import validate_and_clean
from src.product_store import get_product_store
from src.safety import get_safety_layer
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
        is_valid, cleaned_response, validation_metadata = validate_and_clean(response, strict=False)
        if validation_metadata.get("cleaned", False):
            logger.info("Comparison response cleaned", extra={"patterns": validation_metadata.get("patterns_found", [])})
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

    def _filter_by_product_name_match(self, products: list, search_term: str) -> list:
        """
        Filter products to only those whose title contains key search terms.

        This prevents semantic search from returning unrelated products that match
        on generic terms like 'мг', 'капсули', etc.

        Args:
            products: List of Product objects
            search_term: The extracted search term (e.g., "нурофен 200 мг")

        Returns:
            Filtered list of products that contain at least one key term
        """
        # Extract key terms (excluding generic terms and short words)
        search_lower = search_term.lower()
        key_terms = [term for term in search_lower.split() if term not in self._GENERIC_TERMS and len(term) > 2]

        if not key_terms:
            # No key terms to filter on, return all
            return products

        logger.debug(f"Filtering products by key terms: {key_terms}")

        filtered = []
        for product in products:
            title_lower = product.title.lower() if hasattr(product, "title") else ""
            brand_lower = product.brand.lower() if hasattr(product, "brand") else ""

            # Check if any key term is in title or brand
            if any(term in title_lower or term in brand_lower for term in key_terms):
                filtered.append(product)
            else:
                logger.debug(f"Filtered out: {product.title[:40]}... (no match for {key_terms})")

        # If filtering removed all results, be more lenient and return top results
        if not filtered and products:
            logger.warning(f"No products matched key terms {key_terms}, returning top semantic matches")
            return products[:3]

        return filtered

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
        products = self._filter_by_product_name_match(products, search_term)

        # Format catalog response with VP template (safety, triage, footer)
        response = self.response_builder.format_catalog_response(search_term, products, user_input)

        # Validate response for garbage text
        is_valid, cleaned_response, validation_metadata = validate_and_clean(response, strict=False)
        if validation_metadata.get("cleaned", False):
            logger.info("Catalog response cleaned", extra={"patterns": validation_metadata.get("patterns_found", [])})
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
        medical_reasoning = self._build_medical_reasoning_from_unified(llm_result)

        # Product retrieval (uses vector DB + age filtering)
        candidate_products = self._retrieve_product_candidates(medical_reasoning, user_input)
        candidate_products = self.safety_layer.filter_otc_only(candidate_products)
        candidate_products = self._filter_by_age_appropriateness(candidate_products, user_input)

        # Filter by contraindications
        contraindicated_products = []
        if llm_result.extraction.user_conditions:
            candidate_products, contraindicated_products = filter_by_contraindications(
                products=candidate_products,
                user_conditions=llm_result.extraction.user_conditions,
                strict=True,
            )

        # Product refinement (uses existing LLM-based refinement)
        selected_products = self._refine_product_selection(
            user_query=llm_result.extraction.query_translated,
            medical_reasoning=medical_reasoning,
            candidates=candidate_products,
        )

        # Format response using unified result's Bulgarian translations
        final_response = self._format_response_from_unified(llm_result, selected_products, user_input)

        # Add disclaimers based on conditions detected by LLM
        if "child" in llm_result.extraction.user_conditions or llm_result.extraction.age_group in ("infant", "child"):
            final_response = self._add_child_disclaimer(final_response)

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

        # Validate response for garbage text (Issue #17 - Phase 1)
        is_valid, cleaned_response, validation_metadata = validate_and_clean(final_response, strict=False)

        if not is_valid:
            logger.error(
                "Response validation failed - garbage text detected and could not be cleaned",
                extra={
                    "patterns_found": validation_metadata.get("patterns_found", []),
                    "severity": validation_metadata.get("severity", "unknown"),
                },
            )
            # Fall back to a safe generic response
            final_response = (
                "Съжалявам, не мога да генерирам подходящ отговор в момента. "
                "Моля, консултирайте се с фармацевт или лекар."
            )
        elif validation_metadata.get("cleaned", False):
            # Response was cleaned - use the cleaned version
            logger.info(
                "Response cleaned successfully",
                extra={
                    "patterns_removed": validation_metadata.get("patterns_found", []),
                    "patterns_remaining": validation_metadata.get("patterns_remaining", []),
                },
            )
            final_response = cleaned_response

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Unified processor pipeline completed",
            extra={
                "duration_ms": round(duration_ms, 2),
                "llm_time_ms": round(llm_result.processing_time_ms, 2),
                "candidates": len(candidate_products),
                "selected": len(selected_products),
                "conditions": llm_result.extraction.user_conditions,
                "response_validated": is_valid,
                "response_cleaned": validation_metadata.get("cleaned", False),
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

    def _build_medical_reasoning_from_unified(self, llm_result: UnifiedProcessorResult) -> MedicalReasoning:
        """Convert UnifiedProcessorResult to MedicalReasoning for compatibility."""
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

        medical_reasoning = self._build_medical_reasoning_from_unified(llm_result)

        # ── SECTION 1: Symptom info header ──────────────────────────────
        symptom_label = self._build_symptom_header(llm_result.extraction.symptoms, original_query)
        parts.append(f"## 🔍 Информация при симптом: {symptom_label}\n")

        # Explanation (prefer _bg, filter garbage sentences, clean English leaks)
        expl_text = None
        if reasoning.explanation_bg and self._calculate_bulgarian_ratio(reasoning.explanation_bg) >= 0.65:
            expl_text = reasoning.explanation_bg
        elif reasoning.explanation:
            # If generating Bulgarian directly, explanation is already in Bulgarian
            if self._generate_bulgarian_directly:
                expl_text = reasoning.explanation
            else:
                translated = self.translator.translate_to_bulgarian(reasoning.explanation)
                if translated and self._calculate_bulgarian_ratio(translated) > 0.3:
                    expl_text = translated
        if expl_text:
            filtered = self._filter_garbage_sentences(expl_text)
            if filtered:
                parts.append(self._clean_english_leaks(filtered))

        parts.append("")

        # ── SECTION 2: Active ingredients ───────────────────────────────
        # ALWAYS show this section when products are present (Issue #18)
        parts.append("---")
        treatment_type = reasoning.treatment_category or ""
        recommended_ingredients = self._get_recommended_ingredients(treatment_type)
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
                action_text = self._get_treatment_action_text(treatment_type)
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
            if t and self._calculate_bulgarian_ratio(t) >= 0.65 and self._is_valid_self_care_tip(t)
        ]
        if not tips_bg and reasoning.self_care_tips:
            for tip in reasoning.self_care_tips[:3]:
                # If generating Bulgarian directly, tips are already in Bulgarian
                if self._generate_bulgarian_directly:
                    if self._is_valid_self_care_tip(tip):
                        tips_bg.append(tip)
                else:
                    translated = self.translator.translate_to_bulgarian(tip)
                    if translated and self._calculate_bulgarian_ratio(translated) > 0.3:
                        if self._is_valid_self_care_tip(translated):
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
            displayed_products = self._filter_by_severity(products, symptom_count)
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
        warnings_bg = [w for w in warnings_bg[:3] if w and self._calculate_bulgarian_ratio(w) >= 0.65]
        if not warnings_bg and reasoning.warnings:
            for warning in reasoning.warnings[:3]:
                # If generating Bulgarian directly, warnings are already in Bulgarian
                if self._generate_bulgarian_directly:
                    warnings_bg.append(warning)
                else:
                    translated = self.translator.translate_to_bulgarian(warning)
                    if translated and self._calculate_bulgarian_ratio(translated) > 0.3:
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

    # Phrases indicating the model refused to help (English and Bulgarian)
    _REFUSAL_PHRASES = {
        # English
        "i cannot",
        "i can't",
        "i'm not able to",
        "i am not able to",
        "i will not",
        "i won't",
        "cannot fulfill",
        "can't fulfill",
        "cannot help with",
        "can't help with",
        "not appropriate",
        "inappropriate request",
        "decline to",
        "refuse to",
        "against my guidelines",
        "violates my guidelines",
        "not a medical",
        "isn't a medical",
        "is not a medical",
        # Bulgarian
        "не мога",
        "не съм в състояние",
        "не е възможно",
        "не е подходящо",
        "неподходящ",
        "отказвам",
        "не е медицински",
        "това не е",
    }

    def _is_refusal_response(self, reasoning: MedicalReasoning) -> bool:
        """
        Check if MedGemma's response indicates it cannot or will not help.

        This catches cases where inappropriate queries slip through the intent
        classifier but MedGemma refuses to respond.
        """
        if not reasoning or not reasoning.likely_cause:
            return False

        response_lower = reasoning.likely_cause.lower()
        return any(phrase in response_lower for phrase in self._REFUSAL_PHRASES)

    def _translate_to_bulgarian(self, text: str) -> str:
        """Translate English to Bulgarian."""
        return self.translator.translate_to_bulgarian(text)

    def _get_medical_reasoning(self, text: str) -> MedicalReasoning:
        """
        Use MedGemma to understand symptoms and suggest treatment categories.

        Includes fallback strategy for graceful degradation if model fails.
        """
        try:
            return self.medical_model.get_medical_reasoning(text)
        except Exception as e:
            logger.error(f"MedGemma inference failed: {e}", exc_info=True)
            return self._create_fallback_reasoning(text)

    def _create_fallback_reasoning(self, text: str) -> MedicalReasoning:
        """
        Create a safe fallback MedicalReasoning when MedGemma fails.

        Returns a conservative response that recommends consulting a pharmacist.
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

    def _check_safety(
        self, original_query: str, translated_query: str, medical_reasoning: MedicalReasoning
    ) -> tuple[bool, str]:
        """
        Check for red-flag symptoms requiring professional medical attention.

        Checks both original Bulgarian and translated English text for safety patterns,
        plus MedGemma's see_doctor recommendation.

        Returns (is_red_flag, message):
        - True means STOP and return safety message (no products)
        - False means CONTINUE with product search (may still add warnings later)
        """
        # Check original Bulgarian text for actual emergencies
        result = self.safety_layer.check_safety(original_query)
        if result.is_red_flag:
            return True, result.message

        # Check translated English text for actual emergencies
        result_en = self.safety_layer.check_safety(translated_query)
        if result_en.is_red_flag:
            return True, result_en.message

        # For MedGemma's see_doctor recommendation, handle differently based on query type
        if medical_reasoning.see_doctor:
            # For child-related queries, DON'T block - continue to find products
            # but add pediatric warnings (handled by _add_child_disclaimer later)
            if self._is_child_related_query(original_query):
                logger.info("Child query with see_doctor=True - proceeding with pediatric warnings")
                return False, ""  # Continue to product search

            # For pregnancy-related queries, DON'T block - continue with warnings
            if self._is_pregnancy_related_query(original_query):
                logger.info("Pregnancy query with see_doctor=True - proceeding with warnings")
                return False, ""  # Continue to product search

            # For drug combination/interaction queries, DON'T block - these are valid OTC questions
            # (e.g., "Can I take ibuprofen with paracetamol?")
            if self._is_drug_combination_query(original_query):
                logger.info("Drug combination query with see_doctor=True - proceeding with info")
                return False, ""  # Continue to provide helpful information

            # For substitute/alternative queries, DON'T block - search for OTC alternatives
            # (e.g., "Generic substitute for Aulin", "Алтернатива на нимезулид")
            if self._is_substitute_query(original_query):
                logger.info("Substitute query with see_doctor=True - proceeding to find OTC alternatives")
                return False, ""  # Continue to find OTC alternatives

            # For other queries, use the generic doctor recommendation
            return True, (
                "⚠️ **Препоръчваме консултация с лекар.**\n\n"
                "Базирано на вашите симптоми, препоръчваме да се консултирате "
                "с медицински специалист за правилна диагноза и лечение."
            )

        return False, ""

    def _is_pregnancy_related_query(self, text: str) -> bool:
        """Check if query mentions pregnancy or breastfeeding."""
        text_lower = text.lower()
        pregnancy_patterns = USER_CONDITION_PATTERNS.get("pregnancy", [])
        breastfeeding_patterns = USER_CONDITION_PATTERNS.get("breastfeeding", [])
        all_patterns = pregnancy_patterns + breastfeeding_patterns
        return any(kw in text_lower for kw in all_patterns if not kw.startswith(r"\b"))

    def _is_drug_combination_query(self, text: str) -> bool:
        """Check if query is about combining/taking multiple medications together.

        These are valid OTC questions like "Can I take ibuprofen with paracetamol?"
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
            "take with",
            "can i take",
            "can i use",
            "along with",
            "in combination",
        }

        # Check for combination keywords
        has_combination_keyword = any(kw in text_lower for kw in combination_keywords)

        # Also check for pattern: two drug names mentioned
        common_otc_drugs = {
            "ибупрофен",
            "ibuprofen",
            "парацетамол",
            "paracetamol",
            "acetaminophen",
            "аспирин",
            "aspirin",
            "нурофен",
            "nurofen",
            "панадол",
            "panadol",
            "адвил",
            "advil",
            "тайленол",
            "tylenol",
            "аналгин",
            "analgin",
            "темпалгин",
            "темпра",
            "ефералган",
            "efferalgan",
        }
        drugs_mentioned = sum(1 for drug in common_otc_drugs if drug in text_lower)

        return has_combination_keyword or drugs_mentioned >= 2

    def _is_substitute_query(self, text: str) -> bool:
        """Check if query is asking for a substitute/alternative/generic for a drug.

        These are valid questions like "Generic substitute for Aulin" or
        "Алтернатива на нимезулид" - user wants OTC options instead of prescription drug.
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

    def _retrieve_product_candidates(
        self, medical_reasoning: MedicalReasoning, original_query: str = "", top_k: int = 10
    ) -> list:
        """
        Stage 1: Fast vector similarity search to get top-K product candidates.

        Uses ChromaDB with multilingual embeddings based on MedGemma's analysis.
        Now uses hybrid search (semantic + keyword) with category awareness.

        Also validates treatment_type against original query keywords to catch
        MedGemma misclassifications (e.g., GI symptoms classified as cold/flu).
        """
        if self.product_store.collection.count() == 0:
            logger.warning("Product store is empty. Run product_store.py --reload to load products.")
            return []

        search_query = self._build_search_query(medical_reasoning, original_query)

        # Validate/correct treatment_type using original query keywords
        treatment_type = medical_reasoning.treatment_type
        if original_query:
            query_treatment = self._extract_treatment_from_query(original_query)
            if query_treatment:
                # Override if MedGemma's treatment doesn't match query symptoms
                # This catches cases like GI symptoms being classified as cold/flu
                if treatment_type:
                    # Check if there's a category mismatch
                    gi_types = {"antidiarrheal", "digestive", "antacids", "laxatives"}
                    cold_types = {"cough", "decongestants", "antipyretics"}

                    # If query has GI symptoms but MedGemma returned cold/flu, override
                    if query_treatment in gi_types and treatment_type.lower() in cold_types:
                        logger.info(
                            f"Overriding treatment_type from '{treatment_type}' to '{query_treatment}' based on query keywords"
                        )
                        treatment_type = query_treatment
                    # Also override if no treatment type from MedGemma
                else:
                    treatment_type = query_treatment
                    logger.debug(f"Using query-extracted treatment_type: {treatment_type}")

        # Use category-aware hybrid search for better results
        if treatment_type:
            results = self.product_store.search_by_category(
                query=search_query,
                treatment_type=treatment_type,
                n_results=top_k,
            )
        else:
            # Fallback to hybrid search without category
            results = self.product_store.hybrid_search(search_query, n_results=top_k)

        return self._convert_to_products(results)

    def _build_search_query(self, medical_reasoning: MedicalReasoning, original_query: str = "") -> str:
        """Build search query from medical reasoning components.

        For drug combination queries, extracts drug names from original query
        since MedGemma returns generic terms like 'drug interaction query'.
        """
        parts = []

        # Add treatment type (e.g., "analgesics")
        if medical_reasoning.treatment_type:
            parts.append(medical_reasoning.treatment_type)

        # Filter out non-useful symptoms for product search
        non_useful_symptoms = {
            "drug interaction query",
            "drug interaction",
            "safety concern",
            "medication question",
            "dosage question",
            "combination query",
        }
        if medical_reasoning.symptoms:
            useful_symptoms = [s for s in medical_reasoning.symptoms if s.lower() not in non_useful_symptoms]
            parts.extend(useful_symptoms)

        # For drug combo queries, extract actual drug names from original query
        if original_query and self._is_drug_combination_query(original_query):
            drug_names = self._extract_drug_names(original_query)
            if drug_names:
                parts.extend(drug_names)

        # Add likely cause only if it's useful
        if medical_reasoning.likely_cause:
            cause_lower = medical_reasoning.likely_cause.lower()
            if cause_lower not in {"safety concern", "unknown", "not specified"}:
                parts.append(medical_reasoning.likely_cause)

        # For child/baby queries, add age context to retrieval
        if original_query:
            ql = original_query.lower()
            if any(kw in ql for kw in ["бебе", "бебет"]):
                parts.append("бебе бейби за деца")
            elif any(kw in ql for kw in ["дете", "детето", "деца"]):
                parts.append("деца за деца")

        return " ".join(parts) if parts else "medicine"

    # Common OTC drug names for extraction
    _DRUG_NAME_PATTERNS = {
        # Bulgarian names
        "ибупрофен",
        "парацетамол",
        "аспирин",
        "аналгин",
        "нурофен",
        "панадол",
        "темпалгин",
        "темпра",
        "ефералган",
        "адвил",
        "цитрамон",
        "пенталгин",
        "солпадеин",
        # English names
        "ibuprofen",
        "paracetamol",
        "acetaminophen",
        "aspirin",
        "nurofen",
        "panadol",
        "advil",
        "tylenol",
        "analgin",
    }

    # Bulgarian symptom keywords → treatment type mapping
    # Used to validate/correct MedGemma's treatment_type
    _BG_SYMPTOM_TO_TREATMENT = {
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

    def _extract_treatment_from_query(self, query: str) -> str | None:
        """
        Extract treatment type from original Bulgarian query keywords.

        Used to validate/correct MedGemma's treatment_type when there's
        a mismatch between detected symptoms and recommended treatment.
        """
        query_lower = query.lower()

        # Count symptom matches by treatment type
        treatment_scores = {}
        for keyword, treatment in self._BG_SYMPTOM_TO_TREATMENT.items():
            if keyword in query_lower:
                treatment_scores[treatment] = treatment_scores.get(treatment, 0) + 1

        if not treatment_scores:
            return None

        # Return treatment with highest score (most keyword matches)
        return max(treatment_scores, key=treatment_scores.get)

    def _query_has_symptom_keywords(self, query: str) -> bool:
        """
        Check if the original query contains any recognizable symptom keywords.

        Used to validate whether MedGemma's detected symptoms are phantom or real.
        """
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in self._BG_SYMPTOM_TO_TREATMENT.keys())

    def _validate_symptoms_against_query(self, symptoms: list[str], original_query: str) -> list[str]:
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
        if not self._query_has_symptom_keywords(query_lower):
            # Only keep symptoms if they match known Bulgarian symptom words
            # This catches cases where the query IS about symptoms but uses different words
            valid_symptoms = []
            for symptom in symptoms:
                symptom_lower = symptom.lower()
                # Check if any keyword from our mapping appears in either the query or symptom
                for keyword in self._BG_SYMPTOM_TO_TREATMENT.keys():
                    if keyword in symptom_lower and keyword in query_lower:
                        valid_symptoms.append(symptom)
                        break
            return valid_symptoms

        # Query has symptom keywords, so keep all detected symptoms
        return symptoms

    def _extract_drug_names(self, text: str) -> list[str]:
        """Extract known drug names from text for product search."""
        text_lower = text.lower()
        found = []
        for drug in self._DRUG_NAME_PATTERNS:
            if drug in text_lower:
                found.append(drug)
        return found

    def _convert_to_products(self, results: list) -> list:
        """Convert ChromaDB results to Product objects."""
        products = []
        for result in results:
            try:
                products.append(Product.from_chromadb(result))
            except Exception as e:
                logger.warning("Failed to parse product", extra={"error": str(e)})
        return products

    def _refine_product_selection(
        self, user_query: str, medical_reasoning: MedicalReasoning, candidates: list, max_products: int = 3
    ) -> list:
        """Stage 2: Use LLM to pick the best products from candidates.

        Applies pharmacological reranking BEFORE sending to LLM, so the
        LLM sees ingredient-matched products at the top of the list.
        """
        if not candidates:
            return []

        # Pre-sort candidates: ingredient-matched first, homeopathy last
        candidates = self._pharmacological_rerank(candidates, medical_reasoning)

        # Build comprehensive reasoning string with user conditions
        reasoning_parts = [
            f"Symptoms: {', '.join(medical_reasoning.symptoms)}",
            f"Likely cause: {medical_reasoning.likely_cause}",
            f"Treatment type: {medical_reasoning.treatment_type}",
        ]

        # Add user conditions if present
        if medical_reasoning.user_conditions:
            conditions_str = ", ".join(medical_reasoning.user_conditions)
            reasoning_parts.append(f"User conditions: {conditions_str}")
            reasoning_parts.append(
                "IMPORTANT: Products must be safe for the user's conditions. "
                "Avoid recommending anything that could be contraindicated."
            )

        reasoning_str = ". ".join(reasoning_parts) + "."

        selected = self.medical_model.refine_product_selection(
            user_query=user_query,
            medical_reasoning=reasoning_str,
            candidate_products=candidates,
            max_products=max_products + 2,  # Get extra for deduplication
        )

        # Deduplicate by active ingredient to ensure variety
        deduplicated = self._deduplicate_by_ingredient(selected, max_products)

        return deduplicated

    def _pharmacological_rerank(self, candidates: list, medical_reasoning: MedicalReasoning) -> list:
        """Rerank candidates so clinically relevant products appear first.

        Priority (5 tiers):
        1a. Simple products with a recommended active ingredient (e.g., pure paracetamol)
        1b. Combo products with a recommended active ingredient (e.g., cold/flu + paracetamol)
        2. Other non-homeopathic products
        3. Homeopathic products (last)

        This ensures the LLM sees the best candidates at the top of the list
        (LLMs have positional bias toward earlier items).
        """
        from src.product_store import _is_homeopathic_product

        treatment_type = (medical_reasoning.treatment_type or "").lower().strip()
        recommended = self._get_recommended_ingredients(treatment_type) if treatment_type else []

        tier1_simple = []  # Recommended ingredient, single-ingredient product
        tier1_combo = []  # Recommended ingredient, combination product
        tier2 = []  # Non-homeopathic, no matching ingredient
        tier3 = []  # Homeopathic

        for product in candidates:
            comp = (getattr(product, "composition", "") or "").lower()
            title = (getattr(product, "title", "") or "").lower()
            desc = (getattr(product, "description", "") or "").lower()
            combined = f"{comp} {title} {desc}"

            if _is_homeopathic_product(combined):
                tier3.append(product)
                continue

            ingredient = extract_product_ingredient(product)
            if ingredient and ingredient in recommended:
                if is_combination_product(product):
                    tier1_combo.append(product)
                else:
                    tier1_simple.append(product)
            else:
                tier2.append(product)

        reranked = tier1_simple + tier1_combo + tier2 + tier3
        if tier1_simple or tier1_combo:
            logger.info(
                f"Pharmacological rerank: {len(tier1_simple)} simple, "
                f"{len(tier1_combo)} combo, {len(tier2)} other, {len(tier3)} homeopathic"
            )
        return reranked

    def _deduplicate_by_ingredient(self, products: list, max_products: int, max_per_ingredient: int = 1) -> list:
        """
        Deduplicate products by active ingredient to ensure recommendation variety.

        Prevents recommending 3 versions of the same drug (e.g., 3 ibuprofen brands).

        Args:
            products: List of Product objects
            max_products: Maximum products to return
            max_per_ingredient: Maximum products per active ingredient

        Returns:
            Deduplicated list of products
        """
        if not products:
            return []

        seen_ingredients: dict[str, int] = {}
        result = []
        selected_keys: set[str] = set()

        def product_key(product: Product) -> str:
            """Stable key for de-dup across fill pass."""
            sku = (getattr(product, "sku", None) or "").strip()
            if sku:
                return f"sku:{sku}"
            pid = getattr(product, "id", None)
            if pid:
                return f"id:{pid}"
            title = (getattr(product, "title", "") or "").strip().lower()
            return f"title:{title}"

        for product in products:
            # Use fallback_to_title=True for deduplication grouping
            ingredient = extract_product_ingredient(product, fallback_to_title=True)
            count = seen_ingredients.get(ingredient, 0)

            if count < max_per_ingredient:
                result.append(product)
                seen_ingredients[ingredient] = count + 1
                selected_keys.add(product_key(product))
                logger.debug(f"Selected '{product.title}' (ingredient: {ingredient})")

                if len(result) >= max_products:
                    break
            else:
                logger.debug(f"Skipped '{product.title}' (duplicate ingredient: {ingredient})")

        # Fill pass: never return too few products just because ingredient diversity is low.
        # Example: fever query may have many relevant paracetamol SKUs; we still want >=3 shown.
        if len(result) < max_products:
            for product in products:
                if len(result) >= max_products:
                    break
                key = product_key(product)
                if key in selected_keys:
                    continue
                result.append(product)
                selected_keys.add(key)
                logger.debug(
                    f"Fill-pass selected '{product.title}' to reach minimum count ({len(result)}/{max_products})"
                )

        return result

    def _is_child_related_query(self, text: str) -> bool:
        """Check if query mentions children, babies, or age-related terms."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in CHILD_KEYWORDS)

    def _is_safety_information_query(self, text: str) -> bool:
        """Check if query asks about medication safety."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in SAFETY_KEYWORDS)

    def _add_child_disclaimer(self, response: str) -> str:
        """Child safety is now handled inside the main template (triage section
        + safety block + product card warnings). No extra block appended."""
        return response

    def _add_safety_info_disclaimer(self, response: str) -> str:
        """Safety info is now in the main template (safety block + footer).
        No extra block appended."""
        return response

    def _is_chronic_disease_query(self, text: str) -> bool:
        """Check if query is about chronic disease medications."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in CHRONIC_DISEASE_KEYWORDS)

    def _add_chronic_disease_disclaimer(self, response: str) -> str:
        """Add prescription warning for chronic disease queries."""
        # Don't add if response already refers to doctor
        if "консултация с лекар" in response.lower() or "112" in response:
            return response

        disclaimer = """
📋 **Важно за хронични заболявания:**
- Лекарствата за хронични заболявания обикновено се отпускат **по лекарска рецепта**
- Не променяйте дозировката без консултация с вашия лекар
- Мога да ви помогна с допълнителни продукти: тест ленти, глюкомери, хранителни добавки
- За предписани лекарства, моля консултирайте се с вашия лекар или фармацевт"""
        return response + "\n" + disclaimer

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

    # =========================================================================
    # GARBAGE PATTERNS - Filter low-quality text from responses
    # =========================================================================
    # These patterns detect text that shouldn't appear in user-facing responses:
    # - Drug leaflet boilerplate (side effects, contraindications)
    # - EU regulation fragments
    # - Translation artifacts and garbled text
    # - Medical jargon inappropriate for consumers
    # - Product catalog noise

    _GARBAGE_PATTERNS = {
        # -----------------------------------------------------------------
        # DRUG LEAFLET / PACKAGE INSERT TEXT
        # -----------------------------------------------------------------
        # Side effects sections
        "нежелани реакции",
        "странични ефекти",
        "неизвестна честота",
        "с неизвестна честота",
        "нежелана реакция",
        "възможни нежелани",
        "side effects",
        "unknown frequency",
        "adverse reactions",
        "много чести",
        "чести нежелани",
        "нечести нежелани",
        "редки нежелани",
        # Anatomical system categories
        "мускулно- скелетната",
        "съединителната тъкан",
        "нарушения на кожата",
        "подкожната тъкан",
        "инфекции и ефекти",
        "мястото на приложение",
        "стомашно-чревни нарушения",
        "чернодробни нарушения",
        "сърдечни нарушения",
        "дихателни нарушения",
        "нарушения на нервната",
        "психични нарушения",
        "репродуктивни нарушения",
        "ендокринни нарушения",
        # Contraindications boilerplate
        "свръхчувствителност към активното",
        "свръхчувствителност към някоя от помощните",
        "противопоказания: свръхчувствителност",
        "да не се прилага при пациенти с",
        # Dosage/storage instructions
        "препоръчителна доза е",
        "максимална дневна доза",
        "да се съхранява на място",
        "срок на годност",
        "след изтичане на срока",
        "да се пази от деца",
        # Pharmaceutical body parts (leaflet language)
        "семенна течност",
        "сперматогенеза",
        "ерекция",
        # -----------------------------------------------------------------
        # EU REGULATIONS / LEGAL TEXT
        # -----------------------------------------------------------------
        "емисиите на парникови",
        "парникови газове",
        "регламент",
        "европейския парламент",
        "европейски парламент",
        "съвета",
        "в съответствие с изискванията",
        "директива на ес",
        "в съответствие с регламент",
        "официален вестник",
        "европейска комисия",
        "държави членки",
        "специални условия на труд",
        "стоманодобивната промишленост",
        "техниките средства за подпомагане",
        # EU Official Journal citations (ОВ = Официален вестник)
        "ов l",
        "ов c",
        "(ов l",
        "(ов c",
        "ов l 268",
        "ов l 269",
        "18.10.2003",
        "стр.",
        "стр)",
        "(стр.",
        "официален вестник на ес",
        "официален вестник на европейския съюз",
        "директива 2001/83/",
        "регламент (ео)",
        "регламент (ес)",
        # -----------------------------------------------------------------
        # REPEATED / INCOHERENT PHRASES
        # -----------------------------------------------------------------
        "болка в гърба, болка в гърба",
        "болка в корема, болка в корема",
        "главоболие, главоболие",
        "температура, температура",
        "не се препоръчва употребата",
        "да се каже, че",
        "консултирайте с вашия лекар или фармацевт",
        "този препарат",
        "лекарствен продукт",
        "човешки рекомбинантен човешки рекомбинантен",
        "рекомбинантен еритропоетин",
        "препоръчителни че",
        # -----------------------------------------------------------------
        # TRUNCATED / GARBLED TEXT
        # -----------------------------------------------------------------
        "(сърх)",
        "(Сърх)",
        "( сърх",
        "сърх)",
        "тол- сол",
        "сол- сол",
        "- сол-",
        "тол-сол",
        "( -",
        "- )",
        "( )",
        "(-)",
        "- -",
        "-- --",
        "---",
        "мои_____",
        "ст ст ст",
        "(д възможно най-",
        "таблетка на",
        "нетно вещество",
        "от с",
        "обучение",
        # -----------------------------------------------------------------
        # FRAGMENTS / NONSENSE / FILLER
        # -----------------------------------------------------------------
        "допринася за по-малко",
        "усили въздуха",
        "трябва да се вземат мерки",
        "както и да е, трябва",
        "както и да е",
        "в зависимост от състоянието",
        "да се избягва свързването",
        "по- малко от 6 месеца",
        "(по- малко от",
        "през последните три години",
        "cuts обикновено",
        # -----------------------------------------------------------------
        # IRRELEVANT CATEGORIES
        # -----------------------------------------------------------------
        "сметки и апарати",
        "зъбні протези",
        "грижа за зъбні протези",
        "трикотажни",
        "тарифен номер",
        "тарифна позиция",
        "митническа позиция",
        "стокова позиция",
        "лични данни",
        "защита на личните",
        "средство за защита",
        "репелент",
        "комар",
        "комари",
        "средство за комари",
        "защита срещу комари",
        "ще се справим ли",
        "уха си ти",
        # LLM hallucination patterns (Feb 2026 - Issue #17)
        "може да се използва като средство за",
        "за да може да се използва",
        "които могат да бъдат използвани като",
        # -----------------------------------------------------------------
        # MEDICAL JARGON (too technical for consumers)
        # -----------------------------------------------------------------
        "забрана за употреба при пациенти",
        "лекувани с човешки",
        "клинични изпитвания",
        "рандомизирано проучване",
        "двойно-сляпо",
        "плацебо-контролирано",
        "фармакокинетика",
        "фармакодинамика",
        "бионаличност",
        "полуживот на елиминиране",
        "плазмена концентрация",
        "пиково ниво",
        "лекарствени взаимодействия с",
        "индуктор на cyp",
        "инхибитор на cyp",
        "p-гликопротеин",
        # -----------------------------------------------------------------
        # PHARMACEUTICAL CODES / TECHNICAL
        # -----------------------------------------------------------------
        "mg/ml",
        "мг/мл",
        "таблетки x",
        "atc код",
        "atc-код",
        "анатомо-терапевтична",
        "inn:",
        "международно непатентно",
        "партиден номер",
        "сериен номер",
        # -----------------------------------------------------------------
        # TRANSLATION ARTIFACTS
        # -----------------------------------------------------------------
        "в в ",
        "на на ",
        "за за ",
        "от от ",
        "с с ",  # Doubled prepositions
        "the the",
        "a a ",
        "an an ",
        "is is ",  # English doubles
        " ,",
        " .",
        " ;",
        " :",  # Space before punctuation
        # -----------------------------------------------------------------
        # PRODUCT CATALOG / E-COMMERCE NOISE
        # -----------------------------------------------------------------
        "добави в количка",
        "добави в любими",
        "виж повече",
        "виж всички",
        "покажи повече",
        "изчерпано количество",
        "очаквайте скоро",
        "безплатна доставка",
        "бърза доставка",
        "цена с ддс",
        "цена без ддс",
        "% отстъпка",
        "артикулен номер",
        "баркод:",
        # -----------------------------------------------------------------
        # INSURANCE / ADMINISTRATIVE (Bulgarian healthcare system)
        # -----------------------------------------------------------------
        "нзок",
        "здравна каса",
        "реимбурсиране",
        "протокол за лечение",
        "позитивен списък",
        # -----------------------------------------------------------------
        # TRANSLATION HALLUCINATIONS / WRONG CONTEXT
        # -----------------------------------------------------------------
        # Completely wrong medical terms for context
        "introna",
        "интрон",
        "интерферон",
        "хепатит",
        "hepatitis",  # Unless actually asking about hepatitis
        "отстраняване на газовете",
        "отстраняване на газове",
        "цацове и слитове",
        "слитове за маса",
        "най-често се налага лечение с",
        "с intron",
        "с интрон",
        # Industrial/technical garbage
        "индустриален",
        "промишлен",
        "производство на",
        "преработка на",
        # Nonsense phrases from bad translation
        "възможно най- малко време",
        "да се използва доза",
        "се прилага в рамките на 1 час",
        "терапията с вирусите",
        "майчино- съдово лечение",
        "химикали и подобни форми",
        "предразположени към",
        "спадове в температурата",
        "прави бебето удобно",
        "определената за тази цел възраст",
        "труд на човека",
        "условия на труд",
        "4. 7",  # EU regulation numbering
        "4.7 специални",
        # More truncated/garbled patterns
        "_____",
        "____",
        "___",
        " ст ",
        " ст,",
        ",ст,",
        "ст ст",
        "мои___",
        "мои____",  # English fragments that shouldn't appear in BG output
        "keep baby",
        "offer fluids",
        "lightly dressed",
        "keep бебе",
        "keep дете",  # Mixed English/BG
        "immediate care if fever",
        "immediate care if",
        "if fever exceeds",
        "if temperature exceeds",
        " if ",
        " exceeds ",  # English conjunctions in BG text
        "lukewarm",
        "sponge bath",
        "seek medical",
        "medical attention",
        # Common English words that indicate bad translation
        "keep ",
        "should ",
        "usually ",
        "avoid ",
        "monitor ",
        "ensure ",
        "apply ",
        " and ",
        "worsen after",
        "symptoms worsen",
        "see doctor",
        "consult doctor",
        # Malformed text patterns
        "това е в.",
        "това е в,",
        "в. or",
        ", or ",
        "крайни нарушения",
        "нарушения на вкуса",
        "ставите инфекции",
        "инфекции, които",
        '" вижте',
        '["',
        '"]',
        # Numbers with spaces in wrong places
        "38 . 5",
        "38. 5",
    }

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
                if self._contains_garbage(original):
                    return None
                return self._clean_english_leaks(original)

            if not translate_reasoning:
                return self._clean_english_leaks(original)
            translated = translated_texts.get(key, original)
            if self._contains_garbage(translated):
                return None
            # Reject text with too much English (< 60% Bulgarian chars)
            if self._calculate_bulgarian_ratio(translated) < 0.60:
                fresh = self.translator.translate_to_bulgarian(original)
                if fresh and self._calculate_bulgarian_ratio(fresh) >= 0.60:
                    return self._clean_english_leaks(fresh)
                return None
            return self._clean_english_leaks(translated)

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
        recommended_ingredients = self._get_recommended_ingredients(treatment_type)
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
                action_text = self._get_treatment_action_text(treatment_type)
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
                    if len(translated_tip) >= 5 and self._is_valid_self_care_tip(translated_tip):
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
            displayed_products = self._filter_by_severity(products, symptom_count)
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
                if translated and not self._contains_garbage(translated):
                    return translated.capitalize()

        return "вашите симптоми"

    def _get_recommended_ingredients(self, treatment_type: str) -> list[str]:
        """Get recommended active ingredients for a treatment type."""
        return get_recommended_ingredients(treatment_type)

    # Brief action descriptions per treatment type (what the ingredients DO)
    _TREATMENT_ACTION_TEXTS = {
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

    def _get_treatment_action_text(self, treatment_type: str) -> str:
        """Get a brief explanation of what the recommended ingredients do."""
        if not treatment_type:
            return ""
        tt = treatment_type.lower().strip()
        if tt in self._TREATMENT_ACTION_TEXTS:
            return self._TREATMENT_ACTION_TEXTS[tt]
        for key, text in self._TREATMENT_ACTION_TEXTS.items():
            if key in tt or tt in key:
                return text
        return ""

    # Keywords indicating a product is for adults only
    _ADULT_ONLY_MARKERS = {"за възрастни", "for adults", "над 15 години", "над 16 години", "над 18 години"}
    # Keywords indicating a product is child/baby-appropriate
    _CHILD_MARKERS = {"за деца", "бебе", "бейби", "baby", "junior", "джуниър", "юноши", "kids", "педиатрич"}
    # Forms suitable for babies/toddlers
    _BABY_FORMS = {"суспензия", "сироп", "капки", "супозитори", "разтвор"}

    def _filter_by_age_appropriateness(self, products: list, original_query: str) -> list:
        """Filter and reorder products based on patient age from query.

        For child/baby queries:
        - Exclude products explicitly marked 'for adults'
        - Boost products marked for children/babies
        - Boost liquid forms (suspension, syrup, suppositories)
        """
        query_lower = (original_query or "").lower()

        # Detect if query is about a child/baby
        is_child_query = any(kw in query_lower for kw in ["бебе", "дете", "детето", "месец", "бебет"])
        any(kw in query_lower for kw in ["бебе", "бебет", "месец"])

        if not is_child_query:
            return products  # No filtering needed

        child_appropriate = []
        child_neutral = []

        for p in products:
            title = (getattr(p, "title", "") or "").lower()
            desc = (getattr(p, "description", "") or "").lower()
            combined = f"{title} {desc}"

            # Exclude adult-only products
            if any(marker in combined for marker in self._ADULT_ONLY_MARKERS):
                logger.info(f"Excluding adult-only product for child query: {title[:50]}")
                continue

            # Check if product is child-appropriate
            has_child_marker = any(marker in combined for marker in self._CHILD_MARKERS)
            has_baby_form = any(form in combined for form in self._BABY_FORMS)

            if has_child_marker or has_baby_form:
                child_appropriate.append(p)
            else:
                child_neutral.append(p)

        # For baby queries, strongly prefer baby-specific products
        result = child_appropriate + child_neutral
        if not result:
            # If filtering removed everything, return originals (better than nothing)
            return products

        logger.info(
            f"Age filter: {len(child_appropriate)} child-specific, "
            f"{len(child_neutral)} neutral, {len(products) - len(result)} excluded"
        )
        return result

    def _filter_by_severity(self, products: list, symptom_count: int) -> list:
        """Filter products by symptom severity and clinical relevance.

        For single symptoms: simple (single-ingredient) products first, combos last.
        Always: homeopathic products after evidence-based ones.
        """
        from src.product_store import _is_homeopathic_product

        if not products:
            return []

        if symptom_count <= 1 and len(products) > 1:
            # Three-tier sort: simple evidence-based → combo → homeopathic
            evidence_simple = []
            evidence_combo = []
            homeopathic = []

            for p in products:
                comp = (getattr(p, "composition", "") or "").lower()
                title = (getattr(p, "title", "") or "").lower()
                desc = (getattr(p, "description", "") or "").lower()
                combined = f"{comp} {title} {desc}"

                if _is_homeopathic_product(combined):
                    homeopathic.append(p)
                elif is_combination_product(p):
                    evidence_combo.append(p)
                else:
                    evidence_simple.append(p)

            reordered = evidence_simple + evidence_combo + homeopathic
            return reordered[:3]

        return products[:3]

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

    def _contains_garbage(self, text: str) -> bool:
        """Check if text contains garbage patterns, low Bulgarian content, or excessive repetition."""
        import re

        if not text or len(text.strip()) < 3:
            return True

        text_lower = text.lower()

        # Check for garbage patterns
        if any(pattern in text_lower for pattern in self._GARBAGE_PATTERNS):
            return True

        # Check Bulgarian content ratio (target 95%+ per Issue 6, filter if below 65%)
        bg_ratio = self._calculate_bulgarian_ratio(text)
        if bg_ratio < 0.65:  # Less than 65% Bulgarian = garbage for BG output
            return True

        # Check for model output artifacts (word/word/word patterns, repeated substrings)
        artifact_patterns = [
            r"\w+/\s*\w+/\s*\w+",  # word/word/word patterns like "си гол/ си гол/ си гол"
            r"(.{2,10})\1{2,}",  # repeated substrings 2+ times
        ]
        for pattern in artifact_patterns:
            if re.search(pattern, text_lower):
                return True

        # Check for excessive word repetition
        words = text_lower.split()
        if len(words) >= 5:
            from collections import Counter

            word_counts = Counter(words)
            # If any word appears more than 50% of the time, it's garbage
            max_count = max(word_counts.values())
            if max_count > len(words) * 0.5:
                return True

        # Check for 2-word phrase repetition (catches patterns like "си гол си гол")
        if len(words) >= 4:
            for i in range(len(words) - 1):
                phrase = " ".join(words[i : i + 2])
                if len(phrase) > 3 and text_lower.count(phrase) >= 2:
                    return True

        # Check for 3-word phrase repetition
        if len(words) > 10:
            for i in range(len(words) - 5):
                phrase = " ".join(words[i : i + 3])
                if text_lower.count(phrase) >= 3:
                    return True

        return False

    def _filter_garbage_sentences(self, text: str) -> str:
        """Remove garbage sentences from explanation (P2b). Keeps only coherent parts."""
        if not text or len(text.strip()) < 5:
            return ""
        # Split by sentence-ending punctuation; also by comma for long run-ons (catches LLM garbage)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        kept = []
        for s in sentences:
            s = s.strip()
            if not s or len(s) < 10:
                continue
            # If a "sentence" is very long and contains comma, check each clause
            if len(s) > 120 and "," in s:
                clauses = [c.strip() for c in s.split(",") if len(c.strip()) >= 10]
                for c in clauses:
                    if not self._contains_garbage(c):
                        upper = sum(1 for ch in c if ch.isupper())
                        if len(c) > 0 and upper / len(c) <= 0.4:
                            kept.append(c)
                continue
            if self._contains_garbage(s):
                continue
            # Drop sentences that are mostly uppercase (EU jargon)
            upper = sum(1 for c in s if c.isupper())
            if len(s) > 0 and upper / len(s) > 0.4:
                continue
            kept.append(s)
        result = " ".join(kept) if kept else ""
        # Fallback: if critical garbage still present (e.g. cached/missed), truncate before that sentence
        critical = [
            "защита на личните",
            "лични данни",
            "средство за защита",
            "зъбні протези",
            "зъбни протези",
            "металокерамика",
        ]
        for phrase in critical:
            if phrase in result.lower():
                idx = result.lower().index(phrase)
                # Find last sentence end before the garbage
                before = result[:idx]
                last_end = max(before.rfind(". "), before.rfind("! "), before.rfind("? "))
                result = (result[: last_end + 1].rstrip() if last_end >= 0 else "") or ""
                break
        return result

    def _calculate_bulgarian_ratio(self, text: str) -> float:
        """Calculate the ratio of Bulgarian characters in text."""
        if not text:
            return 0.0
        bulgarian_chars = set("абвгдежзийклмнопрстуфхцчшщъьюя")
        text_lower = text.lower()
        bg_count = sum(1 for c in text_lower if c in bulgarian_chars)
        total_alpha = sum(1 for c in text_lower if c.isalpha())
        return bg_count / total_alpha if total_alpha > 0 else 0.0

    # Garbage patterns for self-care tips (LLM/translation artifacts)
    _TIP_GARBAGE = (
        "стъпления",
        "заявление за одобряване",
        "субекти които не са",
        "сребрист пръстен",
        "гимназиален",
        "направено е от лекар",
        "допълнение на външната",
        "допълнение на вътрешни",
        "корекция на дозата",
        "препарат за дългосрочна",
        "белезникав",
        "хранителна добавка за",
        "приложете повече от една доза веднъж на всеки две седмици",
        "сметки на бюджетите",
        "това е всичко което",
        # LLM hallucination patterns (Issue #17)
        "зъбні протези",
        "зъбни протези",
        "грижа за зъбні протези",
        "защита на личните",
        "средство за защита",
        "репелент",
        "комар",
        "комари",
        "пластмасов",
        "ламарин",
        "металокерамика",
        "отпадъчни препарати",
    )
    # Valid self-care keywords — tip should have at least one
    _VALID_TIP_KEYWORDS = (
        "течност",
        "вода",
        "почивка",
        "почивайте",
        "компрес",
        "храна",
        "сън",
        "витамин",
        "солен",
        "гаргар",
        "топл",
        "студен",
        "въздух",
        "влажност",
        "хидратаци",
        "масаж",
        "дишане",
        "избягвайте",
        "проверете",
        "облечете",
        "давайте",
        "пийте",
        "яжте",
        "отдих",
        "отпочин",
        "намалете",
        "приложете",
        "бебе",
        "дете",
        "грижа",
        "листовка",
        "доза",
        "възстановяване",
    )

    def _is_valid_self_care_tip(self, tip: str) -> bool:
        """Filter garbage self-care tips from LLM/translation output."""
        if not tip or len(tip.strip()) < 8:
            return False
        t = tip.lower().strip()
        # Reject known garbage
        if any(g in t for g in self._TIP_GARBAGE):
            return False
        # Reject >50% uppercase (garbled)
        upper = sum(1 for c in tip if c.isupper())
        if len(tip) > 0 and upper / len(tip) > 0.5:
            return False
        # Reject if no health-related keyword
        if not any(kw in t for kw in self._VALID_TIP_KEYWORDS):
            return False
        return True

    def _clean_english_leaks(self, text: str) -> str:
        """Remove English words leaked into otherwise-Bulgarian text.

        Strategy: identify sentences with English words and re-translate
        the entire sentence (not individual words, which produces garbage).
        Drop sentences that can't be translated.
        """
        import re

        if not text or self._calculate_bulgarian_ratio(text) >= 0.95:
            return text  # Already clean Bulgarian

        if self._calculate_bulgarian_ratio(text) < 0.50:
            return text  # Too much English — not a "leak" scenario

        # Split into sentences and clean each
        sentences = re.split(r"(?<=[.!?])\s+", text)
        if len(sentences) <= 1:
            # Single sentence: check for English words
            latin_words = re.findall(r"\b[a-zA-Z]{3,}\b", text)
            # Known OK words (medical terms, units, brands that can stay in English)
            known_ok_lower = {
                # Standard medical terms / abbreviations
                "covid", "sars", "otc", "nsaid",
                "paracetamol", "ibuprofen", "aspirin", "diclofenac",
                # Units and dilutions
                "mg", "ml", "ph", "dh", "ch",
                # Major brands
                "nurofen", "brufen", "voltaren", "advil", "tylenol",
                "claritine", "zyrtec", "boiron", "tantum", "motilium",
            }
            # English words to clean (Issue #19: include capitalized medical terms)
            eng_words = [
                w for w in latin_words
                if w.lower() not in known_ok_lower
            ]
            if eng_words:
                # Re-translate the entire sentence
                fresh = self.translator.translate_to_bulgarian(text)
                if fresh and self._calculate_bulgarian_ratio(fresh) >= 0.85:
                    # Check for repetition garbage
                    if not self._has_repetition(fresh):
                        return fresh
                # If translation failed or produced garbage, just remove English words
                result = text
                for w in eng_words:
                    result = result.replace(w, "").replace("  ", " ")
                return result.strip()
            return text

        # Multiple sentences: clean each independently
        clean = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if self._calculate_bulgarian_ratio(sent) >= 0.90:
                clean.append(sent)
            else:
                # Try to re-translate
                fresh = self.translator.translate_to_bulgarian(sent)
                if fresh and self._calculate_bulgarian_ratio(fresh) >= 0.80 and not self._has_repetition(fresh):
                    clean.append(fresh)
                # Otherwise drop the sentence

        return " ".join(clean) if clean else text

    @staticmethod
    def _has_repetition(text: str, threshold: int = 3) -> bool:
        """Detect translation garbage — repeated words/phrases."""
        words = text.lower().split()
        if len(words) < 4:
            return False
        # Check for word repetition (same word appearing > threshold times)
        from collections import Counter

        counts = Counter(words)
        return any(c >= threshold for w, c in counts.items() if len(w) > 2)


# Global pipeline instance
_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    """Get or create the pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline
