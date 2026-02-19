"""
Common utilities and models shared across pipeline and services.

This module provides shared functionality to prevent circular imports
between the pipeline and services layers.

Dependency hierarchy:
- common (no dependencies on pipeline or services)
- pipeline (imports from common)
- services (imports from common and pipeline)
- orchestrator (imports from common, pipeline, and services)

Note: To avoid circular imports at package initialization time, we only
export models from this __init__.py. Import contraindications directly:
    from src.common.contraindications import extract_user_conditions
"""

# Only export models to avoid circular import during package initialization
from src.common.models import (
    PipelineResult,
    Product,
)

__all__ = [
    "Product",
    "PipelineResult",
]
