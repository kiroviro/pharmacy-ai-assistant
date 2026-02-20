#!/usr/bin/env python3
"""
Shopify Product Data Quality Checker

Validates crawled product data against Shopify requirements to prevent
import failures and production degradation.
"""

import csv
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class QualityMetrics:
    """Quality metrics for product data."""
    total_products: int = 0
    total_variants: int = 0

    # Critical fields
    missing_title: int = 0
    missing_price: int = 0
    missing_sku: int = 0
    invalid_barcode: int = 0
    valid_barcode: int = 0
    no_barcode: int = 0

    # Images
    missing_image: int = 0
    placeholder_image: int = 0

    # Data quality
    duplicate_skus: int = 0
    duplicate_barcodes: int = 0
    invalid_price: int = 0

    # Collections
    skus_seen: set = None
    barcodes_seen: set = None

    def __post_init__(self):
        self.skus_seen = set()
        self.barcodes_seen = set()


def is_valid_ean13(barcode: str) -> bool:
    """Validate EAN-13 barcode with checksum."""
    if not barcode or not barcode.isdigit():
        return False

    if len(barcode) != 13:
        return False

    # EAN-13 checksum validation
    odd_sum = sum(int(barcode[i]) for i in range(0, 12, 2))
    even_sum = sum(int(barcode[i]) for i in range(1, 12, 2))
    checksum = (10 - ((odd_sum + even_sum * 3) % 10)) % 10

    return checksum == int(barcode[12])


def check_file_quality(csv_path: Path) -> QualityMetrics:
    """Check quality of a single CSV file."""
    metrics = QualityMetrics()

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Count products vs variants
            if row.get('Title'):
                metrics.total_products += 1
            metrics.total_variants += 1

            # Check critical fields
            title = row.get('Title', '').strip()
            if not title:
                metrics.missing_title += 1

            price = row.get('Price', '').strip()
            if not price:
                metrics.missing_price += 1
            else:
                try:
                    float(price)
                except ValueError:
                    metrics.invalid_price += 1

            sku = row.get('SKU', '').strip()
            if not sku:
                metrics.missing_sku += 1
            else:
                if sku in metrics.skus_seen:
                    metrics.duplicate_skus += 1
                metrics.skus_seen.add(sku)

            # Barcode validation
            barcode = row.get('Barcode', '').strip()
            if not barcode:
                metrics.no_barcode += 1
            elif is_valid_ean13(barcode):
                metrics.valid_barcode += 1
                if barcode in metrics.barcodes_seen:
                    metrics.duplicate_barcodes += 1
                metrics.barcodes_seen.add(barcode)
            else:
                metrics.invalid_barcode += 1

            # Image checks
            image_url = row.get('Product image URL', '').strip()
            if not image_url:
                metrics.missing_image += 1
            elif 'placeholder' in image_url.lower() or 'default' in image_url.lower():
                metrics.placeholder_image += 1

    return metrics


def print_report(metrics: QualityMetrics, file_name: str):
    """Print detailed quality report."""
    print("=" * 70)
    print(f"SHOPIFY IMPORT QUALITY REPORT: {file_name}")
    print("=" * 70)
    print(f"Total products:            {metrics.total_products:,}")
    print(f"Total variants:            {metrics.total_variants:,}")
    print()

    # Critical fields
    print("CRITICAL FIELDS")
    print("-" * 70)
    if metrics.missing_title > 0:
        print(f"  ✗ FAIL  Missing titles:       {metrics.missing_title}")
    else:
        print(f"  ✓ PASS  All products have titles")

    if metrics.missing_price > 0:
        print(f"  ✗ FAIL  Missing prices:       {metrics.missing_price}")
    else:
        print(f"  ✓ PASS  All products have prices")

    if metrics.invalid_price > 0:
        print(f"  ✗ FAIL  Invalid prices:       {metrics.invalid_price}")

    print()

    # Barcodes
    print("BARCODES")
    print("-" * 70)
    barcode_coverage = (metrics.valid_barcode / metrics.total_variants * 100) if metrics.total_variants > 0 else 0
    print(f"With valid EAN-13:         {metrics.valid_barcode:,}")
    print(f"With invalid barcodes:     {metrics.invalid_barcode:,}")
    print(f"Without barcodes:          {metrics.no_barcode:,}")
    print(f"Valid barcode coverage:    {barcode_coverage:.1f}%")

    if metrics.duplicate_barcodes > 0:
        print(f"  ⚠️  WARNING  Duplicate barcodes:  {metrics.duplicate_barcodes}")

    print()

    # Images
    print("IMAGES")
    print("-" * 70)
    if metrics.missing_image > 0:
        print(f"  ✗ FAIL  Missing images:       {metrics.missing_image}")
    else:
        print(f"  ✓ PASS  All products have images")

    if metrics.placeholder_image > 0:
        print(f"  ⚠️  WARNING  Placeholder images: {metrics.placeholder_image}")

    print()

    # SKU quality
    if metrics.duplicate_skus > 0:
        print(f"  ✗ FAIL  Duplicate SKUs:       {metrics.duplicate_skus}")
        print()

    # Overall assessment
    print("=" * 70)
    print("SHOPIFY IMPORT READINESS")
    print("=" * 70)

    critical_issues = []
    warnings = []

    if metrics.missing_title > 0:
        critical_issues.append(f"Missing titles: {metrics.missing_title}")
    if metrics.missing_price > 0:
        critical_issues.append(f"Missing prices: {metrics.missing_price}")
    if metrics.invalid_price > 0:
        critical_issues.append(f"Invalid prices: {metrics.invalid_price}")
    if metrics.duplicate_skus > 0:
        critical_issues.append(f"Duplicate SKUs: {metrics.duplicate_skus}")
    if metrics.missing_image > 0:
        critical_issues.append(f"Missing images: {metrics.missing_image}")

    if barcode_coverage < 85:
        warnings.append(f"Low barcode coverage: {barcode_coverage:.1f}% (recommend >85%)")
    if metrics.invalid_barcode > 10:
        warnings.append(f"Many invalid barcodes: {metrics.invalid_barcode}")
    if metrics.placeholder_image > 0:
        warnings.append(f"Placeholder images: {metrics.placeholder_image}")

    if critical_issues:
        print("✗ NOT READY FOR SHOPIFY IMPORT")
        print()
        print("Critical issues that will cause import failures:")
        for issue in critical_issues:
            print(f"  • {issue}")
        print()
        return False
    else:
        print("✓ READY FOR SHOPIFY IMPORT")
        print()
        if warnings:
            print("⚠️  Warnings (non-blocking):")
            for warning in warnings:
                print(f"  • {warning}")
            print()
        return True


def main():
    """Check all product CSV files."""
    output_dir = Path('output')

    # Check all products_*.csv files
    csv_files = sorted(output_dir.glob('products_*.csv'))

    if not csv_files:
        print("❌ No product CSV files found in output/ directory")
        sys.exit(1)

    all_ready = True

    for csv_file in csv_files:
        metrics = check_file_quality(csv_file)
        ready = print_report(metrics, csv_file.name)
        all_ready = all_ready and ready
        print()

    # Overall status
    print("=" * 70)
    if all_ready:
        print("✅ ALL FILES READY FOR SHOPIFY IMPORT")
        print()
        print("Next steps:")
        print("  1. Backup your current Shopify product data")
        print("  2. Import using Shopify admin: Products > Import")
        print("  3. Review imported products before publishing")
        sys.exit(0)
    else:
        print("❌ FILES NOT READY - FIX ISSUES BEFORE IMPORTING")
        print()
        print("Fix critical issues above to prevent import failures.")
        sys.exit(1)


if __name__ == '__main__':
    main()
