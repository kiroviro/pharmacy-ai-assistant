"""
Performance investigation script to identify 49-second outlier bottlenecks.

Usage:
    python scripts/investigate_performance.py

This script:
1. Runs test queries through the pipeline with detailed timing
2. Identifies which stage(s) cause slowdowns
3. Generates a performance report
"""

import time
import json
from pathlib import Path

from src.pipeline import get_pipeline
from src.logging_config import get_logger

logger = get_logger("performance_investigation")


# Test queries that might be slow
TEST_QUERIES = [
    # Simple queries (should be fast)
    "главоболие",
    "имам температура",
    "болка в гърлото",

    # Complex queries (might be slower)
    "Имам силно главоболие, температура 38 градуса, болки в мускулите и общо неразположение от 3 дни",
    "Детето ми на 5 години има кашлица, хрема и леко повишена температура. Какво да му дам?",
    "Имам хронични болки в ставите, особено в коленете и китките. Болката е по-силна сутрин.",

    # Edge cases
    "аспирин",  # Single drug name
    "парацетамол или ибупрофен",  # Comparison
    "какво имате за настинка",  # Catalog query
]


def measure_pipeline_timing(query: str) -> dict:
    """
    Run a query through the pipeline and extract detailed timing.

    Returns dict with:
        - query: the input query
        - total_ms: total response time
        - timings: dict of per-stage timings
        - response_length: character count of response
    """
    pipeline = get_pipeline()

    start = time.perf_counter()
    result = pipeline.process(query)
    total_ms = (time.perf_counter() - start) * 1000

    # Extract timing data from logs or result
    # Our Week 1 instrumentation logs timings, but they're in logs
    # For now, just measure total time

    return {
        "query": query,
        "total_ms": round(total_ms, 2),
        "response_length": len(result.response) if result.response else 0,
        "is_medical": result.is_medical,
        "is_red_flag": result.is_red_flag,
        "products_found": len(result.selected_products) if hasattr(result, 'selected_products') else 0,
    }


def run_investigation():
    """Run performance investigation on test queries."""
    print("=" * 80)
    print("PERFORMANCE INVESTIGATION - 49s Outlier Analysis")
    print("=" * 80)
    print()

    results = []

    for i, query in enumerate(TEST_QUERIES, 1):
        print(f"\n[{i}/{len(TEST_QUERIES)}] Testing: {query[:60]}...")

        # Run query 3 times to account for variance
        timings = []
        for run in range(3):
            result = measure_pipeline_timing(query)
            timings.append(result['total_ms'])
            print(f"  Run {run+1}: {result['total_ms']:.0f}ms")

        # Use median to avoid outliers in measurement
        median_ms = sorted(timings)[1]
        result = measure_pipeline_timing(query)
        result['median_ms'] = median_ms
        result['min_ms'] = min(timings)
        result['max_ms'] = max(timings)

        results.append(result)

        # Warn if slow
        if median_ms > 10000:
            print(f"  ⚠️  SLOW: {median_ms/1000:.1f}s")
        elif median_ms > 5000:
            print(f"  ⚠️  Moderate: {median_ms/1000:.1f}s")
        else:
            print(f"  ✅ Fast: {median_ms/1000:.1f}s")

    # Analysis
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    # Sort by median time
    results.sort(key=lambda x: x['median_ms'], reverse=True)

    print("\nSlowest queries:")
    for r in results[:5]:
        print(f"  {r['median_ms']/1000:.1f}s - {r['query'][:60]}")

    print("\nFastest queries:")
    for r in results[-5:]:
        print(f"  {r['median_ms']/1000:.1f}s - {r['query'][:60]}")

    # Statistics
    all_times = [r['median_ms'] for r in results]
    print(f"\nStatistics:")
    print(f"  Average: {sum(all_times)/len(all_times)/1000:.1f}s")
    print(f"  Min: {min(all_times)/1000:.1f}s")
    print(f"  Max: {max(all_times)/1000:.1f}s")
    print(f"  P95: {sorted(all_times)[int(len(all_times)*0.95)]/1000:.1f}s")

    # Save results
    output_path = Path("output/performance_investigation.json")
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": time.time(),
            "results": results,
            "statistics": {
                "avg_ms": sum(all_times)/len(all_times),
                "min_ms": min(all_times),
                "max_ms": max(all_times),
                "p95_ms": sorted(all_times)[int(len(all_times)*0.95)],
            }
        }, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_path}")

    # Recommendations
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)

    max_time = max(all_times)
    if max_time > 10000:
        print("\n⚠️  CRITICAL: Queries taking >10s detected")
        print("\nLikely causes:")
        print("  1. MedGemma inference slow (cold start or complex query)")
        print("  2. ChromaDB vector search timing out")
        print("  3. Translation model slow on long text")
        print("\nNext steps:")
        print("  1. Check logs for detailed per-stage timing (Week 1 instrumentation)")
        print("  2. Profile specific slow query with line-level profiler")
        print("  3. Consider:")
        print("     - Model quantization (4-bit MedGemma)")
        print("     - Caching aggressive for common queries")
        print("     - Timeout on vector search (fallback to keyword search)")
    else:
        print("\n✅ Performance acceptable (<10s)")

    return results


if __name__ == "__main__":
    results = run_investigation()
