#!/usr/bin/env python3
"""
Fix product data issues before Shopify import.

Handles:
- Removes rows with missing titles/prices (variants without main product)
- Fixes duplicate SKUs
- Reports on fixable vs unfixable issues
"""

import csv
import sys
from pathlib import Path
from collections import defaultdict


def fix_csv_file(input_path: Path, output_path: Path):
    """Fix quality issues in CSV file."""
    removed_count = 0
    fixed_skus = 0
    sku_counter = defaultdict(int)

    with open(input_path, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames

        # Read all rows
        rows = []
        for row in reader:
            title = row.get('Title', '').strip()
            price = row.get('Price', '').strip()

            # Skip rows without title AND price (orphaned variants)
            if not title and not price:
                removed_count += 1
                continue

            # Fix duplicate SKUs by appending counter
            sku = row.get('SKU', '').strip()
            if sku:
                sku_counter[sku] += 1
                if sku_counter[sku] > 1:
                    row['SKU'] = f"{sku}-{sku_counter[sku]}"
                    fixed_skus += 1

            rows.append(row)

    # Write fixed data
    with open(output_path, 'w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return removed_count, fixed_skus


def main():
    """Fix all product CSV files."""
    output_dir = Path('output')
    fixed_dir = output_dir / 'fixed'
    fixed_dir.mkdir(exist_ok=True)

    csv_files = sorted(output_dir.glob('products_*.csv'))

    if not csv_files:
        print("❌ No product CSV files found")
        sys.exit(1)

    print("=" * 70)
    print("FIXING PRODUCT DATA ISSUES")
    print("=" * 70)
    print()

    for csv_file in csv_files:
        output_file = fixed_dir / csv_file.name
        removed, fixed_skus = fix_csv_file(csv_file, output_file)

        print(f"✓ {csv_file.name}")
        print(f"  Removed {removed} orphaned variant rows")
        print(f"  Fixed {fixed_skus} duplicate SKUs")
        print(f"  Saved to: {output_file}")
        print()

    print("=" * 70)
    print("✅ FIXED FILES SAVED TO: output/fixed/")
    print()
    print("Next step: Run quality check on fixed files:")
    print("  python3 check_shopify_quality.py")
    print("=" * 70)


if __name__ == '__main__':
    main()
