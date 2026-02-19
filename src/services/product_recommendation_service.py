"""
Product Recommendation Service.

Handles product search, retrieval, and recommendation logic:
- Building search queries from medical reasoning
- Extracting drug names from queries
- Orchestrating product search pipeline (retrieve → rerank → refine → deduplicate)
- Converting results to Product objects
"""

from src.logging_config import get_logger
from src.medical_model import MedicalReasoning
from src.common.models import Product

logger = get_logger("viapharma.services.product_recommendation")


class ProductRecommendationService:
    """
    Service for product search and recommendations.

    Responsibilities:
    - Build search queries from medical reasoning
    - Extract drug names from queries
    - Orchestrate product search pipeline
    - Convert search results to Product objects
    """

    # Common OTC drug names for extraction
    DRUG_NAME_PATTERNS = {
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

    def __init__(
        self,
        product_matcher=None,
        safety_validator=None,
        safety_layer=None,
        medical_reasoning_service=None,
    ):
        """
        Initialize ProductRecommendationService.

        Args:
            product_matcher: Optional ProductMatcher instance
            safety_validator: Optional SafetyValidator instance
            safety_layer: Optional SafetyLayer instance
            medical_reasoning_service: Optional MedicalReasoningService instance
        """
        self.product_matcher = product_matcher
        self.safety_validator = safety_validator
        self.safety_layer = safety_layer
        self.medical_reasoning_service = medical_reasoning_service

    def build_search_query(
        self, medical_reasoning: MedicalReasoning, original_query: str = ""
    ) -> str:
        """
        Build search query from medical reasoning components.

        For drug combination queries, extracts drug names from original query
        since MedGemma returns generic terms like 'drug interaction query'.

        Args:
            medical_reasoning: MedicalReasoning object with symptoms, treatment type, etc.
            original_query: Original user query

        Returns:
            Search query string for product retrieval
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
            useful_symptoms = [
                s for s in medical_reasoning.symptoms if s.lower() not in non_useful_symptoms
            ]
            parts.extend(useful_symptoms)

        # For drug combo queries, extract actual drug names from original query
        if original_query and self.medical_reasoning_service:
            if self.medical_reasoning_service.is_drug_combination_query(original_query):
                drug_names = self.extract_drug_names(original_query)
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

    def extract_drug_names(self, text: str) -> list[str]:
        """
        Extract known drug names from text for product search.

        Args:
            text: User input text

        Returns:
            List of drug names found in text
        """
        text_lower = text.lower()
        found = []
        for drug in self.DRUG_NAME_PATTERNS:
            if drug in text_lower:
                found.append(drug)
        return found

    def convert_to_products(self, results: list) -> list[Product]:
        """
        Convert ChromaDB results to Product objects.

        Args:
            results: List of ChromaDB search results

        Returns:
            List of Product objects
        """
        products = []
        for result in results:
            try:
                products.append(Product.from_chromadb(result))
            except Exception as e:
                logger.warning("Failed to parse product", extra={"error": str(e)})
        return products

    def get_recommended_products(
        self,
        medical_reasoning: MedicalReasoning,
        original_query: str,
        user_conditions: list[str] = None,
        max_products: int = 3,
    ) -> tuple[list[Product], list[tuple]]:
        """
        Orchestrate the full product recommendation pipeline.

        Pipeline stages:
        1. Retrieve candidates from vector DB
        2. Filter by safety (OTC only, age appropriateness)
        3. Filter by contraindications
        4. Pharmacological reranking
        5. LLM-based refinement
        6. Deduplication by ingredient

        Args:
            medical_reasoning: MedicalReasoning object
            original_query: Original user query
            user_conditions: List of user medical conditions
            max_products: Maximum number of products to return

        Returns:
            Tuple of (selected_products, contraindicated_products)
        """
        if not self.product_matcher:
            logger.error("ProductMatcher not available for product recommendation")
            return [], []

        user_conditions = user_conditions or []

        # Stage 1: Retrieve candidates from vector DB
        logger.info("Stage 1: Retrieving product candidates")
        candidate_products = self.product_matcher.retrieve_candidates(
            medical_reasoning, original_query
        )

        # Stage 2: Filter by safety (OTC only)
        if self.safety_layer:
            logger.info("Stage 2: Filtering for OTC products only")
            candidate_products = self.safety_layer.filter_otc_only(candidate_products)

        # Stage 3: Filter by age appropriateness
        if self.safety_validator:
            logger.info("Stage 3: Filtering by age appropriateness")
            candidate_products = self.safety_validator.filter_by_age_appropriateness(
                candidate_products, original_query
            )

        # Stage 4: Filter by contraindications
        contraindicated_products = []
        if user_conditions:
            logger.info(f"Stage 4: Filtering by contraindications ({len(user_conditions)} conditions)")
            # Import here to avoid circular dependency
            from src.common.contraindications import filter_by_contraindications

            candidate_products, contraindicated_products = filter_by_contraindications(
                candidate_products, user_conditions
            )

        # Stage 5: Pharmacological reranking
        logger.info("Stage 5: Pharmacological reranking")
        reranked_products = self.product_matcher.pharmacological_rerank(
            candidate_products, medical_reasoning.treatment_type
        )

        # Stage 6: LLM-based refinement (get extra for deduplication)
        logger.info("Stage 6: LLM-based product refinement")
        refined_products = self.product_matcher.refine_selection(
            reranked_products, medical_reasoning, max_products=max_products + 2
        )

        # Stage 7: Deduplicate by ingredient
        logger.info("Stage 7: Deduplicating by ingredient")
        selected_products = self.product_matcher.deduplicate_by_ingredient(
            refined_products, max_products=max_products
        )

        logger.info(
            f"Product recommendation pipeline complete: {len(selected_products)} products selected"
        )

        return selected_products, contraindicated_products

    def filter_by_name_match(
        self, products: list[Product], search_term: str
    ) -> list[Product]:
        """
        Filter products by name match for catalog queries.

        Delegates to ProductMatcher for actual filtering logic.

        Args:
            products: List of products to filter
            search_term: Search term to match against product names

        Returns:
            Filtered list of products
        """
        if not self.product_matcher:
            logger.warning("ProductMatcher not available, returning original products")
            return products

        return self.product_matcher.filter_by_name_match(products, search_term)


# Singleton instance
_product_recommendation_service = None


def get_product_recommendation_service(
    product_matcher=None,
    safety_validator=None,
    safety_layer=None,
    medical_reasoning_service=None,
) -> ProductRecommendationService:
    """
    Get or create the ProductRecommendationService singleton.

    Args:
        product_matcher: Optional ProductMatcher instance
        safety_validator: Optional SafetyValidator instance
        safety_layer: Optional SafetyLayer instance
        medical_reasoning_service: Optional MedicalReasoningService instance

    Returns:
        ProductRecommendationService instance
    """
    global _product_recommendation_service
    if _product_recommendation_service is None:
        _product_recommendation_service = ProductRecommendationService(
            product_matcher=product_matcher,
            safety_validator=safety_validator,
            safety_layer=safety_layer,
            medical_reasoning_service=medical_reasoning_service,
        )
    return _product_recommendation_service
