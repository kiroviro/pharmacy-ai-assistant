"""
Response validation to detect and handle garbage text in LLM outputs.

This module provides validation to catch MedGemma 4B hallucinations
where the model inserts irrelevant Bulgarian text (e.g., "защита на личните данни",
"зъбні протези") into medical reasoning outputs.

Root Cause: LLM hallucination (see docs/TECHNICAL_DEBT.md Issue #17)
Fix: Pattern-based detection + fallback handling
"""
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

# Known garbage patterns from E2E test analysis (Feb 14, 2026)
# These are Bulgarian phrases that should NEVER appear in medical advice
GARBAGE_PATTERNS = [
    "защита на личните",           # "protection of personal"
    "лични данни",                 # "personal data"
    "средство за защита",          # "means of protection"
    "зъбні протези",               # "dental prosthetics"
    "грижа за зъбні протези",      # "denture care"
    "протези",                     # "prosthetics" (standalone)
    "репелент",                    # "repellent"
    "комар",                       # "mosquito"
    "средство за комари",          # "mosquito repellent"
    "защита срещу комари",         # "mosquito protection"
]

# Patterns that indicate severe hallucination (sentence fragments, repetition)
SEVERE_HALLUCINATION_PATTERNS = [
    "може да се използва като средство за",  # "can be used as a means for"
    "за да може да се използва",             # "so that it can be used"
    "които могат да бъдат използвани",       # "which can be used"
]


def validate_response(response: str) -> Tuple[bool, List[str], str]:
    """
    Validate response for garbage text patterns.

    Args:
        response: The LLM-generated response to validate

    Returns:
        Tuple of (is_valid, garbage_patterns_found, severity)
        - is_valid: True if response is clean, False if garbage detected
        - garbage_patterns_found: List of garbage patterns found in response
        - severity: "none", "minor", "severe"
    """
    if not response or not response.strip():
        return True, [], "none"

    response_lower = response.lower()

    # Check for garbage patterns
    found_garbage = [p for p in GARBAGE_PATTERNS if p in response_lower]

    # Check for severe hallucination patterns
    found_severe = [p for p in SEVERE_HALLUCINATION_PATTERNS if p in response_lower]

    if found_severe:
        severity = "severe"
    elif found_garbage:
        severity = "minor"
    else:
        severity = "none"

    all_patterns = found_garbage + found_severe
    is_valid = len(all_patterns) == 0

    return is_valid, all_patterns, severity


def extract_garbage_context(response: str, patterns: List[str], context_chars: int = 100) -> List[dict]:
    """
    Extract context around garbage patterns for logging/debugging.

    Args:
        response: The full response text
        patterns: List of garbage patterns found
        context_chars: Number of characters to show before/after pattern

    Returns:
        List of dicts with pattern, position, and context
    """
    results = []
    response_lower = response.lower()

    for pattern in patterns:
        idx = response_lower.find(pattern)
        if idx != -1:
            start = max(0, idx - context_chars)
            end = min(len(response), idx + len(pattern) + context_chars)
            context = response[start:end]

            results.append({
                "pattern": pattern,
                "position": idx,
                "context": f"...{context}...",
            })

    return results


def clean_response_sentences(response: str, patterns: List[str]) -> str:
    """
    Remove sentences containing garbage patterns.

    This is a conservative approach: remove entire sentences that contain
    garbage text rather than trying to edit them.

    Args:
        response: The full response text
        patterns: List of garbage patterns to filter

    Returns:
        Cleaned response with garbage sentences removed
    """
    # Split into sentences (simple approach - could be improved)
    sentences = response.split('.')

    cleaned_sentences = []
    removed_count = 0

    for sentence in sentences:
        sentence_lower = sentence.lower()
        has_garbage = any(p in sentence_lower for p in patterns)

        if not has_garbage:
            cleaned_sentences.append(sentence)
        else:
            removed_count += 1
            logger.warning(f"Removed sentence with garbage: {sentence[:100]}...")

    if removed_count > 0:
        logger.info(f"Removed {removed_count} sentences containing garbage patterns")

    # Rejoin sentences
    cleaned = '.'.join(cleaned_sentences)

    # Clean up any double periods or spacing issues
    cleaned = cleaned.replace('..', '.').replace('  ', ' ').strip()

    return cleaned


def validate_and_clean(response: str, strict: bool = False) -> Tuple[bool, str, dict]:
    """
    Validate response and optionally clean it.

    Args:
        response: The LLM-generated response
        strict: If True, reject responses with any garbage.
                If False, attempt to clean by removing sentences.

    Returns:
        Tuple of (is_valid, cleaned_response, metadata)
        - is_valid: True if response is acceptable (clean or successfully cleaned)
        - cleaned_response: Original response or cleaned version
        - metadata: Dict with validation info (patterns found, severity, etc.)
    """
    is_valid, patterns, severity = validate_response(response)

    metadata = {
        "original_valid": is_valid,
        "patterns_found": patterns,
        "severity": severity,
        "cleaned": False,
    }

    # If valid, return as-is
    if is_valid:
        return True, response, metadata

    # If garbage found and strict mode, reject
    if strict:
        logger.warning(f"Response rejected (strict mode): found {len(patterns)} garbage patterns")
        return False, response, metadata

    # Attempt to clean by removing sentences
    cleaned = clean_response_sentences(response, patterns)

    # Re-validate cleaned response
    is_clean_valid, remaining_patterns, clean_severity = validate_response(cleaned)

    metadata["cleaned"] = True
    metadata["patterns_remaining"] = remaining_patterns
    metadata["clean_severity"] = clean_severity

    if is_clean_valid:
        logger.info(f"Successfully cleaned response: removed {len(patterns)} patterns")
        return True, cleaned, metadata
    else:
        logger.warning(f"Cleaning failed: {len(remaining_patterns)} patterns remain")
        return False, cleaned, metadata


def get_validation_stats() -> dict:
    """
    Get statistics on validation (for metrics/monitoring).

    This is a placeholder for future implementation of validation metrics.
    Could track: total validations, rejection rate, cleaning success rate, etc.
    """
    return {
        "total_validations": 0,
        "rejections": 0,
        "cleanings": 0,
        "rejection_rate": 0.0,
    }
