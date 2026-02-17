"""
Debug script to trace garbage text in responses.

Traces through pipeline for failing query to identify where irrelevant text comes from.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import get_pipeline

def trace_query(query: str):
    """Trace pipeline execution for a query."""
    print("=" * 80)
    print(f"TRACING QUERY: {query}")
    print("=" * 80)

    pipeline = get_pipeline()
    result = pipeline.process(query)

    print("\n📊 RESULT OVERVIEW:")
    print(f"  Is medical: {result.is_medical}")
    print(f"  Is red flag: {result.is_red_flag}")
    print(f"  Selected products: {len(result.selected_products) if hasattr(result, 'selected_products') and result.selected_products else 0}")
    print(f"  Candidate products: {len(result.candidate_products) if hasattr(result, 'candidate_products') and result.candidate_products else 0}")

    # Check for garbage text patterns
    garbage_patterns = [
        "защита на личните",
        "средство за защита",
        "зъбни протези",
        "грижа за зъбни протези",
        "репелент",
        "комар"
    ]

    response_lower = result.response.lower()
    found_garbage = [p for p in garbage_patterns if p in response_lower]

    if found_garbage:
        print(f"\n🚨 GARBAGE DETECTED: {found_garbage}")
    else:
        print("\n✅ NO GARBAGE DETECTED")

    # Show selected products
    if hasattr(result, 'selected_products') and result.selected_products:
        print("\n🛒 SELECTED PRODUCTS:")
        for i, prod in enumerate(result.selected_products[:5], 1):
            if isinstance(prod, dict):
                title = prod.get('title', 'Unknown')
                category = prod.get('category', 'Unknown')
                print(f"  {i}. {title}")
                print(f"     Category: {category}")
            else:
                print(f"  {i}. {prod.title if hasattr(prod, 'title') else str(prod)[:100]}")
                if hasattr(prod, 'category'):
                    print(f"     Category: {prod.category}")

    # Show candidate products (from vector search)
    if hasattr(result, 'candidate_products') and result.candidate_products:
        print("\n🔍 CANDIDATE PRODUCTS (from vector search):")
        for i, prod in enumerate(result.candidate_products[:10], 1):
            if isinstance(prod, dict):
                title = prod.get('title', 'Unknown')
                category = prod.get('category', 'Unknown')
                print(f"  {i}. {title}")
                print(f"     Category: {category}")
                # Check if this product contains garbage
                title_lower = title.lower()
                if any(g in title_lower for g in garbage_patterns):
                    print(f"     ⚠️  GARBAGE IN TITLE")
            else:
                print(f"  {i}. {prod.title if hasattr(prod, 'title') else str(prod)[:100]}")

    # Show response excerpt
    print("\n📝 RESPONSE EXCERPT (first 500 chars):")
    print(result.response[:500])
    print("...")

    # Search for garbage in response
    if found_garbage:
        print("\n🔎 GARBAGE TEXT CONTEXT:")
        for pattern in found_garbage:
            idx = response_lower.find(pattern)
            if idx != -1:
                start = max(0, idx - 50)
                end = min(len(result.response), idx + len(pattern) + 50)
                context = result.response[start:end]
                print(f"\n  Pattern: '{pattern}'")
                print(f"  Context: ...{context}...")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    # Critical failing queries
    failing_queries = [
        "Имам температура 38 градуса",
        "Имам болка в ухото при дете.",
        "Какво да направя при ларингит?",
    ]

    for query in failing_queries:
        trace_query(query)
        print("\n" * 2)
