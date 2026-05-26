"""
Amazon liquidation manifest CSV parser.

Handles multiple CSV formats with automatic column detection and normalization.
Supports 35+ column variations across different manifest versions.
"""
import csv
import logging
import re
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

from .models import ManifestRow

logger = logging.getLogger(__name__)

CSV_TO_FIELD_MAPPING = {
    "liquidatorvendorcode": "liquidatorvendorcode",
    "inventorylocation": "inventorylocation",
    "fc": "fc",
    "iog": "iog",
    "condition": "condition",
    "shipmentclosed": "shipmentclosed",
    "bol": "bol",
    "carrier": "carrier",
    "shiptocity": "shiptocity",
    "pkgid": "pkgid",
    "pallet_id": "pallet_id",
    "pallet id": "pallet_id",
    "gl": "gl",
    "department": "department",
    "gl_description": "gl_description",
    "gl description": "gl_description",
    "categorycode": "categorycode",
    "category": "category",
    "subcatcode": "subcatcode",
    "subcategory": "subcategory",
    "asin": "asin",
    "upc": "upc",
    "ean": "ean",
    "fcsku": "fcsku",
    "fnsku": "fnsku",
    "item_desc": "item_desc",
    "item desc": "item_desc",
    "qty": "qty",
    "itempkgweight": "itempkgweight",
    "itempkgweightuom": "itempkgweightuom",
    "currency_code": "currency_code",
    "currency code": "currency_code",
    "cost": "cost",
    "total_retail": "total_retail",
    "total retail": "total_retail",
    "total_cost": "total_cost",
    "total cost": "total_cost",
    "unit_retail": "unit_retail",
    "unit retail": "unit_retail",
    "lpn": "lpn",
    "listing_id": "listing_id",
    "listing id": "listing_id",
    "slot_size": "slot_size",
    "slot size": "slot_size",
    "is_parcel": "is_parcel",
    "is parcel": "is_parcel",
    "date_in": "date_in",
    "date in": "date_in",
}

FIELD_TYPES: dict[str, type] = {
    "qty": int,
    "itempkgweight": float,
    "cost": float,
    "total_retail": float,
    "total_cost": float,
    "unit_retail": float,
    "is_parcel": bool,
    "date_in": date,
}


class ManifestParser:
    """
    Parses Amazon liquidation manifest CSVs with automatic format detection.

    Handles:
    - Multiple CSV column naming conventions (spaces, underscores, mixed case)
    - Type coercion (int, float, bool, date) with fallback to None
    - Batch ID extraction from filenames (e.g. A2Z43836.csv -> "A2Z43836")
    - Batch processing of multiple CSV files
    """

    def __init__(self):
        self._stats = {
            "files_processed": 0,
            "files_failed": 0,
            "rows_parsed": 0,
            "rows_failed": 0,
        }

    def parse_file(self, path: str | Path) -> list[ManifestRow]:
        """Parse a single manifest CSV file into ManifestRow objects."""
        path = Path(path)
        logger.info("Parsing manifest: %s", path.name)

        column_mapping = self._detect_format(path)
        if not column_mapping:
            self._stats["files_failed"] += 1
            return []

        batch_id = self._extract_batch_id(path.name)
        rows = []

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row_num, csv_row in enumerate(reader, start=2):
                    try:
                        row = self._map_row(csv_row, column_mapping)
                        row.batch_id = batch_id
                        rows.append(row)
                        self._stats["rows_parsed"] += 1
                    except Exception as e:
                        self._stats["rows_failed"] += 1
                        logger.warning("Row %d in %s: %s", row_num, path.name, e)

            self._stats["files_processed"] += 1
            logger.info("Parsed %s: %d rows", path.name, len(rows))

        except Exception as e:
            self._stats["files_failed"] += 1
            logger.error("Failed to parse %s: %s", path.name, e)

        return rows

    def parse_directory(self, directory: str | Path) -> list[ManifestRow]:
        """Parse all CSV files in a directory."""
        directory = Path(directory)
        csv_files = sorted(directory.glob("*.csv"))
        logger.info("Found %d CSV files in %s", len(csv_files), directory)

        all_rows = []
        for csv_file in csv_files:
            all_rows.extend(self.parse_file(csv_file))

        return all_rows

    def get_stats(self) -> dict:
        return self._stats.copy()

    def _detect_format(self, path: Path) -> Optional[dict[str, str]]:
        """Read CSV header and build column mapping."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    logger.error("No columns in %s", path)
                    return None

                mapping = {}
                for col in reader.fieldnames:
                    normalized = col.strip().lower()
                    if normalized in CSV_TO_FIELD_MAPPING:
                        mapping[col] = CSV_TO_FIELD_MAPPING[normalized]

                mapped = len(mapping)
                total = len(reader.fieldnames)
                logger.info("Format detected in %s: %d/%d columns mapped", path.name, mapped, total)
                return mapping

        except Exception as e:
            logger.error("Error detecting format of %s: %s", path, e)
            return None

    @staticmethod
    def _map_row(csv_row: dict[str, str], column_mapping: dict[str, str]) -> ManifestRow:
        """Map a CSV row dict to a ManifestRow using the column mapping."""
        data: dict[str, Any] = {}
        for csv_col, field_name in column_mapping.items():
            raw = csv_row.get(csv_col, "")
            field_type = FIELD_TYPES.get(field_name, str)
            data[field_name] = _parse_value(raw, field_type)

        valid_fields = {k: v for k, v in data.items() if hasattr(ManifestRow, k)}
        return ManifestRow(**valid_fields)

    @staticmethod
    def _extract_batch_id(filename: str) -> Optional[str]:
        """Extract batch identifier from filename (e.g. 'A2Z43836.csv' -> 'A2Z43836')."""
        match = re.search(r"(A2Z\d+)", filename, re.IGNORECASE)
        return match.group(1).upper() if match else None


def _parse_value(value: str, field_type: type) -> Any:
    """Parse a CSV string value to the target type."""
    if value is None or value.strip() == "":
        return None

    value = value.strip()

    try:
        if field_type == int:
            return int(float(value.replace(",", "").replace(" ", "")))
        elif field_type == float:
            return float(value.replace(",", "").replace(" ", ""))
        elif field_type == bool:
            return value.lower() in ("true", "1", "yes", "y", "t")
        elif field_type == date:
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
            return None
        else:
            return value
    except (ValueError, TypeError):
        return None
