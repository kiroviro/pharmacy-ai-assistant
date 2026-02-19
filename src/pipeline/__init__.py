"""
ViaPharma OTC Chatbot Pipeline Package.

This package provides the main pipeline orchestrator for the chatbot.
It follows the Perplexity two-stage retrieval pattern:
1. Vector DB returns top-K candidates (fast, cheap)
2. LLM refines and picks best matches (accurate)

Modules:
- constants: Keyword patterns for condition extraction and query detection
- models: DEPRECATED - moved to src.common.models
- conditions: DEPRECATED - moved to src.common.contraindications
- product_ingredients: Ingredient recognition and product utilities
- query_router: Query type detection (catalog, comparison, help)
- orchestrator: Main Pipeline class

Note: Contraindication functions and data models have been moved to src.common
to prevent circular imports. Import from src.common instead:
    from src.common import Product, PipelineResult, extract_user_conditions
"""

# Re-export constants for backward compatibility
# NOTE: Pipeline and get_pipeline are NOT imported here to avoid circular imports.
# Import directly from orchestrator: from src.pipeline.orchestrator import Pipeline
from src.pipeline.constants import (
    CATALOG_CATEGORIES,
    CATALOG_PATTERNS_BG,
    CATALOG_PATTERNS_EN,
    CHILD_KEYWORDS,
    CHRONIC_DISEASE_KEYWORDS,
    CONTRAINDICATION_KEYWORDS,
    SAFETY_KEYWORDS,
    USER_CONDITION_PATTERNS,
)
from src.common.models import PipelineResult, Product

__all__ = [
    # Models (import from src.common preferred)
    "Product",
    "PipelineResult",
    # Constants
    "USER_CONDITION_PATTERNS",
    "CONTRAINDICATION_KEYWORDS",
    "CATALOG_PATTERNS_BG",
    "CATALOG_PATTERNS_EN",
    "CATALOG_CATEGORIES",
    "CHILD_KEYWORDS",
    "SAFETY_KEYWORDS",
    "CHRONIC_DISEASE_KEYWORDS",
]
