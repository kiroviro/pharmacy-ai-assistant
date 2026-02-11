"""
Metrics tracking for LLM response quality.

Tracks quality scores over time and provides trend analysis
to help identify improvements or regressions.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.evaluation import (
    EvaluationResult,
    SEVERITY_CRITICAL,
    SEVERITY_IMPORTANT,
    SEVERITY_MINOR,
    SEVERITY_PASS,
    CATEGORY_THRESHOLDS,
    CRITERIA_WEIGHTS,
)
from src.logging_config import get_logger

logger = get_logger("viapharma.metrics")

METRICS_DIR = Path("data/metrics")


@dataclass
class MetricsSnapshot:
    """A snapshot of quality metrics at a point in time."""

    timestamp: str
    total_queries: int
    passed_queries: int
    overall_score: float
    scores_by_category: dict = field(default_factory=dict)
    scores_by_criterion: dict = field(default_factory=dict)
    failure_breakdown: dict = field(default_factory=dict)
    avg_response_time_ms: float = 0.0

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate as percentage."""
        if self.total_queries == 0:
            return 0.0
        return self.passed_queries / self.total_queries

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "total_queries": self.total_queries,
            "passed_queries": self.passed_queries,
            "pass_rate": round(self.pass_rate, 3),
            "overall_score": round(self.overall_score, 3),
            "scores_by_category": {k: round(v, 3) for k, v in self.scores_by_category.items()},
            "scores_by_criterion": {k: round(v, 3) for k, v in self.scores_by_criterion.items()},
            "failure_breakdown": self.failure_breakdown,
            "avg_response_time_ms": round(self.avg_response_time_ms, 2),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MetricsSnapshot":
        """Create from dictionary."""
        return cls(
            timestamp=data["timestamp"],
            total_queries=data["total_queries"],
            passed_queries=data["passed_queries"],
            overall_score=data["overall_score"],
            scores_by_category=data.get("scores_by_category", {}),
            scores_by_criterion=data.get("scores_by_criterion", {}),
            failure_breakdown=data.get("failure_breakdown", {}),
            avg_response_time_ms=data.get("avg_response_time_ms", 0.0),
        )


def calculate_metrics(results: list[EvaluationResult]) -> MetricsSnapshot:
    """
    Calculate metrics from evaluation results.

    Args:
        results: List of EvaluationResult objects

    Returns:
        MetricsSnapshot with aggregated metrics
    """
    if not results:
        return MetricsSnapshot(
            timestamp=datetime.now().isoformat(),
            total_queries=0,
            passed_queries=0,
            overall_score=0.0,
        )

    # Basic counts
    total = len(results)
    passed = sum(1 for r in results if r.passed)

    # Overall score
    overall_score = sum(r.overall_score for r in results) / total

    # Scores by category
    category_scores = {}
    category_counts = {}
    for r in results:
        if r.category not in category_scores:
            category_scores[r.category] = 0.0
            category_counts[r.category] = 0
        category_scores[r.category] += r.overall_score
        category_counts[r.category] += 1

    scores_by_category = {
        cat: category_scores[cat] / category_counts[cat]
        for cat in category_scores
    }

    # Scores by criterion
    criterion_scores = {k: 0.0 for k in CRITERIA_WEIGHTS}
    for r in results:
        for criterion, score in r.scores.items():
            if criterion in criterion_scores:
                criterion_scores[criterion] += score

    scores_by_criterion = {
        k: v / total for k, v in criterion_scores.items()
    }

    # Failure breakdown
    failure_breakdown = {
        "critical": sum(1 for r in results if r.severity == SEVERITY_CRITICAL),
        "important": sum(1 for r in results if r.severity == SEVERITY_IMPORTANT),
        "minor": sum(1 for r in results if r.severity == SEVERITY_MINOR),
        "pass": sum(1 for r in results if r.severity == SEVERITY_PASS),
    }

    # Average response time
    avg_time = sum(r.response_time_ms for r in results) / total

    return MetricsSnapshot(
        timestamp=datetime.now().isoformat(),
        total_queries=total,
        passed_queries=passed,
        overall_score=overall_score,
        scores_by_category=scores_by_category,
        scores_by_criterion=scores_by_criterion,
        failure_breakdown=failure_breakdown,
        avg_response_time_ms=avg_time,
    )


def save_metrics(snapshot: MetricsSnapshot, filename: Optional[str] = None) -> Path:
    """
    Save metrics snapshot to file.

    Args:
        snapshot: MetricsSnapshot to save
        filename: Optional filename (default: metrics_{date}.json)

    Returns:
        Path to saved file
    """
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    if filename is None:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"metrics_{date_str}.json"

    filepath = METRICS_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot.to_dict(), f, indent=2, ensure_ascii=False)

    logger.info(f"Saved metrics to {filepath}")
    return filepath


def load_metrics(filepath: Path) -> MetricsSnapshot:
    """Load metrics from file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return MetricsSnapshot.from_dict(data)


def load_metrics_history(days: int = 30) -> list[MetricsSnapshot]:
    """
    Load metrics history for the specified number of days.

    Args:
        days: Number of days to look back

    Returns:
        List of MetricsSnapshot objects, sorted by timestamp
    """
    if not METRICS_DIR.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days)
    snapshots = []

    for filepath in METRICS_DIR.glob("metrics_*.json"):
        try:
            snapshot = load_metrics(filepath)
            snapshot_time = datetime.fromisoformat(snapshot.timestamp.replace("Z", "+00:00"))
            if snapshot_time.replace(tzinfo=None) >= cutoff:
                snapshots.append(snapshot)
        except Exception as e:
            logger.warning(f"Failed to load {filepath}: {e}")

    return sorted(snapshots, key=lambda s: s.timestamp)


def get_trend_indicator(current: float, previous: float, threshold: float = 0.02) -> str:
    """
    Get trend indicator comparing current to previous value.

    Args:
        current: Current value
        previous: Previous value
        threshold: Minimum change to show trend (default 2%)

    Returns:
        "↑" for improvement, "↓" for regression, "→" for stable
    """
    if previous == 0:
        return "→"

    change = (current - previous) / previous

    if change > threshold:
        return "↑"
    elif change < -threshold:
        return "↓"
    else:
        return "→"


def print_metrics_report(
    current: MetricsSnapshot,
    history: Optional[list[MetricsSnapshot]] = None,
):
    """
    Print a formatted metrics report.

    Args:
        current: Current metrics snapshot
        history: Optional historical snapshots for trend analysis
    """
    # Get previous snapshot for comparison
    previous = history[-2] if history and len(history) >= 2 else None

    print("\n" + "=" * 70)
    print("📊 QUALITY METRICS REPORT")
    print("=" * 70)
    print(f"Timestamp: {current.timestamp}")
    print(f"Total queries: {current.total_queries}")
    print()

    # Overall metrics
    print("OVERALL METRICS")
    print("-" * 40)

    score_trend = get_trend_indicator(current.overall_score, previous.overall_score) if previous else ""
    pass_trend = get_trend_indicator(current.pass_rate, previous.pass_rate) if previous else ""

    print(f"  Overall score:  {current.overall_score*100:5.1f}%  {score_trend}")
    print(f"  Pass rate:      {current.pass_rate*100:5.1f}%  {pass_trend}")
    print(f"  Avg response:   {current.avg_response_time_ms:5.0f}ms")
    print()

    # Failure breakdown
    print("FAILURES BY SEVERITY")
    print("-" * 40)
    fb = current.failure_breakdown
    total_failures = fb.get("critical", 0) + fb.get("important", 0) + fb.get("minor", 0)
    print(f"  🔴 Critical:    {fb.get('critical', 0):3d}  (must fix)")
    print(f"  🟡 Important:   {fb.get('important', 0):3d}  (should fix)")
    print(f"  🟢 Minor:       {fb.get('minor', 0):3d}  (nice to fix)")
    print(f"  ✅ Pass:        {fb.get('pass', 0):3d}")
    print()

    # Category breakdown
    print("SCORES BY CATEGORY")
    print("-" * 40)
    for category, score in sorted(current.scores_by_category.items()):
        threshold = CATEGORY_THRESHOLDS.get(category, 0.85)
        status = "✅" if score >= threshold else "❌"

        prev_score = previous.scores_by_category.get(category) if previous else None
        trend = get_trend_indicator(score, prev_score) if prev_score else ""

        print(f"  {category:15} {score*100:5.1f}% / {threshold*100:.0f}%  {status} {trend}")
    print()

    # Criterion breakdown
    print("SCORES BY CRITERION")
    print("-" * 40)
    for criterion, score in sorted(current.scores_by_criterion.items()):
        weight = CRITERIA_WEIGHTS.get(criterion, 0)
        prev_score = previous.scores_by_criterion.get(criterion) if previous else None
        trend = get_trend_indicator(score, prev_score) if prev_score else ""

        print(f"  {criterion:15} {score*100:5.1f}%  (weight: {weight*100:.0f}%) {trend}")
    print()

    # Recommendations
    print("RECOMMENDATIONS")
    print("-" * 40)
    if fb.get("critical", 0) > 0:
        print("  ⚠️  Fix critical failures immediately (safety issues)")
    if fb.get("important", 0) > 0:
        print("  📝 Address important failures (intent classification)")

    # Find lowest scoring categories
    low_categories = [
        (cat, score) for cat, score in current.scores_by_category.items()
        if score < CATEGORY_THRESHOLDS.get(cat, 0.85)
    ]
    if low_categories:
        print(f"  📉 Focus on: {', '.join(cat for cat, _ in low_categories)}")

    print("=" * 70)


def print_trend_report(history: list[MetricsSnapshot], days: int = 7):
    """Print a trend report showing changes over time."""
    if len(history) < 2:
        print("Not enough data for trend analysis (need at least 2 snapshots)")
        return

    print("\n" + "=" * 70)
    print(f"📈 QUALITY TREND REPORT (Last {days} days)")
    print("=" * 70)

    oldest = history[0]
    newest = history[-1]

    print(f"Period: {oldest.timestamp[:10]} to {newest.timestamp[:10]}")
    print(f"Snapshots: {len(history)}")
    print()

    # Overall trend
    score_change = newest.overall_score - oldest.overall_score
    pass_change = newest.pass_rate - oldest.pass_rate

    print("OVERALL TREND")
    print("-" * 40)
    print(f"  Score:     {oldest.overall_score*100:.1f}% → {newest.overall_score*100:.1f}%  ({score_change*100:+.1f}%)")
    print(f"  Pass rate: {oldest.pass_rate*100:.1f}% → {newest.pass_rate*100:.1f}%  ({pass_change*100:+.1f}%)")
    print()

    # Category trends
    print("CATEGORY TRENDS")
    print("-" * 40)
    all_categories = set(oldest.scores_by_category.keys()) | set(newest.scores_by_category.keys())
    for category in sorted(all_categories):
        old_score = oldest.scores_by_category.get(category, 0)
        new_score = newest.scores_by_category.get(category, 0)
        change = new_score - old_score
        trend = get_trend_indicator(new_score, old_score)
        print(f"  {category:15} {old_score*100:.1f}% → {new_score*100:.1f}%  ({change*100:+.1f}%) {trend}")

    print("=" * 70)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.metrics [report|trend|history]")
        print("  report  - Show latest metrics report")
        print("  trend   - Show trend over last 7 days")
        print("  history - List all saved metrics")
        sys.exit(1)

    command = sys.argv[1]

    if command == "report":
        history = load_metrics_history(days=30)
        if history:
            print_metrics_report(history[-1], history)
        else:
            print("No metrics found. Run evaluation first.")

    elif command == "trend":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        history = load_metrics_history(days=days)
        print_trend_report(history, days)

    elif command == "history":
        history = load_metrics_history(days=365)
        print(f"\nFound {len(history)} metrics snapshots:")
        for s in history:
            print(f"  {s.timestamp[:19]}  score={s.overall_score*100:.1f}%  pass={s.pass_rate*100:.1f}%")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
