#!/usr/bin/env python3
"""
Price Validator for ViaPharma products.

Compares prices in products_processed.csv against live benu.bg prices
to identify discrepancies.

Usage:
    # Sample validation (default 50 products)
    python scripts/price_validator.py --sample 50

    # Full audit (all products, with rate limiting)
    python scripts/price_validator.py --full --delay 1.0

    # Check specific products by URL handle
    python scripts/price_validator.py --products "handle1,handle2,handle3"
"""

import argparse
import csv
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests

# Rate limiting settings
DEFAULT_DELAY = 0.5  # seconds between requests
MAX_RETRIES = 3


@dataclass
class PriceComparison:
    """Result of comparing CSV price vs live benu.bg price."""

    url_handle: str
    title: str
    csv_price_bgn: float
    csv_price_eur: float
    benu_price_eur: float | None
    benu_price_bgn: float | None
    status: str  # "match", "mismatch", "not_found", "error"
    difference_bgn: float | None = None
    difference_pct: float | None = None
    error_message: str | None = None


def fetch_benu_price(url_handle: str, session: requests.Session) -> tuple[float | None, float | None, str | None]:
    """
    Fetch price from benu.bg for a given product URL handle.

    Returns: (price_eur, price_bgn, error_message)
    """
    url = f"https://benu.bg/{url_handle}"

    try:
        response = session.get(url, timeout=10)

        if response.status_code == 404:
            return None, None, "Product not found on benu.bg"

        if response.status_code != 200:
            return None, None, f"HTTP {response.status_code}"

        html = response.text

        # Try to extract price from JSON-LD schema
        schema_match = re.search(r'"@type"\s*:\s*"Product"[^}]*"price"\s*:\s*"?([0-9.]+)"?', html)
        if schema_match:
            price_eur = float(schema_match.group(1))
            price_bgn = round(price_eur * 1.9558, 2)  # Fixed EUR to BGN rate
            return price_eur, price_bgn, None

        # Fallback: look for price in meta tags or common patterns
        meta_match = re.search(r'<meta[^>]*property="product:price:amount"[^>]*content="([0-9.]+)"', html)
        if meta_match:
            price_eur = float(meta_match.group(1))
            price_bgn = round(price_eur * 1.9558, 2)
            return price_eur, price_bgn, None

        # Another pattern: look for offers schema
        offers_match = re.search(r'"offers"[^}]*"price"\s*:\s*"?([0-9.]+)"?', html)
        if offers_match:
            price_eur = float(offers_match.group(1))
            price_bgn = round(price_eur * 1.9558, 2)
            return price_eur, price_bgn, None

        return None, None, "Could not parse price from page"

    except requests.RequestException as e:
        return None, None, f"Request error: {str(e)}"
    except Exception as e:
        return None, None, f"Parse error: {str(e)}"


def load_products(csv_path: str) -> list[dict]:
    """Load products from CSV file."""
    products = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append(row)
    return products


def compare_prices(
    products: list[dict],
    sample_size: int | None = None,
    delay: float = DEFAULT_DELAY,
    progress_callback=None,
) -> list[PriceComparison]:
    """
    Compare CSV prices against live benu.bg prices.

    Args:
        products: List of product dicts from CSV
        sample_size: If set, randomly sample this many products
        delay: Seconds to wait between requests
        progress_callback: Optional callback(current, total) for progress updates

    Returns:
        List of PriceComparison results
    """
    if sample_size and sample_size < len(products):
        products = random.sample(products, sample_size)

    results = []
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.8",
    })

    total = len(products)
    for i, product in enumerate(products):
        url_handle = product.get("url_handle", "")
        title = product.get("title", "")

        try:
            csv_price_bgn = float(product.get("price_bgn", 0))
            csv_price_eur = float(product.get("price_eur", 0))
        except (ValueError, TypeError):
            csv_price_bgn = 0
            csv_price_eur = 0

        if progress_callback:
            progress_callback(i + 1, total)

        # Fetch live price
        benu_eur, benu_bgn, error = fetch_benu_price(url_handle, session)

        if error:
            status = "not_found" if "not found" in error.lower() else "error"
            results.append(PriceComparison(
                url_handle=url_handle,
                title=title,
                csv_price_bgn=csv_price_bgn,
                csv_price_eur=csv_price_eur,
                benu_price_eur=None,
                benu_price_bgn=None,
                status=status,
                error_message=error,
            ))
        else:
            # Compare prices (use BGN as primary comparison)
            diff_bgn = round(benu_bgn - csv_price_bgn, 2) if benu_bgn else None
            diff_pct = round((diff_bgn / csv_price_bgn) * 100, 1) if diff_bgn and csv_price_bgn else None

            # Consider match if within 2% or 0.50 BGN
            is_match = abs(diff_bgn or 0) <= max(0.50, csv_price_bgn * 0.02)
            status = "match" if is_match else "mismatch"

            results.append(PriceComparison(
                url_handle=url_handle,
                title=title,
                csv_price_bgn=csv_price_bgn,
                csv_price_eur=csv_price_eur,
                benu_price_eur=benu_eur,
                benu_price_bgn=benu_bgn,
                status=status,
                difference_bgn=diff_bgn,
                difference_pct=diff_pct,
            ))

        # Rate limiting
        if i < total - 1:
            time.sleep(delay)

    return results


def generate_report(results: list[PriceComparison], output_path: str | None = None) -> str:
    """Generate a summary report of price comparisons."""
    total = len(results)
    matches = sum(1 for r in results if r.status == "match")
    mismatches = [r for r in results if r.status == "mismatch"]
    not_found = sum(1 for r in results if r.status == "not_found")
    errors = sum(1 for r in results if r.status == "error")

    lines = [
        "=" * 70,
        "PRICE VALIDATION REPORT",
        f"Generated: {datetime.now().isoformat()}",
        "=" * 70,
        "",
        "SUMMARY",
        "-" * 40,
        f"Total products checked:  {total}",
        f"Prices match:            {matches} ({matches/total*100:.1f}%)",
        f"Price mismatches:        {len(mismatches)} ({len(mismatches)/total*100:.1f}%)",
        f"Not found on benu.bg:    {not_found} ({not_found/total*100:.1f}%)",
        f"Errors:                  {errors} ({errors/total*100:.1f}%)",
        "",
    ]

    if mismatches:
        # Sort by absolute difference
        mismatches.sort(key=lambda x: abs(x.difference_bgn or 0), reverse=True)

        lines.extend([
            "PRICE MISMATCHES (sorted by difference)",
            "-" * 70,
        ])

        for r in mismatches[:50]:  # Show top 50
            direction = "↑" if (r.difference_bgn or 0) > 0 else "↓"
            lines.append(
                f"{direction} {r.title[:40]:<40} | "
                f"CSV: {r.csv_price_bgn:>7.2f} BGN | "
                f"Benu: {r.benu_price_bgn:>7.2f} BGN | "
                f"Diff: {r.difference_bgn:>+7.2f} ({r.difference_pct:>+5.1f}%)"
            )

        if len(mismatches) > 50:
            lines.append(f"... and {len(mismatches) - 50} more mismatches")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)

    return report


def save_results_csv(results: list[PriceComparison], output_path: str):
    """Save detailed results to CSV."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "url_handle", "title", "csv_price_bgn", "csv_price_eur",
            "benu_price_bgn", "benu_price_eur", "difference_bgn",
            "difference_pct", "status", "error_message"
        ])

        for r in results:
            writer.writerow([
                r.url_handle, r.title, r.csv_price_bgn, r.csv_price_eur,
                r.benu_price_bgn or "", r.benu_price_eur or "",
                r.difference_bgn or "", r.difference_pct or "",
                r.status, r.error_message or ""
            ])


def main():
    parser = argparse.ArgumentParser(description="Validate ViaPharma prices against benu.bg")
    parser.add_argument("--csv", default="data/products_processed.csv", help="Path to products CSV")
    parser.add_argument("--sample", type=int, help="Number of random products to check")
    parser.add_argument("--full", action="store_true", help="Check all products")
    parser.add_argument("--products", help="Comma-separated list of URL handles to check")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Delay between requests (seconds)")
    parser.add_argument("--output", default="data/price_validation", help="Output directory for reports")

    args = parser.parse_args()

    # Load products
    print(f"Loading products from {args.csv}...")
    products = load_products(args.csv)
    print(f"Loaded {len(products)} products")

    # Filter if specific products requested
    if args.products:
        handles = [h.strip() for h in args.products.split(",")]
        products = [p for p in products if p.get("url_handle") in handles]
        if not products:
            print("No matching products found!")
            sys.exit(1)
        print(f"Checking {len(products)} specific products")

    # Determine sample size
    sample_size = None
    if args.sample:
        sample_size = min(args.sample, len(products))
        print(f"Sampling {sample_size} random products")
    elif not args.full and not args.products:
        sample_size = min(50, len(products))
        print(f"Default: sampling {sample_size} products (use --full for all)")

    # Progress callback
    def progress(current, total):
        pct = current / total * 100
        bar = "=" * int(pct / 2) + ">" + " " * (50 - int(pct / 2))
        print(f"\r[{bar}] {current}/{total} ({pct:.1f}%)", end="", flush=True)

    # Run comparison
    print("\nFetching prices from benu.bg...")
    results = compare_prices(products, sample_size, args.delay, progress)
    print("\n")

    # Generate report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = f"{args.output}/report_{timestamp}.txt"
    csv_path = f"{args.output}/results_{timestamp}.csv"

    report = generate_report(results, report_path)
    print(report)

    save_results_csv(results, csv_path)
    print(f"\nDetailed results saved to: {csv_path}")
    print(f"Report saved to: {report_path}")

    # Return exit code based on mismatch rate
    mismatch_rate = sum(1 for r in results if r.status == "mismatch") / len(results)
    if mismatch_rate > 0.1:  # More than 10% mismatches
        print(f"\nWARNING: {mismatch_rate*100:.1f}% price mismatch rate!")
        sys.exit(1)


if __name__ == "__main__":
    main()
