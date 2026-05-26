#!/usr/bin/env python3
"""
Example: Parse a liquidation manifest CSV and display summary.

Usage:
    python examples/parse_manifest.py path/to/manifest.csv
    python examples/parse_manifest.py path/to/manifest_dir/
"""
import sys
import os
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.manifest import ManifestParser


def main():
    parser = argparse.ArgumentParser(description="Parse Amazon liquidation manifest CSV")
    parser.add_argument("path", help="Path to a CSV file or directory of CSVs")
    args = parser.parse_args()

    target = Path(args.path)
    manifest_parser = ManifestParser()

    if target.is_dir():
        rows = manifest_parser.parse_directory(target)
    elif target.is_file():
        rows = manifest_parser.parse_file(target)
    else:
        print(f"ERROR: {target} not found")
        sys.exit(1)

    stats = manifest_parser.get_stats()

    print(f"\n{'=' * 60}")
    print("MANIFEST SUMMARY")
    print(f"{'=' * 60}")
    print(f"Files processed: {stats['files_processed']}")
    print(f"Total rows:      {len(rows)}")
    print(f"With ASIN:       {sum(1 for r in rows if r.has_asin())}")
    print(f"Without ASIN:    {sum(1 for r in rows if not r.has_asin())}")

    total_retail = sum(r.retail_value() for r in rows)
    print(f"Total retail:    ${total_retail:,.2f}")

    departments = {}
    for r in rows:
        dept = r.department or "(unknown)"
        departments[dept] = departments.get(dept, 0) + 1

    print(f"\nDepartments ({len(departments)}):")
    for dept, count in sorted(departments.items(), key=lambda x: -x[1])[:10]:
        print(f"  {dept}: {count}")

    batches = set(r.batch_id for r in rows if r.batch_id)
    if batches:
        print(f"\nBatch IDs: {', '.join(sorted(batches))}")


if __name__ == "__main__":
    main()
