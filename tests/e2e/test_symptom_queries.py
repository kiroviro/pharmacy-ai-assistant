"""
E2E tests for symptom-related queries.
Tests symptom descriptions, pregnancy queries, and complex multi-symptom scenarios.
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

# Symptom queries (83 symptoms + 3 pregnancy + 3 complex = 89 total)
TEST_QUERIES = {
    "symptoms": [
        "Боли ме главата от сутринта",
        "Имам хрема и кихам много",
        "Имам температура 38 градуса",
        "Чувствам се уморен и ми се вие свят",
        "Боли ме коремът след ядене",
        # Симптоми и препоръки (expanded)
        "Имам температура 38.5 – какво да взема?",
        "Какво препоръчвате при суха кашлица?",
        "Имам запушен нос и главоболие – какво да пия?",
        "Какво да взема при болки в гърлото?",
        "Имам разстройство от вчера – какво да направя?",
        "Какво е подходящо при стомашни киселини?",
        "Какво мога да пия при мускулни болки?",
        "Имам обрив по кожата – какво препоръчвате?",
        "Какво да взема при силна менструална болка?",
        "Имам безсъние – има ли нещо без рецепта?",
        "Какво помага при световъртеж?",
        "Какво се дава при хранително натравяне?",
        "Имам болки в ушите – какво да направя?",
        "Какво препоръчвате при алергия към полени?",
        "Имам високо кръвно и главоболие – какво да взема?",
        # Extended symptom queries (61–120)
        "Имам втрисане и болки в тялото – какво да взема?",
        "Какво препоръчвате при постоянна кашлица?",
        "Имам болки в корема от няколко дни.",
        "Какво да направя при загуба на глас?",
        "Имам сухота в устата.",
        "Какво се дава при киселини вечер?",
        "Имам болки в ставите сутрин.",
        "Какво препоръчвате при запек при възрастен човек?",
        "Имам сърбеж по кожата без обрив.",
        "Какво да взема при вирус?",
        "Имам болка в гърдите при кашляне.",
        "Какво помага при херпес?",
        "Имам подути лимфни възли.",
        "Какво да направя при слънчево изгаряне?",
        "Имам проблем със съня от седмица.",
        "Какво да взема при паник атака?",
        "Имам шум в ушите.",
        "Какво се препоръчва при ниско кръвно?",
        "Имам постоянна умора.",
        "Какво помага при газове?",
        "Имам болки в коляното.",
        "Какво да взема при силна хрема?",
        "Имам суха кожа и напуквания.",
        "Какво препоръчвате при често главоболие?",
        "Имам раздразнено гърло.",
        "Какво да направя при кървящи венци?",
        "Имам стягане в гърдите.",
        "Какво да взема при гадене при пътуване?",
        "Имам болки в рамото.",
        "Какво помага при нервност?",
        "Имам обрив след нов крем.",
        "Какво да взема при болки в синусите?",
        "Имам температура при дете.",
        "Какво се дава при хранително разстройство?",
        "Имам суха кашлица нощем.",
        "Какво помага при зачервени очи?",
        "Имам изтръпване на ръцете.",
        "Какво да направя при алергична реакция?",
        "Имам болки в гърба.",
        "Какво да взема при афти?",
        "Имам чести настинки.",
        "Какво препоръчвате при липса на апетит?",
        "Имам спазми в стомаха.",
        "Какво да направя при висока температура 39.5?",
        "Имам болка при преглъщане.",
        "Какво помага при раздразнени очи от компютър?",
        "Имам кашлица повече от 2 седмици.",
        "Какво да направя при силна мигрена?",
        "Имам болка в ухото при дете.",
        "Какво препоръчвате при нервно напрежение?",
        "Имам проблем с концентрацията.",
        "Какво да взема при тежест в стомаха?",
        "Имам болка в глезена.",
        "Какво помага при изпотяване нощем?",
        "Имам суха кашлица и температура.",
        "Какво да направя при подут глезен?",
        "Имам обрив след антибиотик.",
        "Какво се препоръчва при храносмилателни проблеми?",
        "Имам болки в ръката.",
        "Какво да направя при световъртеж?",
    ],
    "pregnancy": [
        "Бременна съм и ме боли главата",
        "Имам настинка, но съм бременна в 3-ти месец",
        "Кърмя и имам болки в гърлото",
    ],
    "complex": [
        "Имам кашлица, хрема и температура от 2 дни",
        "Боли ме гърлото, имам главоболие и съм без сили",
        "Имам стомашни болки, гадене и диария",
    ],
}


def run_all_tests():
    """Run all symptom query tests and collect results."""
    all_results = []
    total_queries = sum(len(queries) for queries in TEST_QUERIES.values())
    current = 0

    catalog_titles = load_catalog_titles()
    print(f"\nCatalog: {len(catalog_titles)} product titles loaded from output/products_*.csv")
    print(f"\n{'='*80}")
    print(f"E2E SYMPTOM QUERY TESTS - {total_queries} QUERIES")
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
    print(f"Starting symptom query tests at {datetime.now().isoformat()}\n")
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

    print("Running symptom query tests...\n")
    results = run_all_tests()
    report = generate_report(results)
    print_report(report)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "test_results_symptoms.json"

    output = {
        "timestamp": datetime.now().isoformat(),
        "test_category": "symptoms",
        "report": report,
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Detailed results saved to: {output_file}")
    print(f"\n✅ Symptom query test suite completed!")


if __name__ == "__main__":
    main()
