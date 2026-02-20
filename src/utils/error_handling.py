"""
Error handling utilities with metrics tracking.

Provides decorators for consistent error handling with fallback values
and observability through metrics.
"""

import functools
from typing import Any, Callable, TypeVar

from src.logging_config import get_logger

logger = get_logger("viapharma.error_handling")

# Metrics counter for fallback usage
_fallback_metrics: dict[str, int] = {}

T = TypeVar("T")


def fallback_on_error(
    fallback: Any = None,
    log_level: str = "warning",
    metric_name: str | None = None,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    include_traceback: bool = False,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that catches exceptions and returns a fallback value.

    Also tracks metrics on how often fallbacks occur, helping detect
    production issues.

    Args:
        fallback: Value to return on error (default: None)
        log_level: Logging level - "debug", "info", "warning", "error" (default: "warning")
        metric_name: Optional metric name for tracking (defaults to function name)
        exceptions: Tuple of exception types to catch (default: (Exception,))
        include_traceback: Whether to include full traceback in logs (default: False)

    Returns:
        Decorated function that catches errors and returns fallback

    Examples:
        @fallback_on_error(fallback=[], log_level="warning", metric_name="llm_refinement_failures")
        def refine_selection(self, products):
            return self.llm.refine(products)  # Returns [] on error

        @fallback_on_error(fallback={}, exceptions=(KeyError, ValueError))
        def parse_config(self, data):
            return json.loads(data)  # Returns {} on KeyError or ValueError
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            nonlocal metric_name
            if metric_name is None:
                metric_name = f"{func.__module__}.{func.__name__}"

            try:
                return func(*args, **kwargs)
            except exceptions as e:
                # Track metrics
                _fallback_metrics[metric_name] = _fallback_metrics.get(metric_name, 0) + 1

                # Log with appropriate level
                log_func = getattr(logger, log_level, logger.warning)
                extra = {
                    "function": func.__name__,
                    "metric": metric_name,
                    "fallback_count": _fallback_metrics[metric_name],
                    "exception_type": type(e).__name__,
                }

                if include_traceback:
                    log_func(
                        f"{func.__name__} failed, using fallback: {e}",
                        extra=extra,
                        exc_info=True,
                    )
                else:
                    log_func(
                        f"{func.__name__} failed, using fallback: {e}",
                        extra=extra,
                    )

                return fallback

        return wrapper

    return decorator


def get_fallback_metrics() -> dict[str, int]:
    """
    Get current fallback metrics.

    Returns:
        Dictionary mapping metric names to fallback counts

    Examples:
        >>> metrics = get_fallback_metrics()
        >>> print(metrics)
        {'llm_refinement_failures': 3, 'translation_failures': 1}
    """
    return _fallback_metrics.copy()


def reset_fallback_metrics() -> None:
    """Reset all fallback metrics (useful for testing)."""
    global _fallback_metrics
    _fallback_metrics.clear()
