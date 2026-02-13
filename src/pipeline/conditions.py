"""
User condition extraction and contraindication filtering.

Handles detection of user health conditions (pregnancy, diabetes, etc.)
and filtering products that are contraindicated for those conditions.
"""

import re

from src.logging_config import get_logger
from src.pipeline.constants import USER_CONDITION_PATTERNS, CONTRAINDICATION_KEYWORDS

logger = get_logger("viapharma.pipeline.conditions")


def extract_user_conditions(text: str) -> list[str]:
    """
    Extract user conditions from query text (Bulgarian or English).

    Args:
        text: User query or translated text

    Returns:
        List of standardized condition identifiers
    """
    text_lower = text.lower()
    conditions = []

    for condition, patterns in USER_CONDITION_PATTERNS.items():
        for pattern in patterns:
            # Handle regex patterns (start with \b or contain special chars)
            if pattern.startswith(r"\b") or any(c in pattern for c in r"[]\d+*?"):
                if re.search(pattern, text_lower):
                    conditions.append(condition)
                    break
            else:
                if pattern in text_lower:
                    conditions.append(condition)
                    break

    if conditions:
        logger.info(f"Extracted user conditions: {conditions}")

    return conditions


def check_contraindication(product_contraindications: str, user_conditions: list[str]) -> tuple[bool, list[str]]:
    """
    Check if a product has contraindications matching user conditions.

    Args:
        product_contraindications: Product's contraindications text
        user_conditions: List of user condition identifiers

    Returns:
        Tuple of (has_contraindication, list of matching conditions)
    """
    if not product_contraindications or not user_conditions:
        return False, []

    contra_lower = product_contraindications.lower()
    matching_conditions = []

    for condition in user_conditions:
        keywords = CONTRAINDICATION_KEYWORDS.get(condition, [])
        for keyword in keywords:
            if keyword.lower() in contra_lower:
                matching_conditions.append(condition)
                break

    return len(matching_conditions) > 0, matching_conditions


def filter_by_contraindications(
    products: list,
    user_conditions: list[str],
    strict: bool = True
) -> tuple[list, list]:
    """
    Filter products that have contraindications matching user conditions.

    Args:
        products: List of Product objects
        user_conditions: List of user condition identifiers
        strict: If True, completely exclude contraindicated products
                If False, move them to end of list with warning

    Returns:
        Tuple of (safe_products, contraindicated_products)
    """
    if not user_conditions:
        return products, []

    safe_products = []
    contraindicated = []

    for product in products:
        has_contra, matching = check_contraindication(
            product.contraindications, user_conditions
        )

        if has_contra:
            logger.warning(
                f"Product '{product.title}' contraindicated for: {matching}",
                extra={"product_id": product.id, "conditions": matching}
            )
            contraindicated.append((product, matching))
        else:
            safe_products.append(product)

    logger.info(
        f"Contraindication filter: {len(safe_products)} safe, {len(contraindicated)} filtered",
        extra={"user_conditions": user_conditions}
    )

    return safe_products, contraindicated
