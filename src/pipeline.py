"""
Pipeline orchestrator for the ViaPharma OTC Chatbot.
Each step can be swapped out for real implementations as we build them.

Pipeline follows the Perplexity two-stage retrieval pattern:
1. Vector DB returns top-K candidates (fast, cheap)
2. LLM refines and picks best matches (accurate)
"""

from dataclasses import dataclass, field
from typing import Optional

from src.medical_model import get_medical_model
from src.translator import get_translator


@dataclass
class Product:
    """Represents a product from the catalogue."""
    id: str
    name: str
    category: str
    active_ingredients: str = ""
    indications: str = ""
    dosage: str = ""
    contraindications: str = ""
    warnings: str = ""
    price: float = 0.0
    is_otc: bool = True

    def to_display_string(self) -> str:
        """Format product for display in chat."""
        parts = [f"**{self.name}** ({self.price:.2f} лв)"]
        if self.indications:
            parts.append(f"   - {self.indications}")
        if self.dosage:
            parts.append(f"   - Дозировка: {self.dosage}")
        if self.warnings:
            parts.append(f"   - ⚠️ {self.warnings}")
        return "\n".join(parts)


@dataclass
class PipelineResult:
    """Result from the pipeline processing."""
    response: str
    is_medical: bool = True
    is_red_flag: bool = False
    original_text: str = ""
    translated_text: str = ""
    medical_reasoning: str = ""
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
        # Component placeholders - will be replaced with real implementations
        self.intent_classifier = None
        self.safety_layer = None
        self.vector_store = None

        # Models (lazy loaded by default for faster startup)
        self._medical_model = None
        self._translator = None
        self._lazy_load = lazy_load

        if not lazy_load:
            self._load_medical_model()
            self._load_translator()

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

        # Step 1: Intent Classification
        is_medical = self._classify_intent(user_input)
        if not is_medical:
            return PipelineResult(
                response="Мога да помогна само с въпроси, свързани със здравето. Моля, опишете вашите симптоми.",
                is_medical=False,
                original_text=user_input
            )

        # Step 2: Translate BG → EN
        translated = self._translate_to_english(user_input)

        # Step 3: Medical Reasoning - understand symptoms and suggest treatment types
        medical_reasoning = self._get_medical_reasoning(translated)

        # Step 4: Safety Check
        is_red_flag, safety_message = self._check_safety(translated, medical_reasoning)
        if is_red_flag:
            return PipelineResult(
                response=self._translate_to_bulgarian(safety_message),
                is_medical=True,
                is_red_flag=True,
                original_text=user_input,
                translated_text=translated,
                medical_reasoning=medical_reasoning
            )

        # Step 5a: Product Retrieval - Vector DB returns top-K candidates (FAST)
        candidate_products = self._retrieve_product_candidates(medical_reasoning)

        # Step 5b: Product Refinement - LLM picks best matches (ACCURATE)
        selected_products = self._refine_product_selection(
            user_query=translated,
            medical_reasoning=medical_reasoning,
            candidates=candidate_products
        )

        # Step 6 & 7: Translate back and format response
        final_response = self._format_response(
            medical_reasoning=medical_reasoning,
            products=selected_products
        )

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

    # =========================================================================
    # Step 1: Intent Classification
    # =========================================================================
    def _classify_intent(self, text: str) -> bool:
        """
        Check if input is a medical/health query.

        Placeholder: always returns True
        TODO: Replace with DistilBERT multilingual classifier
        """
        return True

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
    def _check_safety(self, user_query: str, medical_reasoning: str) -> tuple[bool, str]:
        """
        Check for red-flag symptoms that require professional medical attention.

        Placeholder: no red flags
        TODO: Replace with safety layer checking for:
        - Chest pain, difficulty breathing
        - Sudden severe symptoms
        - Symptoms lasting too long
        - Any prescription-only conditions
        """
        return False, ""

    # =========================================================================
    # Step 5a: Product Retrieval (Vector DB - FAST)
    # =========================================================================
    def _retrieve_product_candidates(self, medical_reasoning: str, top_k: int = 10) -> list:
        """
        Stage 1: Fast vector similarity search to get top-K product candidates.

        Placeholder: returns empty list
        TODO: Replace with ChromaDB vector search

        Args:
            medical_reasoning: The medical analysis from MedGemma
            top_k: Number of candidates to retrieve (default: 10)

        Returns:
            List of Product objects (candidates, not final selection)
        """
        # Placeholder products for testing
        return [
            Product(
                id="1",
                name="Парацетамол 500mg",
                category="Аналгетици",
                indications="Главоболие, температура, болки",
                dosage="1-2 таблетки на всеки 4-6 часа",
                contraindications="Чернодробни заболявания",
                warnings="Не превишавайте 8 таблетки дневно",
                price=3.99,
                is_otc=True
            ),
            Product(
                id="2",
                name="Ибупрофен 400mg",
                category="НСПВС",
                indications="Болка, възпаление, температура",
                dosage="1 таблетка на всеки 6-8 часа",
                contraindications="Стомашни язви, бременност",
                warnings="Приемайте с храна",
                price=5.99,
                is_otc=True
            ),
            Product(
                id="3",
                name="Аспирин 500mg",
                category="Аналгетици",
                indications="Болка, температура, възпаление",
                dosage="1-2 таблетки на всеки 4 часа",
                contraindications="Деца под 16, астма",
                warnings="Не приемайте на празен стомах",
                price=4.50,
                is_otc=True
            ),
        ]

    # =========================================================================
    # Step 5b: Product Refinement (LLM - ACCURATE)
    # =========================================================================
    def _refine_product_selection(
        self,
        user_query: str,
        medical_reasoning: str,
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

        # Use MedGemma to refine the selection
        return self.medical_model.refine_product_selection(
            user_query=user_query,
            medical_reasoning=medical_reasoning,
            candidate_products=candidates,
            max_products=max_products
        )

    # =========================================================================
    # Step 7: Response Formatting
    # =========================================================================
    def _format_response(self, medical_reasoning: str, products: list) -> str:
        """Format the final response with products and disclaimer."""

        response_parts = []

        # Medical context (translated back to Bulgarian)
        response_parts.append(self._translate_to_bulgarian(medical_reasoning))

        # Product recommendations
        if products:
            response_parts.append("\n\n**Препоръчани продукти:**\n")
            for i, product in enumerate(products, 1):
                if isinstance(product, Product):
                    response_parts.append(f"{i}. {product.to_display_string()}\n")
                else:
                    response_parts.append(f"{i}. {product}\n")
        else:
            response_parts.append("\n\n*[Продуктовият каталог все още не е зареден]*")

        # Disclaimer (always shown)
        response_parts.append("\n---")
        response_parts.append("*Това е информационна услуга, не медицински съвет.*")
        response_parts.append("*Консултирайте се с фармацевт за повече информация.*")

        return "\n".join(response_parts)


# Global pipeline instance
_pipeline: Optional[Pipeline] = None


def get_pipeline() -> Pipeline:
    """Get or create the pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline
