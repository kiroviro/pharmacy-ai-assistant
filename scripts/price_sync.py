#!/usr/bin/env python3
"""
Price Sync System for ViaPharma products.

Fetches current prices from benu.bg and updates the local CSV.
Designed to be run as a scheduled job (cron/GitHub Actions).

Usage:
    # Sync all products (with rate limiting)
    python scripts/price_sync.py --full

    # Sync only products with known mismatches
    python scripts/price_sync.py --mismatches data/price_validation/results_latest.csv

    # Dry run (don't update CSV, just report)
    python scripts/price_sync.py --dry-run --sample 100

    # Generate Shopify-compatible update CSV
    python scripts/price_sync.py --shopify-export
"""

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

# Rate limiting - be respectful to benu.bg
REQUEST_DELAY = 1.0  # seconds between requests
BATCH_SIZE = 100  # products per batch
BATCH_DELAY = 10  # seconds between batches

# Price tolerance - don't update if difference is tiny
PRICE_TOLERANCE_BGN = 0.10
PRICE_TOLERANCE_PCT = 0.01  # 1%

# EUR to BGN fixed rate
EUR_TO_BGN = 1.9558
BGN_TO_EUR = 0.5113


@dataclass
class PriceUpdate:
    """Represents a price update for a product."""

    url_handle: str
    sku: str
    title: str
    old_price_bgn: float
    new_price_bgn: float
    old_price_eur: float
    new_price_eur: float
    difference_bgn: float
    difference_pct: float
    source: str = "benu.bg"
    timestamp: str = ""


def fetch_benu_price(url_handle: str, session: requests.Session) -> tuple[float | None, str | None]:
    """
    Fetch current price from benu.bg.

    Returns: (price_eur, error_message)
    """
    url = f"https://benu.bg/{url_handle}"

    try:
        response = session.get(url, timeout=15)

        if response.status_code == 404:
            return None, "not_found"

        if response.status_code != 200:
            return None, f"http_{response.status_code}"

        html = response.text

        # Extract price from JSON-LD schema
        patterns = [
            r'"@type"\s*:\s*"Product"[^}]*"price"\s*:\s*"?([0-9.]+)"?',
            r'"offers"[^}]*"price"\s*:\s*"?([0-9.]+)"?',
            r'<meta[^>]*property="product:price:amount"[^>]*content="([0-9.]+)"',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return float(match.group(1)), None

        return None, "parse_error"

    except requests.Timeout:
        return None, "timeout"
    except requests.RequestException as e:
        return None, f"request_error"
    except Exception as e:
        return None, f"error"


def load_products_csv(csv_path: str) -> tuple[list[dict], list[str]]:
    """Load products from CSV, returning rows and fieldnames."""
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        products = list(reader)
    return products, fieldnames


def should_update_price(old_bgn: float, new_bgn: float) -> bool:
    """Determine if price difference warrants an update."""
    if old_bgn == 0:
        return new_bgn > 0

    diff = abs(new_bgn - old_bgn)
    diff_pct = diff / old_bgn

    return diff > PRICE_TOLERANCE_BGN or diff_pct > PRICE_TOLERANCE_PCT


def sync_prices(
    products: list[dict],
    delay: float = REQUEST_DELAY,
    dry_run: bool = False,
    progress_callback=None,
) -> tuple[list[PriceUpdate], list[dict]]:
    """
    Sync prices from benu.bg.

    Args:
        products: List of product dicts
        delay: Seconds between requests
        dry_run: If True, don't modify products
        progress_callback: Optional callback(current, total, product_name)

    Returns:
        (list of updates made, list of errors)
    """
    updates = []
    errors = []

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.8",
    })

    total = len(products)
    timestamp = datetime.now().isoformat()

    for i, product in enumerate(products):
        url_handle = product.get("url_handle", "")
        title = product.get("title", "")[:50]
        sku = product.get("sku", "")

        if progress_callback:
            progress_callback(i + 1, total, title)

        try:
            old_price_bgn = float(product.get("price_bgn", 0))
            old_price_eur = float(product.get("price_eur", 0))
        except (ValueError, TypeError):
            old_price_bgn = 0
            old_price_eur = 0

        # Fetch current price
        new_price_eur, error = fetch_benu_price(url_handle, session)

        if error:
            errors.append({
                "url_handle": url_handle,
                "title": title,
                "error": error,
            })
        elif new_price_eur is not None:
            new_price_bgn = round(new_price_eur * EUR_TO_BGN, 2)

            if should_update_price(old_price_bgn, new_price_bgn):
                diff_bgn = round(new_price_bgn - old_price_bgn, 2)
                diff_pct = round((diff_bgn / old_price_bgn * 100) if old_price_bgn else 100, 1)

                update = PriceUpdate(
                    url_handle=url_handle,
                    sku=sku,
                    title=product.get("title", ""),
                    old_price_bgn=old_price_bgn,
                    new_price_bgn=new_price_bgn,
                    old_price_eur=old_price_eur,
                    new_price_eur=new_price_eur,
                    difference_bgn=diff_bgn,
                    difference_pct=diff_pct,
                    timestamp=timestamp,
                )
                updates.append(update)

                # Update product dict if not dry run
                if not dry_run:
                    product["price_bgn"] = new_price_bgn
                    product["price_eur"] = new_price_eur

        # Rate limiting with batch delays
        if i < total - 1:
            time.sleep(delay)
            if (i + 1) % BATCH_SIZE == 0:
                print(f"\n  Batch complete, pausing {BATCH_DELAY}s...")
                time.sleep(BATCH_DELAY)

    return updates, errors


def save_products_csv(products: list[dict], fieldnames: list[str], output_path: str):
    """Save updated products to CSV."""
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(products)


def save_updates_log(updates: list[PriceUpdate], output_path: str):
    """Save update log for auditing."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "url_handle", "sku", "title",
            "old_price_bgn", "new_price_bgn", "difference_bgn", "difference_pct"
        ])
        for u in updates:
            writer.writerow([
                u.timestamp, u.url_handle, u.sku, u.title,
                u.old_price_bgn, u.new_price_bgn, u.difference_bgn, u.difference_pct
            ])


def generate_shopify_update_csv(updates: list[PriceUpdate], output_path: str):
    """
    Generate Shopify-compatible CSV for bulk price updates.

    This can be imported directly into Shopify Admin > Products > Import.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        # Shopify bulk update columns
        writer.writerow(["Handle", "Variant Price"])
        for u in updates:
            writer.writerow([u.url_handle, u.new_price_bgn])

    print(f"Shopify update CSV saved to: {output_path}")
    print("Import via: Shopify Admin > Products > Import > Update existing products")


def main():
    parser = argparse.ArgumentParser(description="Sync ViaPharma prices from benu.bg")
    parser.add_argument("--csv", default="data/products_processed.csv", help="Path to products CSV")
    parser.add_argument("--sample", type=int, help="Only sync N random products")
    parser.add_argument("--full", action="store_true", help="Sync all products")
    parser.add_argument("--mismatches", help="Only sync products from a previous validation CSV")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help="Delay between requests")
    parser.add_argument("--dry-run", action="store_true", help="Don't update CSV, just report")
    parser.add_argument("--shopify-export", action="store_true", help="Generate Shopify import CSV")
    parser.add_argument("--output-dir", default="data/price_sync", help="Output directory")

    args = parser.parse_args()

    # Load products
    print(f"Loading products from {args.csv}...")
    products, fieldnames = load_products_csv(args.csv)
    print(f"Loaded {len(products)} products")

    # Filter based on mode
    if args.mismatches:
        # Load mismatches from previous validation
        print(f"Loading mismatches from {args.mismatches}...")
        with open(args.mismatches, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            mismatch_handles = {
                row["url_handle"]
                for row in reader
                if row.get("status") == "mismatch"
            }
        products = [p for p in products if p.get("url_handle") in mismatch_handles]
        print(f"Found {len(products)} mismatched products to sync")

    elif args.sample:
        import random
        products = random.sample(products, min(args.sample, len(products)))
        print(f"Sampling {len(products)} products")

    elif not args.full:
        print("Use --full to sync all products, --sample N for subset, or --mismatches for previous mismatches")
        sys.exit(1)

    if not products:
        print("No products to sync!")
        sys.exit(0)

    # Progress callback
    def progress(current, total, name):
        pct = current / total * 100
        print(f"\r[{current}/{total}] ({pct:.1f}%) {name:<50}", end="", flush=True)

    # Run sync
    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"\n{mode}: Syncing prices from benu.bg...")
    print(f"Estimated time: ~{len(products) * args.delay / 60:.1f} minutes\n")

    updates, errors = sync_prices(products, args.delay, args.dry_run, progress)
    print("\n")

    # Report results
    print("=" * 60)
    print("SYNC RESULTS")
    print("=" * 60)
    print(f"Products checked:  {len(products)}")
    print(f"Prices updated:    {len(updates)}")
    print(f"Errors:            {len(errors)}")

    if updates:
        total_diff = sum(u.difference_bgn for u in updates)
        avg_diff = total_diff / len(updates)
        print(f"\nAverage price change: {avg_diff:+.2f} BGN")

        print("\nTop 10 price changes:")
        for u in sorted(updates, key=lambda x: abs(x.difference_bgn), reverse=True)[:10]:
            direction = "↑" if u.difference_bgn > 0 else "↓"
            print(f"  {direction} {u.title[:40]:<40} {u.old_price_bgn:>7.2f} → {u.new_price_bgn:>7.2f} ({u.difference_pct:+.1f}%)")

    # Save outputs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    if updates:
        # Save update log
        log_path = f"{args.output_dir}/updates_{timestamp}.csv"
        save_updates_log(updates, log_path)
        print(f"\nUpdate log saved to: {log_path}")

        # Generate Shopify export if requested
        if args.shopify_export:
            shopify_path = f"{args.output_dir}/shopify_import_{timestamp}.csv"
            generate_shopify_update_csv(updates, shopify_path)

    # Save updated CSV if not dry run
    if not args.dry_run and updates:
        # Reload all products and apply updates
        all_products, all_fieldnames = load_products_csv(args.csv)

        # Create lookup for updates
        update_lookup = {u.url_handle: u for u in updates}

        for product in all_products:
            handle = product.get("url_handle", "")
            if handle in update_lookup:
                u = update_lookup[handle]
                product["price_bgn"] = u.new_price_bgn
                product["price_eur"] = u.new_price_eur

        # Backup original
        backup_path = f"{args.output_dir}/backup_{timestamp}.csv"
        import shutil
        shutil.copy(args.csv, backup_path)
        print(f"Backup saved to: {backup_path}")

        # Save updated CSV
        save_products_csv(all_products, all_fieldnames, args.csv)
        print(f"Updated CSV saved to: {args.csv}")

    if errors:
        error_path = f"{args.output_dir}/errors_{timestamp}.csv"
        with open(error_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["url_handle", "title", "error"])
            writer.writeheader()
            writer.writerows(errors)
        print(f"Errors saved to: {error_path}")


if __name__ == "__main__":
    main()
