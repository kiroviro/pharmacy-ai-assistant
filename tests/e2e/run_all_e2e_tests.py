"""
Master test runner for all E2E test suites.
Runs all test categories sequentially and generates a combined report.
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# Configuration
API_URL = "http://localhost:8000"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
TESTS_DIR = Path(__file__).parent

TEST_SUITES = [
    "test_edge_cases.py",         # Smallest first (7 queries, ~1 min)
    "test_medication_queries.py",  # 77 queries
    "test_symptom_queries.py",     # 89 queries
    "test_safety_queries.py",      # 75 queries
    "test_catalog_queries.py",     # 118 queries
]


def check_server():
    """Check if API server is running."""
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        if response.status_code != 200:
            print("❌ Server is not responding correctly.")
            print("   Please start the API server first: python api_server.py")
            return False
        print("✅ API server is running\n")
        return True
    except Exception as e:
        print(f"❌ Cannot connect to API server: {e}")
        print("   Please start the server with: python api_server.py")
        return False


def clear_cache():
    """Clear server caches before test run."""
    print("Clearing server cache...")
    try:
        r = requests.post(f"{API_URL}/cache/clear", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"✅ Cache cleared: {data.get('cleared', [])}\n")
            return True
        else:
            print("⚠️  Cache clear failed; continuing with existing cache\n")
            return False
    except Exception as e:
        print(f"⚠️  Could not clear cache: {e}; continuing\n")
        return False


def run_test_suite(test_file: str) -> dict:
    """Run a single test suite and return results."""
    test_path = TESTS_DIR / test_file
    test_name = test_file.replace("test_", "").replace(".py", "")

    print(f"\n{'='*80}")
    print(f"Running: {test_name.upper()}")
    print(f"{'='*80}\n")

    start_time = time.time()

    try:
        result = subprocess.run(
            [sys.executable, str(test_path)],
            cwd=str(TESTS_DIR),
            capture_output=True,
            text=True,
            timeout=7200  # 2 hour timeout per suite
        )

        elapsed = time.time() - start_time

        # Print stdout for live feedback
        if result.stdout:
            print(result.stdout)

        # Check for errors
        if result.returncode != 0:
            print(f"\n❌ {test_name} FAILED (exit code {result.returncode})")
            if result.stderr:
                print(f"Error output:\n{result.stderr}")
            return {
                "suite": test_name,
                "status": "failed",
                "exit_code": result.returncode,
                "elapsed_seconds": round(elapsed, 2),
                "error": result.stderr,
            }

        # Try to load the result JSON
        output_file = OUTPUT_DIR / f"test_results_{test_name}.json"
        if output_file.exists():
            with open(output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                report = data.get("report", {})
                summary = report.get("summary", {})

                return {
                    "suite": test_name,
                    "status": "success",
                    "exit_code": 0,
                    "elapsed_seconds": round(elapsed, 2),
                    "total_queries": summary.get("total_queries", 0),
                    "by_severity": summary.get("by_severity", {}),
                    "by_status": summary.get("by_status", {}),
                    "output_file": str(output_file),
                }
        else:
            return {
                "suite": test_name,
                "status": "success",
                "exit_code": 0,
                "elapsed_seconds": round(elapsed, 2),
                "output_file": None,
            }

    except subprocess.TimeoutExpired:
        print(f"\n❌ {test_name} TIMEOUT (exceeded 2 hours)")
        return {
            "suite": test_name,
            "status": "timeout",
            "elapsed_seconds": 7200,
        }
    except Exception as e:
        print(f"\n❌ {test_name} EXCEPTION: {e}")
        return {
            "suite": test_name,
            "status": "exception",
            "error": str(e),
        }


def print_summary(results: list):
    """Print combined summary of all test suites."""
    print("\n\n" + "="*80)
    print("📊 ALL E2E TESTS - SUMMARY")
    print("="*80 + "\n")

    total_queries = 0
    total_time = 0
    all_severity = {"none": 0, "low": 0, "medium": 0, "high": 0, "critical": 0}

    for r in results:
        suite = r["suite"]
        status = r["status"]
        elapsed = r.get("elapsed_seconds", 0)
        total_time += elapsed

        if status == "success":
            queries = r.get("total_queries", 0)
            total_queries += queries

            # Aggregate severity counts
            for sev, count in r.get("by_severity", {}).items():
                all_severity[sev] = all_severity.get(sev, 0) + count

            icon = "✅"
            status_str = f"{queries} queries in {elapsed:.1f}s"
        elif status == "failed":
            icon = "❌"
            status_str = f"FAILED (exit {r.get('exit_code', 'unknown')})"
        elif status == "timeout":
            icon = "⏱️"
            status_str = "TIMEOUT"
        else:
            icon = "❌"
            status_str = "EXCEPTION"

        print(f"{icon} {suite:25} {status_str}")

    print(f"\n{'='*80}")
    print(f"Total Queries: {total_queries}")
    print(f"Total Time: {total_time/60:.1f} minutes")
    print(f"\n⚠️  SEVERITY DISTRIBUTION (all suites)")
    for severity in ["critical", "high", "medium", "low", "none"]:
        count = all_severity.get(severity, 0)
        if count > 0:
            icon = {"critical": "🚨", "high": "❌", "medium": "⚠️", "low": "⚠️", "none": "✅"}[severity]
            pct = (count / total_queries * 100) if total_queries > 0 else 0
            print(f"  {icon} {severity.upper():8} {count:3} ({pct:.1f}%)")

    print(f"\n{'='*80}")


def main():
    """Main entry point."""
    print(f"\n🚀 Starting all E2E test suites at {datetime.now().isoformat()}\n")

    # Check server
    if not check_server():
        sys.exit(1)

    # Clear cache once at start
    clear_cache()

    # Run all test suites
    results = []
    for test_file in TEST_SUITES:
        result = run_test_suite(test_file)
        results.append(result)

        # Small delay between suites
        time.sleep(2)

    # Print summary
    print_summary(results)

    # Save combined results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "test_results_all_e2e.json"

    output = {
        "timestamp": datetime.now().isoformat(),
        "suites_run": len(results),
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Combined results saved to: {output_file}")

    # Exit code based on failures
    failed = sum(1 for r in results if r["status"] != "success")
    if failed > 0:
        print(f"\n❌ {failed} test suite(s) failed")
        sys.exit(1)
    else:
        print(f"\n✅ All test suites completed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
