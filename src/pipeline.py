"""
Pipeline orchestrator for the ViaPharma OTC Chatbot.
Each step can be swapped out for real implementations as we build them.

Pipeline follows the Perplexity two-stage retrieval pattern:
1. Vector DB returns top-K candidates (fast, cheap)
2. LLM refines and picks best matches (accurate)
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from src.medical_model import get_medical_model, MedicalReasoning
from src.translator import get_translator
from src.product_store import get_product_store
from src.intent_classifier import get_intent_classifier
from src.safety import get_safety_layer
from src.logging_config import get_logger
from src.config import get_settings

logger = get_logger("viapharma.pipeline")


@dataclass
class Product:
    """Represents a product from the catalogue."""
    id: str
    title: str  # Product name
    brand: str = ""  # Марка
    manufacturer: str = ""  # Производител
    category: str = ""
    tags: str = ""
    url_handle: str = ""  # URL slug for product link

    # Pricing
    price_bgn: float = 0.0  # Price in лв
    price_eur: float = 0.0  # Price in €

    # Product details
    description: str = ""  # Описание
    composition: str = ""  # Състав
    usage: str = ""  # Начин на употреба
    contraindications: str = ""  # Противопоказания

    # Additional info
    barcode: str = ""
    image_url: str = ""
    target_audience: str = ""  # За кого
    form: str = ""  # Форма
    is_otc: bool = True

    # Search relevance
    score: float = 0.0

    @property
    def product_url(self) -> str:
        """Get the full URL to the product page."""
        if self.url_handle:
            base_url = get_settings().product_base_url
            return f"{base_url}/{self.url_handle}"
        return ""

    @classmethod
    def from_chromadb(cls, data: dict) -> "Product":
        """Create a Product from ChromaDB search result."""
        return cls(
            id=str(data.get("id", data.get("sku", ""))),
            title=data.get("title", ""),
            brand=data.get("brand", ""),
            manufacturer=data.get("manufacturer", ""),
            category=data.get("category", ""),
            tags=data.get("tags", ""),
            url_handle=data.get("url_handle", ""),
            price_bgn=float(data.get("price_bgn", 0)),
            price_eur=float(data.get("price_eur", 0)),
            description=data.get("description", ""),
            composition=data.get("composition", ""),
            usage=data.get("usage", ""),
            contraindications=data.get("contraindications", ""),
            barcode=data.get("barcode", ""),
            image_url=data.get("image_url", ""),
            target_audience=data.get("target_audience", ""),
            form=data.get("form", ""),
            is_otc=data.get("is_otc", True),
            score=float(data.get("score", 0)),
        )

    def to_display_string(self) -> str:
        """Format product for display in chat with clean markdown."""
        lines = []

        # Title - make it a link if URL available
        if self.product_url:
            lines.append(f"**[{self.title}]({self.product_url})**")
        else:
            lines.append(f"**{self.title}**")

        # Price and brand on same line
        price_line = f"💰 {self.price_bgn:.2f} лв ({self.price_eur:.2f} €)"
        if self.brand:
            price_line += f"  •  🏷️ {self.brand}"
        lines.append(price_line)

        # Description - clean formatting, smart truncation
        if self.description:
            desc = self.description[:300].strip()
            if len(self.description) > 300:
                # Cut at last complete sentence or word
                last_period = desc.rfind('.')
                if last_period > 200:
                    desc = desc[:last_period + 1]
                else:
                    desc = desc.rsplit(' ', 1)[0] + "..."
            lines.append(f"\n{desc}")

        # Add to cart link
        if self.product_url:
            lines.append(f"\n🛒 [Виж продукта / Купи]({self.product_url})")

        return "\n".join(lines)


@dataclass
class PipelineResult:
    """Result from the pipeline processing."""
    response: str
    is_medical: bool = True
    is_red_flag: bool = False
    original_text: str = ""
    translated_text: str = ""
    medical_reasoning: Optional[MedicalReasoning] = None
    candidate_products: list = field(default_factory=list)  # Stage 1: top-K from vector DB
    selected_products: list = field(default_factory=list)   # Stage 2: LLM-refined selection


class Pipeline:
    """
    Main pipeline that orchestrates all processing steps.

    Uses Perplexity-style two-stage retrieval:
    - Stage 1: Fast vector search for candidates
    - Stage 2: LLM refinement for best matches
    """

    def __init__(self, lazy_load: bool = True):
        """
        Initialize the pipeline.

        Args:
            lazy_load: If True, models are loaded on first use. If False, load immediately.
        """
        # Initialize intent classifier and safety layer
        self.intent_classifier = get_intent_classifier()
        self.safety_layer = get_safety_layer()

        # Product store (ChromaDB)
        self._product_store = None

        # Models (lazy loaded by default for faster startup)
        self._medical_model = None
        self._translator = None
        self._lazy_load = lazy_load

        if not lazy_load:
            self._load_medical_model()
            self._load_translator()
            self._load_product_store()

    def _load_product_store(self):
        """Load the product store."""
        if self._product_store is None:
            self._product_store = get_product_store()

    @property
    def product_store(self):
        """Get the product store, loading it if necessary."""
        if self._product_store is None:
            self._load_product_store()
        return self._product_store

    def _load_translator(self):
        """Load the translator models."""
        if self._translator is None:
            self._translator = get_translator()
            # Pre-load both translation models
            self._translator.load_all()

    @property
    def translator(self):
        """Get the translator, loading it if necessary."""
        if self._translator is None:
            self._translator = get_translator()
        return self._translator

    def _load_medical_model(self):
        """Load the MedGemma model."""
        if self._medical_model is None:
            self._medical_model = get_medical_model()
            self._medical_model.load()

    @property
    def medical_model(self):
        """Get the medical model, loading it if necessary."""
        if self._medical_model is None:
            self._load_medical_model()
        return self._medical_model

    def process(self, user_input: str) -> PipelineResult:
        """
        Process user input through the full pipeline.

        Steps:
        1. Intent Classification - is this a medical query?
        2. Translate BG → EN
        3. Medical Reasoning (MedGemma) - understand symptoms
        4. Safety Check (red flags, OTC only)
        5a. Product Retrieval (Vector DB) - get top-K candidates [FAST]
        5b. Product Refinement (LLM) - pick best matches [ACCURATE]
        6. Translate EN → BG
        7. Format Response
        """
        start_time = time.perf_counter()
        logger.info(f"Processing query", extra={
            "query_length": len(user_input),
            "query_preview": user_input[:50] + "..." if len(user_input) > 50 else user_input
        })

        # Step 1: Intent Classification
        is_medical, confidence, reason = self.intent_classifier.is_medical_query(user_input)
        logger.debug(f"Intent classification", extra={
            "is_medical": is_medical,
            "confidence": confidence,
            "reason": reason
        })
        if not is_medical:
            return PipelineResult(
                response=self.intent_classifier.get_rejection_message("bg", reason),
                is_medical=False,
                original_text=user_input
            )

        # Step 2: Translate BG → EN
        translated = self._translate_to_english(user_input)

        # Step 3: Medical Reasoning - understand symptoms and suggest treatment types
        medical_reasoning = self._get_medical_reasoning(translated)

        # Check if MedGemma refused to help (non-medical query slipped through)
        if self._is_refusal_response(medical_reasoning):
            return PipelineResult(
                response=self.intent_classifier.get_rejection_message("bg"),
                is_medical=False,
                original_text=user_input,
                translated_text=translated,
                medical_reasoning=medical_reasoning
            )

        # Step 4: Safety Check (check BOTH original Bulgarian and translated English)
        is_red_flag, safety_message = self._check_safety(user_input, translated, medical_reasoning)
        logger.debug(f"Safety check", extra={"is_red_flag": is_red_flag})
        if is_red_flag:
            logger.warning(f"Red flag detected, referring to doctor")
            # Safety messages are already in Bulgarian, no translation needed
            return PipelineResult(
                response=safety_message,
                is_medical=True,
                is_red_flag=True,
                original_text=user_input,
                translated_text=translated,
                medical_reasoning=medical_reasoning
            )

        # Step 5a: Product Retrieval - Vector DB returns top-K candidates (FAST)
        candidate_products = self._retrieve_product_candidates(medical_reasoning)
        logger.debug(f"Vector search returned {len(candidate_products)} candidates")

        # Filter to OTC-only products
        candidate_products = self.safety_layer.filter_otc_only(candidate_products)

        # Step 5b: Product Refinement - LLM picks best matches (ACCURATE)
        selected_products = self._refine_product_selection(
            user_query=translated,
            medical_reasoning=medical_reasoning,
            candidates=candidate_products
        )

        # Check for warning-level symptoms (not blocking, but add message)
        warning_result = self.safety_layer.check_safety(user_input)

        # Step 6 & 7: Translate back and format response
        final_response = self._format_response(
            medical_reasoning=medical_reasoning,
            products=selected_products
        )

        # Add warning message if applicable
        final_response = self.safety_layer.add_safety_disclaimer(final_response, warning_result)

        # Add child-specific disclaimer if query is about children/babies
        if self._is_child_related_query(user_input):
            final_response = self._add_child_disclaimer(final_response)

        # Add safety information disclaimer for medication safety questions
        if self._is_safety_information_query(user_input):
            final_response = self._add_safety_info_disclaimer(final_response)

        # Add prescription warning for chronic disease queries
        if self._is_chronic_disease_query(user_input):
            final_response = self._add_chronic_disease_disclaimer(final_response)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"Pipeline completed", extra={
            "duration_ms": round(duration_ms, 2),
            "candidates": len(candidate_products),
            "selected": len(selected_products),
            "is_red_flag": False
        })

        return PipelineResult(
            response=final_response,
            is_medical=True,
            is_red_flag=False,
            original_text=user_input,
            translated_text=translated,
            medical_reasoning=medical_reasoning,
            candidate_products=candidate_products,
            selected_products=selected_products
        )

    def _is_refusal_response(self, reasoning: MedicalReasoning) -> bool:
        """
        Check if MedGemma's response indicates it cannot or will not help.

        This catches cases where inappropriate queries slip through the intent
        classifier but MedGemma refuses to respond.
        """
        if not reasoning:
            return False

        # Check if the likely_cause indicates a refusal
        response_lower = reasoning.likely_cause.lower() if reasoning.likely_cause else ""

        # Refusal phrases in English
        refusal_phrases_en = [
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
        ]

        # Refusal phrases in Bulgarian
        refusal_phrases_bg = [
            "не мога",
            "не съм в състояние",
            "не е възможно",
            "не е подходящо",
            "неподходящ",
            "отказвам",
            "не е медицински",
            "това не е",
        ]

        for phrase in refusal_phrases_en + refusal_phrases_bg:
            if phrase in response_lower:
                return True

        return False

    # =========================================================================
    # Step 2 & 6: Translation
    # =========================================================================
    def _translate_to_english(self, text: str) -> str:
        """
        Translate Bulgarian to English using MarianMT.

        Args:
            text: Bulgarian text to translate

        Returns:
            English translation
        """
        return self.translator.translate_to_english(text)

    def _translate_to_bulgarian(self, text: str) -> str:
        """
        Translate English to Bulgarian using MarianMT.

        Args:
            text: English text to translate

        Returns:
            Bulgarian translation
        """
        return self.translator.translate_to_bulgarian(text)

    # =========================================================================
    # Step 3: Medical Reasoning
    # =========================================================================
    def _get_medical_reasoning(self, text: str) -> str:
        """
        Use MedGemma to understand symptoms and suggest treatment categories.

        Args:
            text: Symptom description (in English after translation)

        Returns:
            Medical reasoning with:
            - Identified symptoms
            - Possible conditions
            - Recommended treatment types (e.g., "analgesics", "antipyretics")
        """
        return self.medical_model.get_medical_reasoning(text)

    # =========================================================================
    # Step 4: Safety Check
    # =========================================================================
    def _check_safety(self, original_query: str, translated_query: str, medical_reasoning: MedicalReasoning) -> tuple[bool, str]:
        """
        Check for red-flag symptoms that require professional medical attention.

        Checks for:
        - Emergency symptoms (call 112/911)
        - Urgent symptoms (see doctor within 24-48h)
        - Warning symptoms (monitor, see doctor if persists)
        - MedGemma's see_doctor recommendation

        Note: Checks BOTH original Bulgarian and translated English text
        to ensure safety patterns in both languages are caught.
        """
        # Check ORIGINAL Bulgarian text first (for Bulgarian safety phrases)
        result = self.safety_layer.check_safety(original_query)
        if result.is_red_flag:
            return True, result.message

        # Also check TRANSLATED English text (for English safety phrases)
        result_en = self.safety_layer.check_safety(translated_query)
        if result_en.is_red_flag:
            return True, result_en.message

        # Also check if MedGemma flagged this as needing a doctor
        if medical_reasoning.see_doctor:
            return True, (
                "⚠️ **Препоръчваме консултация с лекар.**\n\n"
                "Базирано на вашите симптоми, препоръчваме да се консултирате "
                "с медицински специалист за правилна диагноза и лечение."
            )

        return False, ""

    # =========================================================================
    # Step 5a: Product Retrieval (Vector DB - FAST)
    # =========================================================================
    def _retrieve_product_candidates(self, medical_reasoning: MedicalReasoning, top_k: int = 10) -> list:
        """
        Stage 1: Fast vector similarity search to get top-K product candidates.

        Uses ChromaDB with multilingual embeddings to find relevant products
        based on the medical reasoning from MedGemma.

        Args:
            medical_reasoning: The medical analysis from MedGemma
            top_k: Number of candidates to retrieve (default: 10)

        Returns:
            List of Product objects (candidates, not final selection)
        """
        # Check if product store has products
        if self.product_store.collection.count() == 0:
            logger.warning("Product store is empty. Run product_store.py --reload to load products.")
            return []

        # Build search query from medical reasoning
        search_parts = []
        if medical_reasoning.treatment_type:
            search_parts.append(medical_reasoning.treatment_type)
        if medical_reasoning.symptoms:
            search_parts.extend(medical_reasoning.symptoms)
        if medical_reasoning.likely_cause:
            search_parts.append(medical_reasoning.likely_cause)

        search_query = " ".join(search_parts) if search_parts else "medicine"

        # Search ChromaDB using the medical reasoning as query
        results = self.product_store.search(search_query, n_results=top_k)

        # Convert results to Product objects
        products = []
        for result in results:
            try:
                product = Product.from_chromadb(result)
                products.append(product)
            except Exception as e:
                logger.warning(f"Failed to parse product", extra={"error": str(e)})
                continue

        return products

    # =========================================================================
    # Step 5b: Product Refinement (LLM - ACCURATE)
    # =========================================================================
    def _refine_product_selection(
        self,
        user_query: str,
        medical_reasoning: MedicalReasoning,
        candidates: list,
        max_products: int = 3
    ) -> list:
        """
        Stage 2: Use LLM to pick the best products from candidates.

        This follows the Perplexity pattern:
        - Given original query + candidate matches
        - Pick the best entity match(es)

        Args:
            user_query: Original user query (translated to English)
            medical_reasoning: Medical analysis from MedGemma
            candidates: List of Product objects from vector search
            max_products: Maximum products to recommend (default: 3)

        Returns:
            List of best-matching Product objects
        """
        if not candidates:
            return []

        # Convert MedicalReasoning to string for LLM refinement
        reasoning_str = f"Symptoms: {', '.join(medical_reasoning.symptoms)}. "
        reasoning_str += f"Likely cause: {medical_reasoning.likely_cause}. "
        reasoning_str += f"Treatment type: {medical_reasoning.treatment_type}."

        # Use MedGemma to refine the selection
        return self.medical_model.refine_product_selection(
            user_query=user_query,
            medical_reasoning=reasoning_str,
            candidate_products=candidates,
            max_products=max_products
        )

    # =========================================================================
    # Step 6: Special Context Detection
    # =========================================================================
    def _is_child_related_query(self, text: str) -> bool:
        """
        Check if query is about children or babies.

        Returns True if the query mentions children, babies, or age-related terms.
        """
        child_keywords = {
            # Bulgarian
            'бебе', 'бебета', 'бебешки', 'бебешка', 'бебето',
            'дете', 'деца', 'детски', 'детска', 'детето',
            'новородено', 'кърмаче', 'малко дете',
            'месечно', 'годишно', 'месеца', 'години',
            'педиатър', 'педиатричен',
            'никнене на зъби', 'зъбки',
            'дозировка за дете', 'доза за дете',
            'за деца', 'за бебета',
            # English
            'baby', 'babies', 'infant', 'infants',
            'child', 'children', 'kid', 'kids',
            'toddler', 'newborn',
            'months old', 'years old',
            'pediatric', 'teething',
        }
        text_lower = text.lower()
        return any(kw in text_lower for kw in child_keywords)

    def _is_safety_information_query(self, text: str) -> bool:
        """
        Check if query is asking about medication safety.

        These queries should always include a safety disclaimer.
        """
        safety_keywords = {
            # Bulgarian - dosage/overdose
            'двойна доза', 'тройна доза', 'предозиране', 'предозирах',
            'максимална доза', 'максималната доза', 'колко мога да взема',
            'прекалено много', 'твърде много',
            # Bulgarian - interactions
            'алкохол с', 'пия алкохол', 'комбинирам', 'смесвам',
            'взема заедно', 'едновременно',
            # Bulgarian - safety concerns
            'безопасно ли е', 'опасно ли е', 'вредно ли е',
            'странични ефекти', 'странични действия', 'нежелани реакции',
            'противопоказания', 'да не взема',
            # Bulgarian - pregnancy/breastfeeding
            'по време на бременност', 'бременна', 'кърмене', 'кърмя',
            # English
            'double dose', 'overdose', 'maximum dose',
            'alcohol with', 'combine', 'mix medications',
            'safe to take', 'dangerous', 'harmful',
            'side effects', 'contraindications',
            'during pregnancy', 'pregnant', 'breastfeeding',
        }
        text_lower = text.lower()
        return any(kw in text_lower for kw in safety_keywords)

    def _add_child_disclaimer(self, response: str) -> str:
        """Add child-specific safety disclaimer to response."""
        disclaimer = """
⚠️ **Важно за деца и бебета:**
- Винаги проверявайте възрастовите ограничения на опаковката
- Дозировката зависи от възрастта и теглото на детето
- Консултирайте се с педиатър преди даване на лекарства на бебета под 6 месеца
- При съмнение, попитайте фармацевт за подходящата доза"""
        return response + "\n" + disclaimer

    def _add_safety_info_disclaimer(self, response: str) -> str:
        """Add medication safety disclaimer to response."""
        # Don't add if response already contains emergency message
        if "112" in response or "СПЕШНО" in response:
            return response

        disclaimer = """
💊 **Важна информация за безопасност:**
- Винаги спазвайте препоръчаната доза от листовката
- Не комбинирайте лекарства без консултация с фармацевт или лекар
- При съмнение за предозиране, обадете се на Токсикологичен център или 112
- Консултирайте се с лекар преди употреба при бременност или кърмене"""
        return response + "\n" + disclaimer

    def _is_chronic_disease_query(self, text: str) -> bool:
        """
        Check if query is about chronic disease medications.

        These typically require prescriptions and should include a warning.
        """
        chronic_keywords = {
            # Bulgarian - diabetes
            'диабет', 'диабетик', 'захарен диабет', 'инсулин',
            'кръвна захар', 'глюкоза',
            # Bulgarian - thyroid
            'щитовидна', 'щитовидната жлеза', 'тироксин',
            'хипотиреоидизъм', 'хипертиреоидизъм',
            # Bulgarian - cardiovascular
            'хипертония', 'високо кръвно', 'кръвно налягане',
            'сърдечна недостатъчност', 'аритмия',
            'холестерол', 'статини',
            # Bulgarian - respiratory
            'астма', 'бронхиална астма', 'хобб',
            # Bulgarian - neurological
            'епилепсия', 'паркинсон', 'множествена склероза',
            # Bulgarian - mental health (prescription)
            'антидепресант', 'антипсихотик', 'шизофрения',
            # Bulgarian - autoimmune
            'ревматоиден артрит', 'лупус', 'имуносупресор',
            # English equivalents
            'diabetes', 'insulin', 'blood sugar',
            'thyroid', 'hypothyroidism', 'hyperthyroidism',
            'hypertension', 'blood pressure',
            'asthma', 'copd',
            'epilepsy', 'parkinson',
            'antidepressant', 'antipsychotic',
        }
        text_lower = text.lower()
        return any(kw in text_lower for kw in chronic_keywords)

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

    # =========================================================================
    # Step 7: Response Formatting
    # =========================================================================
    def _format_response(
        self,
        medical_reasoning: MedicalReasoning,
        products: list,
        translate_reasoning: bool = True
    ) -> str:
        """
        Format the final response as a friendly pharmacy assistant.

        Args:
            medical_reasoning: The medical analysis from MedGemma
            products: List of recommended products
            translate_reasoning: Whether to translate reasoning to Bulgarian (default: True)
        """
        response_parts = []

        # Medical analysis section - show MedGemma's reasoning
        response_parts.append("## 🔍 Медицински анализ\n")

        # Build English text for translation
        english_parts = []
        if medical_reasoning.symptoms:
            english_parts.append(f"Symptoms: {', '.join(medical_reasoning.symptoms)}")
        if medical_reasoning.likely_cause:
            english_parts.append(f"Probable cause: {medical_reasoning.likely_cause}")
        if medical_reasoning.explanation:
            english_parts.append(f"Explanation: {medical_reasoning.explanation}")
        if medical_reasoning.how_treatment_helps:
            english_parts.append(f"How treatment helps: {medical_reasoning.how_treatment_helps}")
        if medical_reasoning.self_care_tips:
            english_parts.append(f"Self-care tips: {'; '.join(medical_reasoning.self_care_tips)}")
        if medical_reasoning.duration_guidance:
            english_parts.append(f"Recovery time: {medical_reasoning.duration_guidance}")
        if medical_reasoning.warnings:
            english_parts.append(f"Warnings: {'; '.join(medical_reasoning.warnings)}")

        english_text = ". ".join(english_parts)

        # Translate to Bulgarian
        if translate_reasoning and english_text:
            try:
                bulgarian_text = self._translate_to_bulgarian(english_text)
            except Exception as e:
                logger.warning(f"Failed to translate reasoning: {e}")
                bulgarian_text = english_text
        else:
            bulgarian_text = english_text

        # Format the analysis sections
        if medical_reasoning.symptoms:
            response_parts.append(f"**🩺 Идентифицирани симптоми:** {', '.join(medical_reasoning.symptoms)}\n")

        if medical_reasoning.likely_cause or medical_reasoning.explanation:
            cause_text = medical_reasoning.likely_cause
            if translate_reasoning and cause_text:
                try:
                    cause_text = self._translate_to_bulgarian(cause_text)
                except Exception:
                    pass
            response_parts.append(f"**🔬 Вероятна причина:** {cause_text}\n")

            if medical_reasoning.explanation:
                explanation = medical_reasoning.explanation
                if translate_reasoning:
                    try:
                        explanation = self._translate_to_bulgarian(explanation)
                    except Exception:
                        pass
                response_parts.append(f"📋 {explanation}\n")

        if medical_reasoning.treatment_type or medical_reasoning.how_treatment_helps:
            treatment = medical_reasoning.treatment_type
            if translate_reasoning and treatment:
                try:
                    treatment = self._translate_to_bulgarian(treatment)
                except Exception:
                    pass
            response_parts.append(f"**💉 Препоръчано лечение:** {treatment}\n")

            if medical_reasoning.how_treatment_helps:
                how_helps = medical_reasoning.how_treatment_helps
                if translate_reasoning:
                    try:
                        how_helps = self._translate_to_bulgarian(how_helps)
                    except Exception:
                        pass
                response_parts.append(f"📋 {how_helps}\n")

        if medical_reasoning.self_care_tips:
            response_parts.append("**🏠 Съвети за домашна грижа:**")
            for tip in medical_reasoning.self_care_tips:
                if translate_reasoning:
                    try:
                        tip = self._translate_to_bulgarian(tip)
                    except Exception:
                        pass
                response_parts.append(f"• {tip}")
            response_parts.append("")

        if medical_reasoning.duration_guidance:
            duration = medical_reasoning.duration_guidance
            if translate_reasoning:
                try:
                    duration = self._translate_to_bulgarian(duration)
                except Exception:
                    pass
            response_parts.append(f"**⏱️ Очаквано възстановяване:** {duration}\n")

        if medical_reasoning.warnings:
            response_parts.append("**⚠️ Важни предупреждения:**")
            for warning in medical_reasoning.warnings:
                if translate_reasoning:
                    try:
                        warning = self._translate_to_bulgarian(warning)
                    except Exception:
                        pass
                response_parts.append(f"• {warning}")
            response_parts.append("")

        # Product recommendations section
        response_parts.append("\n## 💊 Препоръчани продукти\n")

        if products:
            for i, product in enumerate(products, 1):
                if isinstance(product, Product):
                    response_parts.append(f"### {i}. {product.to_display_string()}\n")
                else:
                    response_parts.append(f"### {i}. {product}\n")
        else:
            response_parts.append("*Съжалявам, не намерих подходящи продукти в каталога.*")

        # Add see doctor warning if needed
        if medical_reasoning.see_doctor:
            response_parts.append("\n🏥 **Важно:** Препоръчваме консултация с лекар за вашите симптоми.")

        # Disclaimer (always shown)
        response_parts.append("\n---")
        response_parts.append("*Това е информационна услуга, не медицински съвет. "
                            "Консултирайте се с фармацевт за повече информация.*")

        return "\n".join(response_parts)


# Global pipeline instance
_pipeline: Optional[Pipeline] = None


def get_pipeline() -> Pipeline:
    """Get or create the pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline
