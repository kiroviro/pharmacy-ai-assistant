"""
Ingredient analysis and display formatting for the ViaPharma pipeline.

Handles ingredient extraction, treatment recommendations, and
ingredient section generation for responses.

Extracted from orchestrator.py as part of Issue #2 (Phase 5).
"""

from src.logging_config import get_logger
from src.pipeline.models import Product
from src.pipeline.product_ingredients import (
    INGREDIENT_BG_NAMES,
    extract_all_product_ingredients,
    get_recommended_ingredients,
)

logger = get_logger("viapharma.ingredient_analyzer")


class IngredientAnalyzer:
    """
    Handles ingredient extraction, recommendations, and display formatting.

    Separates ingredient analysis logic from Pipeline orchestration.
    Provides ingredient recommendations, action texts, and formatted sections.
    """

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

    def __init__(self):
        """Initialize IngredientAnalyzer (stateless)."""
        pass

    def get_recommended_ingredients(self, treatment_type: str) -> list[str]:
        """
        Get recommended active ingredients for a treatment type.

        Args:
            treatment_type: Treatment category (e.g., 'analgesics', 'antipyretics')

        Returns:
            List of recommended ingredient keys
        """
        return get_recommended_ingredients(treatment_type)

    def get_treatment_action_text(self, treatment_type: str) -> str:
        """
        Get a brief explanation of what the recommended ingredients do.

        Args:
            treatment_type: Treatment category

        Returns:
            Bulgarian description of treatment action, or empty string
        """
        if not treatment_type:
            return ""

        tt = treatment_type.lower().strip()

        # Direct match
        if tt in self._TREATMENT_ACTION_TEXTS:
            return self._TREATMENT_ACTION_TEXTS[tt]

        # Partial match (substring in either direction)
        for key, text in self._TREATMENT_ACTION_TEXTS.items():
            if key in tt or tt in key:
                return text

        return ""

    def extract_ingredients_from_products(
        self,
        products: list[Product],
        max_ingredients: int = 5
    ) -> list[str]:
        """
        Extract unique ingredients from a list of products.

        Used as fallback when LLM doesn't provide treatment recommendations.

        Args:
            products: List of products to extract from
            max_ingredients: Maximum number of unique ingredients to return

        Returns:
            List of unique ingredient keys
        """
        if not products:
            return []

        seen = set()
        for product in products[:5]:  # Check first 5 products
            for ingredient in extract_all_product_ingredients(product):
                seen.add(ingredient)
                if len(seen) >= max_ingredients:
                    break
            if len(seen) >= max_ingredients:
                break

        return list(seen)[:max_ingredients]

    def build_ingredients_section(
        self,
        treatment_type: str,
        products: list[Product],
        symptom_count: int = 1,
    ) -> list[str]:
        """
        Build the active ingredients section for the response.

        Creates a formatted list of recommended ingredients with action text.
        Always shows section when products are present (Issue #18).

        Args:
            treatment_type: Treatment category for recommendations
            products: List of products being recommended
            symptom_count: Number of symptoms (affects treatment advice)

        Returns:
            List of markdown-formatted lines for the ingredients section
        """
        parts = []

        if not products:
            return parts

        # Get recommended ingredients
        recommended = self.get_recommended_ingredients(treatment_type)

        # Fallback: derive from products when LLM omits
        if not recommended:
            recommended = self.extract_ingredients_from_products(products)

        # Always show ingredients section header
        parts.append("## 💊 Подходящи активни съставки\n")

        if recommended:
            # Convert to Bulgarian names
            ingredient_names_bg = [
                INGREDIENT_BG_NAMES.get(ing, ing)
                for ing in recommended
            ]

            # List ingredients
            for name_bg in ingredient_names_bg:
                parts.append(f"• **{name_bg}**")

            # Add action text if available
            action_text = self.get_treatment_action_text(treatment_type)
            if action_text:
                parts.append(f"\n{action_text}")
        else:
            # Fallback when ingredient extraction fails (Issue #18)
            parts.append("*Проверете активните съставки и дозировката в листовката на продукта.*")

        return parts

    def should_show_combo_note(
        self,
        products: list[Product],
        symptom_count: int
    ) -> bool:
        """
        Determine if a combination product note should be shown.

        Checks if any displayed products are combination products AND
        if the condition warrants combo treatment (multiple symptoms).

        Args:
            products: List of products being displayed
            symptom_count: Number of symptoms reported

        Returns:
            True if combo note should be shown
        """
        if not products or symptom_count < 2:
            return False

        # Check if any products are combo products
        for product in products:
            # Multi-ingredient product
            if len(extract_all_product_ingredients(product)) >= 2:
                return True

            # Cold/flu combo products
            title_lower = (product.title or "").lower()
            if "грип" in title_lower or "настинка" in title_lower:
                return True

        return False

    def get_combo_note(self) -> str:
        """
        Get the combination product explanatory note.

        Returns:
            Bulgarian markdown text explaining combo products
        """
        return (
            "**💊 Комбиниран продукт:** Този продукт съдържа няколко активни съставки, "
            "които работят заедно за облекчаване на множество симптоми едновременно."
        )
