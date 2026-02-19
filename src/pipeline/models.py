"""
Data models for the ViaPharma pipeline.

DEPRECATED: This module has been moved to src.common.models to prevent
circular imports between pipeline and services layers.

Please import from src.common.models instead:
    from src.common.models import Product, PipelineResult

This file re-exports for backward compatibility but will be removed in a future version.
"""

import warnings

warnings.warn(
    "src.pipeline.models is deprecated. Import from src.common.models instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new location for backward compatibility
from src.common.models import PipelineResult, Product

__all__ = ["Product", "PipelineResult"]
