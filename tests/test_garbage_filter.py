"""
Quick unit test to verify garbage pattern filtering works.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import get_pipeline


def test_garbage_detection():
    """Test that garbage patterns are detected."""
    pipeline = get_pipeline()

    # Test texts with garbage patterns
    test_cases = [
        {
            "text": "Това е лекарство за температура. Те могат да бъдат използвани като средство за защита на личните данни.",
            "should_contain_garbage": True,
            "pattern": "защита на личните",
        },
        {
            "text": "Препоръчвам парацетамол. Също има зъбні протези в аптеката.",
            "should_contain_garbage": True,
            "pattern": "зъбні протези",
        },
        {
            "text": "За температура е добре да вземете ибупрофен. Репелент за комари.",
            "should_contain_garbage": True,
            "pattern": "репелент",
        },
        {
            "text": "За температура е добре да вземете ибупрофен. Пийте много течности.",
            "should_contain_garbage": False,
            "pattern": None,
        },
    ]

    print("Testing garbage pattern detection:\n")
    for i, test in enumerate(test_cases, 1):
        contains_garbage = pipeline.text_validator.contains_garbage(test["text"])
        expected = test["should_contain_garbage"]

        status = "✅ PASS" if contains_garbage == expected else "❌ FAIL"
        print(f"{status} Test {i}:")
        print(f"  Text: {test['text'][:60]}...")
        print(f"  Pattern: {test['pattern']}")
        print(f"  Expected garbage: {expected}, Got: {contains_garbage}\n")

        if contains_garbage != expected:
            print(f"  ⚠️  FAILED: Expected {expected}, got {contains_garbage}")
            return False

    print("=" * 80)
    print("All tests passed! Garbage detection working correctly.")
    return True


if __name__ == "__main__":
    success = test_garbage_detection()
    sys.exit(0 if success else 1)
