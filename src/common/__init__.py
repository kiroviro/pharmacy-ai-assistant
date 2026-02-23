"""
Common utilities and models shared across the pipeline.

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
