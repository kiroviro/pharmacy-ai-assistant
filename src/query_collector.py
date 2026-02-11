"""
Query collection for failure analysis.

Collects queries during testing/development to identify common failure patterns
and prioritize improvements. NOT for production use (use audit logging instead).
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.evaluation import EvaluationResult, SEVERITY_CRITICAL, SEVERITY_IMPORTANT
from src.logging_config import get_logger

logger = get_logger("viapharma.query_collector")

QUERIES_DIR = Path("data/queries")
QUERIES_FILE = QUERIES_DIR / "collected_queries.jsonl"


@dataclass
class CollectedQuery:
    """A collected query with evaluation results."""

    timestamp: str
    query_hash: str  # For deduplication
    query_text: str  # Actual text (dev/test only)
    category: str
    score: float
    severity: str
    issues: list
    response_preview: str  # First 200 chars of response

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CollectedQuery":
        """Create from dictionary."""
        return cls(**data)


def hash_query(query: str) -> str:
    """Create a hash for query deduplication."""
    normalized = query.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def collect_query(query: str, result: EvaluationResult):
    """
    Collect a query and its evaluation result.

    Args:
        query: The original query text
        result: The evaluation result
    """
    QUERIES_DIR.mkdir(parents=True, exist_ok=True)

    collected = CollectedQuery(
        timestamp=datetime.now().isoformat(),
        query_hash=hash_query(query),
        query_text=query,
        category=result.category,
        score=round(result.overall_score, 3),
        severity=result.severity,
        issues=result.issues,
        response_preview=result.response[:200] if result.response else "",
    )

    with open(QUERIES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(collected.to_dict(), ensure_ascii=False) + "\n")


def load_collected_queries() -> list[CollectedQuery]:
    """Load all collected queries."""
    if not QUERIES_FILE.exists():
        return []

    queries = []
    with open(QUERIES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    queries.append(CollectedQuery.from_dict(data))
                except json.JSONDecodeError:
                    continue

    return queries


def analyze_common_failures(min_occurrences: int = 2) -> dict:
    """
    Analyze collected queries to find common failure patterns.

    Args:
        min_occurrences: Minimum occurrences to include in analysis

    Returns:
        Dictionary with failure analysis
    """
    queries = load_collected_queries()

    if not queries:
        return {"error": "No queries collected yet"}

    # Filter to failures only
    failures = [q for q in queries if q.severity != "pass"]

    if not failures:
        return {"message": "No failures found!", "total_queries": len(queries)}

    # Count issues
    issue_counts = Counter()
    for q in failures:
        for issue in q.issues:
            issue_counts[issue] += 1

    # Count categories with failures
    category_counts = Counter(q.category for q in failures)

    # Find repeated queries (same hash)
    query_hash_counts = Counter(q.query_hash for q in failures)
    repeated_queries = {
        h: count for h, count in query_hash_counts.items()
        if count >= min_occurrences
    }

    # Get example queries for repeated failures
    repeated_examples = {}
    for q in failures:
        if q.query_hash in repeated_queries and q.query_hash not in repeated_examples:
            repeated_examples[q.query_hash] = q.query_text

    return {
        "total_queries": len(queries),
        "total_failures": len(failures),
        "failure_rate": round(len(failures) / len(queries), 3) if queries else 0,
        "issues_by_frequency": dict(issue_counts.most_common(10)),
        "failures_by_category": dict(category_counts.most_common()),
        "repeated_failures": {
            repeated_examples.get(h, h): count
            for h, count in sorted(repeated_queries.items(), key=lambda x: -x[1])
        },
        "severity_breakdown": {
            "critical": sum(1 for q in failures if q.severity == SEVERITY_CRITICAL),
            "important": sum(1 for q in failures if q.severity == SEVERITY_IMPORTANT),
            "minor": sum(1 for q in failures if q.severity not in (SEVERITY_CRITICAL, SEVERITY_IMPORTANT)),
        },
    }


def get_improvement_priorities() -> list[dict]:
    """
    Get prioritized list of improvements based on failure analysis.

    Returns:
        List of improvement recommendations sorted by priority
    """
    analysis = analyze_common_failures()

    if "error" in analysis or "message" in analysis:
        return []

    priorities = []

    # Priority 1: Critical failures
    critical_count = analysis["severity_breakdown"]["critical"]
    if critical_count > 0:
        priorities.append({
            "priority": 1,
            "type": "critical",
            "description": f"Fix {critical_count} critical safety failures",
            "action": "Review safety layer and add missing patterns",
            "count": critical_count,
        })

    # Priority 2: Repeated failures (same query failing multiple times)
    repeated = analysis.get("repeated_failures", {})
    if repeated:
        top_repeated = list(repeated.items())[:3]
        for query, count in top_repeated:
            priorities.append({
                "priority": 2,
                "type": "repeated",
                "description": f"Query fails {count}x: '{query[:50]}...'",
                "action": "Add few-shot example or keyword to classifier",
                "count": count,
            })

    # Priority 3: Category-level issues
    category_failures = analysis.get("failures_by_category", {})
    for category, count in sorted(category_failures.items(), key=lambda x: -x[1])[:3]:
        if count >= 2:
            priorities.append({
                "priority": 3,
                "type": "category",
                "description": f"Category '{category}' has {count} failures",
                "action": f"Review {category} handling in evaluation or prompts",
                "count": count,
            })

    # Priority 4: Common issues
    common_issues = analysis.get("issues_by_frequency", {})
    for issue, count in list(common_issues.items())[:3]:
        if count >= 2:
            priorities.append({
                "priority": 4,
                "type": "issue",
                "description": f"Issue occurs {count}x: '{issue}'",
                "action": "Address in evaluation criteria or response generation",
                "count": count,
            })

    return sorted(priorities, key=lambda x: (x["priority"], -x["count"]))


def print_failure_analysis():
    """Print a formatted failure analysis report."""
    analysis = analyze_common_failures()

    print("\n" + "=" * 70)
    print("🔍 FAILURE ANALYSIS REPORT")
    print("=" * 70)

    if "error" in analysis:
        print(f"Error: {analysis['error']}")
        return

    if "message" in analysis:
        print(f"✅ {analysis['message']}")
        print(f"Total queries analyzed: {analysis['total_queries']}")
        return

    print(f"Total queries:    {analysis['total_queries']}")
    print(f"Total failures:   {analysis['total_failures']}")
    print(f"Failure rate:     {analysis['failure_rate']*100:.1f}%")
    print()

    print("SEVERITY BREAKDOWN")
    print("-" * 40)
    sb = analysis["severity_breakdown"]
    print(f"  🔴 Critical:    {sb['critical']}")
    print(f"  🟡 Important:   {sb['important']}")
    print(f"  🟢 Minor:       {sb['minor']}")
    print()

    print("FAILURES BY CATEGORY")
    print("-" * 40)
    for category, count in analysis["failures_by_category"].items():
        print(f"  {category:15} {count}")
    print()

    print("TOP ISSUES")
    print("-" * 40)
    for issue, count in list(analysis["issues_by_frequency"].items())[:5]:
        print(f"  [{count}x] {issue}")
    print()

    if analysis["repeated_failures"]:
        print("REPEATED FAILURES")
        print("-" * 40)
        for query, count in list(analysis["repeated_failures"].items())[:5]:
            preview = query[:50] + "..." if len(query) > 50 else query
            print(f"  [{count}x] {preview}")
    print()

    print("=" * 70)


def print_improvement_priorities():
    """Print prioritized improvement recommendations."""
    priorities = get_improvement_priorities()

    print("\n" + "=" * 70)
    print("📋 IMPROVEMENT PRIORITIES")
    print("=" * 70)

    if not priorities:
        print("No improvement priorities identified.")
        print("Either no failures or not enough data collected.")
        return

    for p in priorities:
        emoji = {"critical": "🔴", "repeated": "🔁", "category": "📁", "issue": "⚠️"}.get(p["type"], "•")
        print(f"\n{emoji} Priority {p['priority']}: {p['description']}")
        print(f"   Action: {p['action']}")

    print("\n" + "=" * 70)


def clear_collected_queries():
    """Clear all collected queries (for fresh start)."""
    if QUERIES_FILE.exists():
        QUERIES_FILE.unlink()
        logger.info("Cleared collected queries")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.query_collector [analyze|priorities|clear]")
        print("  analyze    - Show failure analysis report")
        print("  priorities - Show improvement priorities")
        print("  clear      - Clear collected queries")
        sys.exit(1)

    command = sys.argv[1]

    if command == "analyze":
        print_failure_analysis()

    elif command == "priorities":
        print_improvement_priorities()

    elif command == "clear":
        clear_collected_queries()
        print("Collected queries cleared.")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
