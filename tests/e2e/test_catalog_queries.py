"""
E2E tests for catalog-related queries.
Tests cosmetics/skincare products and chronic condition management queries.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# Import shared helpers
from e2e_helpers import (
    API_URL,
    OUTPUT_DIR,
    analyze_response,
    generate_report,
    load_catalog_titles,
    print_report,
    test_query,
)

# Catalog queries (38 cosmetics + 80 chronic = 118 total)
TEST_QUERIES = {
    "cosmetics": [
        "Имате ли крем за атопична кожа?",
        "Кой крем е подходящ при екзема?",
        "Имате ли медицинска козметика за акне?",
        "Кой слънцезащитен крем е подходящ за чувствителна кожа?",
        "Имате ли шампоан против косопад?",
        "Какво препоръчвате при суха и лющеща се кожа?",
        "Имате ли продукти против пигментни петна?",
        "Кой крем е подходящ за розацея?",
        "Имате ли дерматологично тествана козметика?",
        "Кое е най-доброто при напукани устни?",
        "Имате ли крем за диабетно стъпало?",
        "Какво препоръчвате за грижа след слънчево изгаряне?",
        "Имате ли продукти без аромат?",
        "Кой продукт е подходящ за мазна кожа?",
        "Имате ли натурална козметика?",
        # Extended cosmetics queries (171–190)
        "Имате ли крем за псориазис?",
        "Какво препоръчвате при диабетно стъпало?",
        "Имате ли хидратиращ серум?",
        "Кой крем е подходящ за зряла кожа?",
        "Имате ли продукти за розацея?",
        "Какво да използвам при мазна кожа?",
        "Имате ли шампоан при пърхот?",
        "Какво препоръчвате при косопад след раждане?",
        "Имате ли слънцезащита SPF 50?",
        "Какво е подходящо при тъмни кръгове?",
        "Имате ли крем без аромат?",
        "Какво да използвам при чувствителна кожа?",
        "Имате ли медицинска козметика?",
        "Кой продукт е подходящ при акне?",
        "Имате ли крем за ръце при екзема?",
        "Какво препоръчвате при сух скалп?",
        "Имате ли продукти с хиалуронова киселина?",
        "Какво да използвам при стрии?",
        "Имате ли крем за околоочен контур?",
        "Кой шампоан е без сулфати?",
    ],
    "chronic": [
        "Имам диабет и ме боли кръста",
        "Имам високо кръвно и главоболие",
        "Имам астма и кашлям от 3 дни",
        "Имате ли лекарства за диабет?",
        "Предлагате ли апарати за измерване на кръвна захар?",
        "Имате ли тест ленти за глюкомер?",
        "Как се приема лекарство за щитовидна жлеза?",
        "Мога ли да поръчам лекарства по рецепта онлайн?",
        "Имате ли лекарства за високо кръвно?",
        "Кое е подходящо при хроничен гастрит?",
        "Имате ли нещо за поддържане на стави?",
        "Мога ли да спра лекарството си ако се чувствам добре?",
        "Имате ли инхалатори за астма?",
        "Какво се препоръчва при хронична кашлица?",
        "Имате ли добавки при анемия?",
        "Кое е подходящо при остеопороза?",
        "Имате ли лекарства за сърце без рецепта?",
        "Мога ли да комбинирам лекарствата си с хранителни добавки?",
        # Extended chronic queries (191–250)
        "Какво да приема при анемия?",
        "Имате ли калций при остеопороза?",
        "Какво се дава при хроничен гастрит?",
        "Имате ли инсулин?",
        "Какво е подходящо при артрит?",
        "Имате ли лекарства за сърце?",
        "Какво да приема при проблеми с щитовидната жлеза?",
        "Имате ли тест ленти за диабет?",
        "Какво се препоръчва при висок холестерол?",
        "Имате ли апарат за кръвно?",
        "Какво да приема при хронична кашлица?",
        "Имате ли лекарства за астма?",
        "Какво се дава при подагра?",
        "Имате ли добавки при менопауза?",
        "Какво да приема при хронична умора?",
        "Имате ли лекарства за сърцебиене?",
        "Какво се препоръчва при разширени вени?",
        "Имате ли компресионни чорапи?",
        "Какво да приема при дефицит на желязо?",
        "Имате ли лекарства за панкреас?",
        "Какво се препоръчва при бъбречни проблеми?",
        "Имате ли омега-3 добавки?",
        "Какво да приема при висока кръвна захар?",
        "Имате ли инхалатори?",
        "Какво се препоръчва при хроничен бронхит?",
        "Имате ли лекарства за сърдечна недостатъчност?",
        "Какво да приема при нисък хемоглобин?",
        "Имате ли продукти за грижа при лежащо болни?",
        "Какво се препоръчва при невралгия?",
        "Имате ли добавки за памет?",
        "Какво да приема при остеоартрит?",
        "Имате ли крем за разширени капиляри?",
        "Какво се препоръчва при гастроезофагеален рефлукс?",
        "Имате ли лекарства за епилепсия?",
        "Какво да приема при хроничен синузит?",
        "Имате ли добавки с магнезий?",
        "Какво се препоръчва при високо пикочна киселина?",
        "Имате ли продукти за интимна хигиена?",
        "Какво да използвам при гъбична инфекция?",
        "Имате ли крем при хемороиди?",
        "Какво се препоръчва при раздразнено дебело черво?",
        "Имате ли витамини за възрастни хора?",
        "Какво да приема при проблеми със съня?",
        "Имате ли добавки за стави?",
        "Какво се препоръчва при нервно изтощение?",
        "Имате ли продукти без глутен?",
        "Какво да приема при чупливи нокти?",
        "Имате ли крем при дерматит?",
        "Какво се препоръчва при хронична болка?",
        "Имате ли колаген на таблетки?",
        "Какво да приема при дефицит на витамин D?",
        "Имате ли пробиотици за възрастни?",
        "Какво се препоръчва при чести инфекции?",
        "Имате ли хранителни добавки за сърце?",
        "Какво да приема при хормонален дисбаланс?",
        "Имате ли антибактериален сапун?",
        "Какво се препоръчва при хронична тревожност?",
        "Имате ли добавки за имунитет?",
        "Какво да приема при ставни болки при възрастен човек?",
    ],
}


def run_all_tests():
    """Run all catalog query tests and collect results."""
    all_results = []
    total_queries = sum(len(queries) for queries in TEST_QUERIES.values())
    current = 0

    catalog_titles = load_catalog_titles()
    print(f"\nCatalog: {len(catalog_titles)} product titles loaded from output/products_*.csv")
    print(f"\n{'='*80}")
    print(f"E2E CATALOG QUERY TESTS - {total_queries} QUERIES")
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
    print(f"Starting catalog query tests at {datetime.now().isoformat()}\n")
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

    print("Running catalog query tests...\n")
    results = run_all_tests()
    report = generate_report(results)
    print_report(report)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "test_results_catalog.json"

    output = {
        "timestamp": datetime.now().isoformat(),
        "test_category": "catalog",
        "report": report,
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Detailed results saved to: {output_file}")
    print(f"\n✅ Catalog query test suite completed!")


if __name__ == "__main__":
    main()
