#!/usr/bin/env python3
"""
Analyze garbage text in responses from E2E test failures.

This script tests the 3 queries that failed with garbage text and
shows where the patterns appear in the responses.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline import get_pipeline

# The 3 queries that failed with garbage text
FAILING_QUERIES = [
    ("Имам болка в глезена.", ["лични данни"]),
    ("Каква е максималната дневна доза парацетамол?", ["зъбни протези"]),
    ("Какво препоръчвате при суха и лющеща се кожа?", ["лични данни"]),
]

def find_pattern_context(text: str, pattern: str, context_chars: int = 150) -> str:
    """Find pattern in text and return context around it."""
    text_lower = text.lower()
    idx = text_lower.find(pattern.lower())

    if idx == -1:
        return f"Pattern '{pattern}' not found"

    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(pattern) + context_chars)

    # Show where in the response it appears
    position_pct = (idx / len(text)) * 100

    return f"""
Position: {position_pct:.1f}% through response
Context: ...{text[start:end]}...
"""

def main():
    print("Loading pipeline...")
    pipeline = get_pipeline()

    print(f"\nTesting {len(FAILING_QUERIES)} queries that failed with garbage text\n")
    print("="* 80)

    for i, (query, expected_garbage) in enumerate(FAILING_QUERIES, 1):
        print(f"\n[{i}] Query: {query}")
        print(f"    Expected garbage: {expected_garbage}")

        # Process query
        result = pipeline.process(query)
        response = result.response
        response_lower = response.lower()

        # Check each garbage pattern
        found_any = False
        for pattern in expected_garbage:
            if pattern in response_lower:
                found_any = True
                print(f"\n    🚨 FOUND: '{pattern}'")
                print(find_pattern_context(response, pattern))

        if not found_any:
            print(f"    ✅ No garbage found - pattern may have been fixed!")

        print(f"\n    Response length: {len(response)} chars")
        print(f"    Products: {len(result.selected_products)}")
        print("-" * 80)

if __name__ == "__main__":
    main()
