#!/usr/bin/env python3
"""
Validate fresh crawl data against live benu.bg prices.
"""

import csv
import random
import re
import time

import requests


def fetch_benu_price(url_handle: str, session: requests.Session) -> tuple[float | None, float | None, str | None]:
    """Fetch price from live benu.bg."""
    url = f"https://benu.bg/{url_handle}"

    try:
        response = session.get(url, timeout=10)
        if response.status_code == 404:
            return None, None, "not_found"
        if response.status_code != 200:
            return None, None, f"http_{response.status_code}"

        html = response.text

        # Extract EUR price from schema
        patterns = [
            r'"@type"\s*:\s*"Product"[^}]*"price"\s*:\s*"?([0-9.]+)"?',
            r'"offers"[^}]*"price"\s*:\s*"?([0-9.]+)"?',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                price_eur = float(match.group(1))
                price_bgn = round(price_eur * 1.9558, 2)
                return price_eur, price_bgn, None

        return None, None, "parse_error"

    except Exception as e:
        return None, None, str(e)[:50]


def main():
    # Load fresh crawl
    fresh_crawl_path = "/Users/kiril/IdeaProjects/pharmacy-to-shopify/data/benu.bg/raw/products.csv"

    products = []
    with open(fresh_crawl_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append(row)

    print(f"Loaded {len(products)} products from fresh crawl")

    # Sample random products
    sample = random.sample(products, min(30, len(products)))

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept-Language": "bg-BG,bg;q=0.9",
    })

    matches = 0
    mismatches = []
    errors = 0

    print("\nValidating against live benu.bg...")
    print("-" * 80)

    for i, product in enumerate(sample):
        handle = product.get("URL handle", "")
        title = product.get("Title", "")[:40]

        try:
            crawl_price = float(product.get("Price", 0) or 0)
            crawl_eur = float(product.get("Price EUR", 0) or 0)
        except:
            crawl_price = 0
            crawl_eur = 0

        live_eur, live_bgn, error = fetch_benu_price(handle, session)

        if error:
            errors += 1
            status = f"ERROR: {error}"
        elif live_bgn:
            diff = abs(live_bgn - crawl_price)
            diff_pct = (diff / crawl_price * 100) if crawl_price else 100

            if diff <= max(0.50, crawl_price * 0.05):  # Within 5% or 0.50 BGN
                matches += 1
                status = "✓ MATCH"
            else:
                mismatches.append({
                    "title": title,
                    "handle": handle,
                    "crawl": crawl_price,
                    "live": live_bgn,
                    "diff": diff,
                    "diff_pct": diff_pct,
                })
                status = f"✗ MISMATCH: crawl={crawl_price:.2f}, live={live_bgn:.2f} ({diff_pct:+.1f}%)"
        else:
            errors += 1
            status = "ERROR: no price"

        print(f"[{i+1:2}/{len(sample)}] {title:<40} {status}")
        time.sleep(0.5)

    # Summary
    total = len(sample)
    mismatch_count = len(mismatches)

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total checked:    {total}")
    print(f"Matches:          {matches} ({matches/total*100:.1f}%)")
    print(f"Mismatches:       {mismatch_count} ({mismatch_count/total*100:.1f}%)")
    print(f"Errors:           {errors} ({errors/total*100:.1f}%)")

    if mismatches:
        print("\nTOP MISMATCHES:")
        for m in sorted(mismatches, key=lambda x: x["diff"], reverse=True)[:10]:
            print(f"  {m['title']:<40} crawl={m['crawl']:>7.2f} live={m['live']:>7.2f} diff={m['diff_pct']:>+6.1f}%")


if __name__ == "__main__":
    main()
