"""
Shared validation utilities.

Centralizes common validation patterns to prevent duplication.
"""


def is_valid_text(text: str | None, min_length: int = 3) -> bool:
    """
    Check if text is non-empty and meets minimum length requirement.

    Args:
        text: Text to validate (can be None)
        min_length: Minimum character length after stripping whitespace (default: 3)

    Returns:
        True if text is valid (non-None, non-empty after strip, meets min_length)
        False otherwise

    Examples:
        >>> is_valid_text("hello", min_length=3)
        True
        >>> is_valid_text("  ", min_length=3)
        False
        >>> is_valid_text(None)
        False
        >>> is_valid_text("hi", min_length=5)
        False
    """
    return bool(text and len(text.strip()) >= min_length)


def is_empty_or_whitespace(text: str | None) -> bool:
    """
    Check if text is None, empty, or only whitespace.

    Args:
        text: Text to check

    Returns:
        True if text is None, empty, or only whitespace
        False if text contains non-whitespace characters

    Examples:
        >>> is_empty_or_whitespace(None)
        True
        >>> is_empty_or_whitespace("")
        True
        >>> is_empty_or_whitespace("   ")
        True
        >>> is_empty_or_whitespace("hello")
        False
    """
    return not (text and text.strip())
