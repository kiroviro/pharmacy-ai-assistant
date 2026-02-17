"""
ViaPharma OTC Chatbot Pipeline Package.

This package provides the main pipeline orchestrator for the chatbot.
It follows the Perplexity two-stage retrieval pattern:
1. Vector DB returns top-K candidates (fast, cheap)
2. LLM refines and picks best matches (accurate)

Modules:
- constants: Keyword patterns for condition extraction and query detection
- models: Product and PipelineResult dataclasses
- conditions: User condition extraction and contraindication filtering
- product_ingredients: Ingredient recognition and product utilities
- query_router: Query type detection (catalog, comparison, help)
- orchestrator: Main Pipeline class
"""

# Re-export main classes for backward compatibility
from src.pipeline.conditions import (
    check_contraindication,
    extract_user_conditions,
    filter_by_contraindications,
)
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
from src.pipeline.models import PipelineResult, Product
from src.pipeline.orchestrator import Pipeline, get_pipeline

__all__ = [
    # Main classes
    "Pipeline",
    "get_pipeline",
    # Models
    "Product",
    "PipelineResult",
    # Condition functions
    "extract_user_conditions",
    "check_contraindication",
    "filter_by_contraindications",
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
