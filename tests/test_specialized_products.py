"""
Test specialized product detection and helpful messaging.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import get_pipeline


def test_atopic_skin_query():
    """Test that atopic skin query gets helpful message about missing specialized products."""
    print("=" * 80)
    print("TEST: Specialized Product Detection - Atopic Skin")
    print("=" * 80)

    pipeline = get_pipeline()

    # Query that should trigger specialized detection
    query = "Имате ли крем за атопична кожа?"

    print(f"\nQuery: {query}\n")

    result = pipeline.process(query)

    print("Response:")
    print("-" * 80)
    print(result.response)
    print("-" * 80)

    # Check for key elements
    checks = {
        "Has specialized condition notice": "атопична кожа / атопичен дерматит" in result.response,
        "Has explanation": "Атопичният дерматит" in result.response,
        "Has recommendations": "Lipikar" in result.response or "Eucerin" in result.response,
        "Has fallback advice": "Препоръчани специализирани продукти" in result.response,
        "Has alternatives header": "Алтернативи в наличност" in result.response,
        "Has dermatologist recommendation": "дерматолог" in result.response.lower(),
    }

    print("\nChecks:")
    all_passed = True
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {check}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print("✅ ALL CHECKS PASSED")
        print("Specialized product detection working correctly!")
    else:
        print("❌ SOME CHECKS FAILED")
        print("Review response above for issues.")
    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    success = test_atopic_skin_query()
    sys.exit(0 if success else 1)
