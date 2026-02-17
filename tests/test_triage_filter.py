"""
Unit test for triage garbage filtering (Issue #17).

Tests that LLM-generated triage warnings containing garbage patterns
are correctly filtered out before being shown to users.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import get_pipeline


def test_triage_garbage_filtering():
    """Test that garbage patterns in triage warnings are filtered out."""
    print("=" * 80)
    print("TEST: Triage Garbage Filtering (Issue #17)")
    print("=" * 80)

    pipeline = get_pipeline()

    # Test cases: queries that previously had garbage in triage section
    test_cases = [
        {
            "query": "Какво да направя при ларингит?",
            "forbidden_patterns": [
                "зъбні протези",
                "грижа за зъбні протези",
                "пластмасов",
                "ламарин",
                "металокерамика",
            ],
            "description": "Laryngitis query should not mention dental prosthetics"
        },
        {
            "query": "Имам сърбеж по кожата без обрив.",
            "forbidden_patterns": [
                "зъбні протези",
                "защита на личните",
                "средство за защита",
            ],
            "description": "Itching query should not mention dental or data protection"
        },
        {
            "query": "Какво да използвам при стрии?",
            "forbidden_patterns": [
                "зъбні протези",
                "репелент",
                "комар",
            ],
            "description": "Stretch marks query should not mention dental or mosquito repellent"
        },
    ]

    all_passed = True
    results = []

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*80}")
        print(f"Test Case {i}: {test_case['description']}")
        print(f"Query: \"{test_case['query']}\"")
        print('-' * 80)

        result = pipeline.process(test_case['query'])

        # Extract triage section
        triage_bullets = []
        lines = result.response.split('\n')
        in_triage = False
        for line in lines:
            if "⚠️ Потърсете лекар ако:" in line:
                in_triage = True
            elif in_triage:
                if line.startswith("##"):
                    break
                if line.startswith("•"):
                    triage_bullets.append(line)

        print(f"\nTriage bullets found: {len(triage_bullets)}")
        for bullet in triage_bullets:
            print(f"  • {bullet[2:]}")  # Remove leading "• "

        # Check for forbidden patterns
        response_lower = result.response.lower()
        found_forbidden = []
        for pattern in test_case['forbidden_patterns']:
            if pattern in response_lower:
                found_forbidden.append(pattern)

        # Evaluate
        passed = len(found_forbidden) == 0
        if passed:
            print("\n✅ PASS: No forbidden patterns found")
            status = "PASS"
        else:
            print(f"\n❌ FAIL: Found forbidden patterns: {found_forbidden}")
            all_passed = False
            status = "FAIL"

        results.append({
            "query": test_case['query'],
            "status": status,
            "forbidden_found": found_forbidden,
        })

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    passed_count = sum(1 for r in results if r['status'] == 'PASS')
    total_count = len(results)
    print(f"\nResults: {passed_count}/{total_count} tests passed")

    for i, result in enumerate(results, 1):
        status_icon = "✅" if result['status'] == 'PASS' else "❌"
        print(f"{status_icon} Test {i}: {result['status']}")
        if result['forbidden_found']:
            print(f"   Found: {result['forbidden_found']}")

    print("\n" + "=" * 80)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("Triage garbage filtering is working correctly!")
    else:
        print("❌ SOME TESTS FAILED")
        print("Garbage patterns are still appearing in triage sections.")
    print("=" * 80)

    return all_passed

if __name__ == "__main__":
    success = test_triage_garbage_filtering()
    sys.exit(0 if success else 1)
