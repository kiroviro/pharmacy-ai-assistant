"""
E2E tests for medication-related queries.
Tests availability questions, dosing questions, medication comparison, and safety.
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

# Medication queries (77 total)
TEST_QUERIES = {
    "medications": [
        "Имате ли наличен Парацетамол 500 мг?",
        "Трябва ли рецепта за антибиотик?",
        "Имате ли генеричен заместител на Аулин?",
        "Кое е по-силно – Ибупрофен или Диклофенак?",
        "Мога ли да комбинирам два различни обезболяващи?",
        "Колко дни може да се пие Нурофен?",
        "Имате ли прахчета за грип?",
        "Каква е максималната дневна доза парацетамол?",
        "Имате ли нещо за силна зъбобол?",
        "Мога ли да взема антибиотик без консултация с лекар?",
        "Това лекарство подходящо ли е за възрастен човек?",
        "Имате ли лекарства против повръщане?",
        "Мога ли да пия алкохол, докато приемам антибиотик?",
        "Имате ли нещо по-силно от аналгин?",
        "Колко време се приема пробиотик?",
        # Extended medication queries (1–60)
        "Имате ли наличен Ибупрофен 400 мг?",
        "Кое лекарство действа най-бързо при главоболие?",
        "Имате ли прахчета за настинка без захар?",
        "Мога ли да пия аналгин при ниско кръвно?",
        "Колко време се пие антибиотик при ангина?",
        "Имате ли спрей за болно гърло?",
        "Може ли парацетамол при проблеми с черния дроб?",
        "Имате ли капки против гадене?",
        "Кое лекарство е подходящо при мигрена?",
        "Мога ли да комбинирам антибиотик с пробиотик?",
        "Имате ли противовъзпалителен гел за стави?",
        "Кое е по-безопасно за стомаха – ибупрофен или аспирин?",
        "Имате ли таблетки за смучене при кашлица?",
        "Колко часа трябва да има между две дози?",
        "Имате ли нещо за висока температура над 39?",
        "Може ли лекарство за настинка при диабет?",
        "Имате ли лекарства без лактоза?",
        "Кое лекарство е подходящо при болки в кръста?",
        "Имате ли противогъбичен крем?",
        "Колко дни може да се ползва спрей за нос?",
        "Имате ли капки за очи при възпаление?",
        "Кое е подходящо при възпалени венци?",
        "Мога ли да пия обезболяващо на празен стомах?",
        "Имате ли лекарства против подуване?",
        "Кое е най-подходящо при синузит?",
        "Имате ли сироп за влажна кашлица?",
        "Колко време се приема витамин C?",
        "Имате ли таблетки против алергия?",
        "Мога ли да шофирам след това лекарство?",
        "Имате ли нещо за спазми?",
        "Кое лекарство е подходящо при нервно напрежение?",
        "Имате ли прах за рехидратация?",
        "Може ли това лекарство при язва?",
        "Имате ли таблетки за гърло без упойка?",
        "Кое е най-силното обезболяващо без рецепта?",
        "Имате ли антисептичен спрей?",
        "Колко време действа това лекарство?",
        "Може ли да се приема дългосрочно?",
        "Имате ли противовирусни препарати?",
        "Кое лекарство е подходящо при болки в ушите?",
        "Имате ли крем при изгаряне?",
        "Мога ли да взема двойна доза ако болката не минава?",
        "Имате ли лекарства за киселини?",
        "Кое е подходящо при подагра?",
        "Имате ли обезболяващи свещички?",
        "Колко бързо започва да действа?",
        "Имате ли лекарство против грип?",
        "Може ли това лекарство при бременност?",
        "Имате ли антихистамин без сънливост?",
        "Кое лекарство е подходящо при болки в мускулите?",
        "Имате ли таблетки за разреждане на кръвта?",
        "Може ли да се комбинира с витамини?",
        "Имате ли нещо при нервен стомах?",
        "Колко време след хранене се приема?",
        "Имате ли лекарства при запек?",
        "Кое е подходящо при диария?",
        "Имате ли противогрипна ваксина?",
        "Мога ли да приемам това лекарство вечер?",
        "Имате ли билкови лекарства за кашлица?",
        "Кое лекарство е най-щадящо за стомаха?",
    ],
}


def run_all_tests():
    """Run all medication query tests and collect results."""
    all_results = []
    total_queries = sum(len(queries) for queries in TEST_QUERIES.values())
    current = 0

    catalog_titles = load_catalog_titles()
    print(f"\nCatalog: {len(catalog_titles)} product titles loaded from output/products_*.csv")
    print(f"\n{'='*80}")
    print(f"E2E MEDICATION QUERY TESTS - {total_queries} QUERIES")
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
    print(f"Starting medication query tests at {datetime.now().isoformat()}\n")
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

    print("Running medication query tests...\n")
    results = run_all_tests()
    report = generate_report(results)
    print_report(report)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "test_results_medications.json"

    output = {
        "timestamp": datetime.now().isoformat(),
        "test_category": "medications",
        "report": report,
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Detailed results saved to: {output_file}")
    print(f"\n✅ Medication query test suite completed!")


if __name__ == "__main__":
    main()
