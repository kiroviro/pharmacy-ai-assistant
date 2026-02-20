"""
E2E tests for edge cases and boundary conditions.
Tests minimal queries, non-medical queries, and unusual inputs.
"""

import json
import time
from datetime import datetime

import requests

# Import shared helpers
from e2e_helpers import (
    OUTPUT_DIR,
    analyze_response,
    generate_report,
    load_catalog_titles,
    print_report,
    test_query,
)

# Edge case queries (4 edge_cases + 3 non_medical = 7 total)
TEST_QUERIES = {
    "edge_cases": [
        "аспирин",
        "помощ",
        "Какво препоръчвате за грип?",
        "Търся нещо за алергия към прашец",
    ],
    "non_medical": [
        "Как се доставя поръчката?",
        "Какви начини на плащане приемате?",
        "Работите ли в събота?",
    ],
}


def run_all_tests():
    """Run all edge case query tests and collect results."""
    all_results = []
    total_queries = sum(len(queries) for queries in TEST_QUERIES.values())
    current = 0

    catalog_titles = load_catalog_titles()
    print(f"\nCatalog: {len(catalog_titles)} product titles loaded from output/products_*.csv")
    print(f"\n{'='*80}")
    print(f"E2E EDGE CASE QUERY TESTS - {total_queries} QUERIES")
    print(f"{'='*80}\n")

    for category, queries in TEST_QUERIES.items():
        print(f"\n{'='*80}")
        print(f"Category: {category.upper()} ({len(queries)} queries)")
        print('='*80)

        for query in queries:
            current += 1
            print(f"\n[{current}/{total_queries}] {query[:60]}{'...' if len(query) > 60 else ''}")

            result = test_query(query, category)
            analysis = analyze_response(result, catalog_titles=catalog_titles)

            test_result = {
                "query": query,
                "category": category,
                "result": result,
                "analysis": analysis,
            }
            all_results.append(test_result)

            severity = analysis["severity"]
            severity_icon = {
                "none": "✅",
                "low": "⚠️",
                "medium": "⚠️",
                "high": "❌",
                "critical": "🚨",
            }.get(severity, "❓")

            scores = analysis.get("scores", {})

            # Build status line
            parts = [f"Severity: {severity.upper()}", f"Time: {result['response_time_ms']}ms"]

            rel_checked = scores.get("product_relevance_checked")
            rel_ok = scores.get("product_relevance_ok")
            if rel_checked and "product_relevance_groups" in scores and scores["product_relevance_groups"]:
                parts.append(f"Relevance: {'✓' if rel_ok else '✗'}")

            # Template compliance summary
            if scores.get("has_products_section") is not None:
                tmpl_keys = ["has_symptom_header", "has_ingredients_section", "has_safety_block",
                             "has_products_section", "has_triage_section", "has_footer"]
                tmpl_ok = sum(1 for k in tmpl_keys if scores.get(k))
                parts.append(f"Template: {tmpl_ok}/{len(tmpl_keys)}")

            print(f"  {severity_icon} {' | '.join(parts)}")

            if analysis["issues"]:
                for issue in analysis["issues"]:
                    print(f"    🚨 {issue}")

            if analysis["warnings"]:
                for warning in analysis["warnings"]:
                    print(f"    ⚠️  {warning}")

            time.sleep(0.2)

    return all_results


def main():
    """Main entry point."""
    print(f"Starting edge case query tests at {datetime.now().isoformat()}\n")
    print("⚠️  Ensure API server is running (restart with: pkill -f api_server; python api_server.py)\n")

    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code != 200:
            print("❌ Server is not responding correctly. Please start the API server first.")
            return
    except Exception as e:
        print(f"❌ Cannot connect to API server: {e}")
        print("   Please start the server with: python api_server.py")
        return

    # Clear server caches
    print("Clearing server cache...")
    try:
        r = requests.post("http://localhost:8000/cache/clear", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"Cache cleared: {data.get('cleared', [])}\n")
        else:
            print("(Cache clear failed; continuing with existing cache)\n")
    except Exception as e:
        print(f"(Could not clear cache: {e}; continuing)\n")

    print("Running edge case query tests...\n")
    results = run_all_tests()
    report = generate_report(results)
    print_report(report)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "test_results_edge_cases.json"

    output = {
        "timestamp": datetime.now().isoformat(),
        "test_category": "edge_cases",
        "report": report,
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Detailed results saved to: {output_file}")
    print(f"\n✅ Edge case query test suite completed!")


if __name__ == "__main__":
    main()
