"""
User condition extraction and contraindication filtering.

DEPRECATED: This module has been moved to src.common.contraindications to prevent
circular imports between pipeline and services layers.

Please import from src.common.contraindications instead:
    from src.common.contraindications import (
        extract_user_conditions,
        filter_by_contraindications,
        check_contraindication,
    )

This file re-exports for backward compatibility but will be removed in a future version.
"""

import warnings

warnings.warn(
    "src.pipeline.conditions is deprecated. Import from src.common.contraindications instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new location for backward compatibility
from src.common.contraindications import (
    check_contraindication,
    extract_user_conditions,
    filter_by_contraindications,
)

__all__ = [
    "extract_user_conditions",
    "filter_by_contraindications",
    "check_contraindication",
]
