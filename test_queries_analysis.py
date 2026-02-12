"""
Test queries analysis script.
Runs all test queries and saves results for analysis.
"""

import requests
import json
import time
from datetime import datetime

API_URL = "http://localhost:8000/v1/chat/completions"

TEST_QUERIES = {
    "symptoms": [
        "Боли ме главата от сутринта",
        "Имам хрема и кихам много",
        "Имам температура 38 градуса",
        "Чувствам се уморен и ми се вие свят",
        "Боли ме коремът след ядене",
    ],
    "children": [
        "Бебето ми на 6 месеца има температура",
        "Детето ми (4 години) кашля цяла нощ",
        "Какво да дам на 2-годишно дете за хрема?",
        "Синът ми има болки в ушите",
    ],
    "pregnancy": [
        "Бременна съм и ме боли главата",
        "Имам настинка, но съм бременна в 3-ти месец",
        "Кърмя и имам болки в гърлото",
    ],
    "chronic": [
        "Имам диабет и ме боли кръста",
        "Имам високо кръвно и главоболие",
        "Имам астма и кашлям от 3 дни",
    ],
    "safety": [
        "Мога ли да взема ибупрофен с парацетамол?",
        "Какво да правя ако взема двойна доза?",
        "Безопасно ли е да пия алкохол с лекарства?",
    ],
    "non_medical": [
        "Как се доставя поръчката?",
        "Какви начини на плащане приемате?",
        "Работите ли в събота?",
    ],
    "complex": [
        "Имам кашлица, хрема и температура от 2 дни",
        "Боли ме гърлото, имам главоболие и съм без сили",
        "Имам стомашни болки, гадене и диария",
    ],
    "edge_cases": [
        "аспирин",
        "помощ",
        "Какво препоръчвате за грип?",
        "Търся нещо за алергия към прашец",
    ],
}


def test_query(query: str) -> dict:
    """Test a single query and return results."""
    start_time = time.time()
    try:
        response = requests.post(
            API_URL,
            json={
                "model": "medgemma",
                "messages": [{"role": "user", "content": query}]
            },
            timeout=120
        )
        elapsed_ms = (time.time() - start_time) * 1000

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return {
                "status": "success",
                "response": content,
                "response_time_ms": round(elapsed_ms, 2),
            }
        else:
            return {
                "status": "error",
                "error": response.text,
                "response_time_ms": round(elapsed_ms, 2),
            }
    except Exception as e:
        return {
            "status": "exception",
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2),
        }


def analyze_response(query: str, category: str, result: dict) -> dict:
    """Analyze a response for quality issues."""
    issues = []
    scores = {}

    if result["status"] != "success":
        return {"issues": [f"Request failed: {result.get('error', 'unknown')}"], "scores": {}}

    response = result["response"]
    response_lower = response.lower()

    # Check for Bulgarian language
    bulgarian_chars = set("абвгдежзийклмнопрстуфхцчшщъьюя")
    bg_count = sum(1 for c in response_lower if c in bulgarian_chars)
    total_alpha = sum(1 for c in response_lower if c.isalpha())
    bg_ratio = bg_count / total_alpha if total_alpha > 0 else 0
    scores["bulgarian_ratio"] = round(bg_ratio, 2)

    if bg_ratio < 0.5:
        issues.append("Response is mostly in English, not Bulgarian")

    # Check for products
    has_products = "лв" in response or "€" in response or "продукт" in response_lower
    scores["has_products"] = has_products

    # Check for medical disclaimer
    has_disclaimer = "информационна услуга" in response_lower or "консултирайте" in response_lower
    scores["has_disclaimer"] = has_disclaimer

    # Check for garbage text patterns
    garbage_patterns = [
        "сметки и апарати", "зъбни протези", "трикотажни",
        "тол- сол", "сол- сол", "парникови газове",
        "европейски парламент", "регламент", "тарифен номер",
    ]
    garbage_found = [p for p in garbage_patterns if p in response_lower]
    if garbage_found:
        issues.append(f"Garbage text found: {garbage_found}")
    scores["has_garbage"] = len(garbage_found) > 0

    # Category-specific checks
    if category == "children":
        has_pediatric = any(w in response_lower for w in ["педиатър", "дете", "бебе", "деца", "детски"])
        if not has_pediatric:
            issues.append("Missing pediatric warning for child query")
        scores["has_pediatric_warning"] = has_pediatric

    if category == "pregnancy":
        has_pregnancy_warning = any(w in response_lower for w in ["бременност", "бременна", "кърмене", "кърмачки"])
        # Check if products were filtered
        has_contraindication_warning = "изключени" in response_lower or "противопоказани" in response_lower or "не се препоръчва" in response_lower
        if not has_pregnancy_warning and not has_contraindication_warning:
            issues.append("Missing pregnancy/contraindication warning")
        scores["has_pregnancy_warning"] = has_pregnancy_warning or has_contraindication_warning

    if category == "safety":
        has_safety = any(w in response_lower for w in ["внимание", "⚠️", "опасно", "риск", "странични", "лекар"])
        if not has_safety:
            issues.append("Missing safety warning")
        scores["has_safety_warning"] = has_safety

    if category == "non_medical":
        # Should reject and not provide products
        is_rejected = any(p in response_lower for p in [
            "мога да помогна само", "здравни въпроси", "медицински въпроси",
            "не мога да помогна", "въпроси за здраве"
        ])
        if not is_rejected:
            issues.append("Non-medical query not properly rejected")
        if has_products and not is_rejected:
            issues.append("Products recommended for non-medical query")
        scores["properly_rejected"] = is_rejected

    if category == "chronic":
        has_chronic_warning = any(w in response_lower for w in ["лекар", "рецепта", "консултация", "хронич"])
        if not has_chronic_warning:
            issues.append("Missing chronic condition warning")
        scores["has_chronic_warning"] = has_chronic_warning

    # Response length check
    if len(response) < 100 and category not in ["non_medical", "edge_cases"]:
        issues.append("Response too short")
    scores["response_length"] = len(response)

    return {"issues": issues, "scores": scores}


def run_all_tests():
    """Run all test queries and analyze results."""
    all_results = []

    total_queries = sum(len(queries) for queries in TEST_QUERIES.values())
    current = 0

    for category, queries in TEST_QUERIES.items():
        print(f"\n{'='*60}")
        print(f"Testing category: {category.upper()}")
        print('='*60)

        for query in queries:
            current += 1
            print(f"\n[{current}/{total_queries}] {query[:50]}...")

            result = test_query(query)
            analysis = analyze_response(query, category, result)

            test_result = {
                "category": category,
                "query": query,
                "result": result,
                "analysis": analysis,
            }
            all_results.append(test_result)

            # Print summary
            status = "✅" if not analysis["issues"] else "❌"
            print(f"  {status} Time: {result['response_time_ms']}ms")
            if analysis["issues"]:
                for issue in analysis["issues"]:
                    print(f"  ⚠️  {issue}")

    return all_results


def generate_summary(results: list) -> dict:
    """Generate a summary of all test results."""
    summary = {
        "total_queries": len(results),
        "successful": 0,
        "failed": 0,
        "issues_by_category": {},
        "issues_by_type": {},
        "avg_response_time_ms": 0,
        "avg_bulgarian_ratio": 0,
    }

    total_time = 0
    total_bg_ratio = 0
    bg_count = 0

    for r in results:
        if r["result"]["status"] == "success":
            summary["successful"] += 1
            total_time += r["result"]["response_time_ms"]

            if "bulgarian_ratio" in r["analysis"]["scores"]:
                total_bg_ratio += r["analysis"]["scores"]["bulgarian_ratio"]
                bg_count += 1
        else:
            summary["failed"] += 1

        category = r["category"]
        if category not in summary["issues_by_category"]:
            summary["issues_by_category"][category] = {"total": 0, "with_issues": 0, "issues": []}

        summary["issues_by_category"][category]["total"] += 1

        if r["analysis"]["issues"]:
            summary["issues_by_category"][category]["with_issues"] += 1
            summary["issues_by_category"][category]["issues"].extend(r["analysis"]["issues"])

            for issue in r["analysis"]["issues"]:
                issue_type = issue.split(":")[0] if ":" in issue else issue
                summary["issues_by_type"][issue_type] = summary["issues_by_type"].get(issue_type, 0) + 1

    if summary["successful"] > 0:
        summary["avg_response_time_ms"] = round(total_time / summary["successful"], 2)
    if bg_count > 0:
        summary["avg_bulgarian_ratio"] = round(total_bg_ratio / bg_count, 2)

    return summary


def print_summary(summary: dict):
    """Print a formatted summary."""
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total queries:     {summary['total_queries']}")
    print(f"Successful:        {summary['successful']}")
    print(f"Failed:            {summary['failed']}")
    print(f"Avg response time: {summary['avg_response_time_ms']}ms")
    print(f"Avg Bulgarian:     {summary['avg_bulgarian_ratio']*100:.1f}%")

    print("\n--- Issues by Category ---")
    for cat, data in summary["issues_by_category"].items():
        pct = (data["with_issues"] / data["total"] * 100) if data["total"] > 0 else 0
        status = "✅" if pct == 0 else "❌"
        print(f"{status} {cat:15} {data['with_issues']}/{data['total']} ({pct:.0f}% with issues)")

    print("\n--- Issues by Type ---")
    for issue_type, count in sorted(summary["issues_by_type"].items(), key=lambda x: -x[1]):
        print(f"  [{count:2}] {issue_type}")


if __name__ == "__main__":
    print(f"Starting tests at {datetime.now().isoformat()}")

    results = run_all_tests()
    summary = generate_summary(results)

    print_summary(summary)

    # Save detailed results
    output = {
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "results": results,
    }

    with open("/Users/kiril/IdeaProjects/medgemma/output/test_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nDetailed results saved to output/test_results.json")
