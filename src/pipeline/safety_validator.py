"""
Safety validation and filtering for the ViaPharma pipeline.

Handles age-appropriateness filtering, severity-based filtering, and safety disclaimers.
Separates safety validation logic from orchestration.

Extracted from orchestrator.py as part of Issue #1 (Phase 2).
"""

from src.logging_config import get_logger
from src.pipeline.constants import CHILD_KEYWORDS, CHRONIC_DISEASE_KEYWORDS, SAFETY_KEYWORDS
from src.common.models import Product
from src.pipeline.product_ingredients import is_combination_product

logger = get_logger("viapharma.safety_validator")


class SafetyValidator:
    """
    Handles safety validation, age-appropriate filtering, and disclaimer generation.

    Separates safety concerns from Pipeline orchestration.
    """

    # Age-related markers for filtering
    _ADULT_ONLY_MARKERS = {"за възрастни", "for adults", "над 15 години", "над 16 години", "над 18 години"}
    _CHILD_MARKERS = {"за деца", "бебе", "бейби", "baby", "junior", "джуниър", "юноши", "kids", "педиатрич"}
    _BABY_FORMS = {"суспензия", "сироп", "капки", "супозитори", "разтвор"}

    def filter_by_age_appropriateness(self, products: list[Product], original_query: str) -> list[Product]:
        """
        Filter and reorder products based on patient age from query.

        For child/baby queries:
        - Exclude products explicitly marked 'for adults'
        - Boost products marked for children/babies
        - Boost liquid forms (suspension, syrup, suppositories)

        Args:
            products: List of products to filter
            original_query: Original user query to detect age context

        Returns:
            Filtered and reordered products
        """
        query_lower = (original_query or "").lower()

        # Detect if query is about a child/baby
        is_child_query = any(kw in query_lower for kw in ["бебе", "дете", "детето", "месец", "бебет"])

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

    def filter_by_severity(self, products: list[Product], symptom_count: int) -> list[Product]:
        """
        Filter products by symptom severity and clinical relevance.

        For single symptoms: simple (single-ingredient) products first, combos last.
        Always: homeopathic products after evidence-based ones.

        Args:
            products: List of products to filter
            symptom_count: Number of symptoms (affects filtering strategy)

        Returns:
            Filtered and reordered products (max 3)
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

    # =========================================================================
    # Query Classification Methods
    # =========================================================================

    def is_child_related_query(self, text: str) -> bool:
        """
        Check if query mentions children, babies, or age-related terms.

        Args:
            text: Query text to check

        Returns:
            True if query is child-related
        """
        text_lower = text.lower()
        return any(kw in text_lower for kw in CHILD_KEYWORDS)

    def is_safety_information_query(self, text: str) -> bool:
        """
        Check if query asks about medication safety.

        Args:
            text: Query text to check

        Returns:
            True if query is about safety information
        """
        text_lower = text.lower()
        return any(kw in text_lower for kw in SAFETY_KEYWORDS)

    def is_chronic_disease_query(self, text: str) -> bool:
        """
        Check if query is about chronic disease medications.

        Args:
            text: Query text to check

        Returns:
            True if query is about chronic diseases
        """
        text_lower = text.lower()
        return any(kw in text_lower for kw in CHRONIC_DISEASE_KEYWORDS)

    # =========================================================================
    # Disclaimer Methods
    # =========================================================================

    def add_child_disclaimer(self, response: str) -> str:
        """
        Add child safety disclaimer to response.

        Note: Child safety is now handled inside the main template (triage section
        + safety block + product card warnings). No extra block appended.

        Args:
            response: Response text

        Returns:
            Response (unchanged, disclaimer is in template)
        """
        return response

    def add_safety_info_disclaimer(self, response: str) -> str:
        """
        Add safety information disclaimer to response.

        Note: Safety info is now in the main template (safety block + footer).
        No extra block appended.

        Args:
            response: Response text

        Returns:
            Response (unchanged, disclaimer is in template)
        """
        return response

    def add_chronic_disease_disclaimer(self, response: str) -> str:
        """
        Add prescription warning for chronic disease queries.

        Args:
            response: Response text

        Returns:
            Response with disclaimer if applicable
        """
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
