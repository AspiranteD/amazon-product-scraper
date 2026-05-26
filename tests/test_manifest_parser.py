"""Tests for the manifest CSV parser."""
import csv
import tempfile
from pathlib import Path

from src.manifest import ManifestParser, ManifestRow


def _write_csv(rows: list[dict], filename: str = "test.csv") -> Path:
    """Write a test CSV file and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=f"_{filename}", delete=False, newline="", encoding="utf-8"
    )
    writer = csv.DictWriter(tmp, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    tmp.close()
    return Path(tmp.name)


class TestManifestParser:

    def test_parse_basic_csv(self):
        path = _write_csv([
            {"LPN": "LPN001", "ASIN": "B08TEST123", "Item Desc": "Test Product", "Qty": "1", "Total Retail": "29.99"},
            {"LPN": "LPN002", "ASIN": "B08TEST456", "Item Desc": "Another Product", "Qty": "2", "Total Retail": "49.99"},
        ])
        parser = ManifestParser()
        rows = parser.parse_file(path)

        assert len(rows) == 2
        assert rows[0].lpn == "LPN001"
        assert rows[0].asin == "B08TEST123"
        assert rows[0].item_desc == "Test Product"
        assert rows[0].qty == 1
        assert rows[0].total_retail == 29.99

    def test_handles_underscore_column_names(self):
        path = _write_csv([
            {"lpn": "LPN001", "asin": "B08X", "item_desc": "Product", "total_retail": "10.00"},
        ])
        parser = ManifestParser()
        rows = parser.parse_file(path)

        assert len(rows) == 1
        assert rows[0].lpn == "LPN001"

    def test_handles_space_column_names(self):
        path = _write_csv([
            {"LPN": "LPN001", "ASIN": "B08X", "Item Desc": "Product", "Total Retail": "10.00", "Pallet ID": "P001"},
        ])
        parser = ManifestParser()
        rows = parser.parse_file(path)

        assert len(rows) == 1
        assert rows[0].pallet_id == "P001"

    def test_batch_id_from_filename(self):
        path = _write_csv(
            [{"LPN": "LPN001", "ASIN": "B08X"}],
            filename="A2Z43836.csv",
        )
        parser = ManifestParser()
        rows = parser.parse_file(path)

        assert len(rows) == 1
        assert rows[0].batch_id == "A2Z43836"

    def test_empty_values_become_none(self):
        path = _write_csv([
            {"LPN": "LPN001", "ASIN": "", "Total Retail": "", "Qty": ""},
        ])
        parser = ManifestParser()
        rows = parser.parse_file(path)

        assert len(rows) == 1
        assert rows[0].asin is None
        assert rows[0].total_retail is None
        assert rows[0].qty is None

    def test_stats_tracking(self):
        path = _write_csv([
            {"LPN": "LPN001", "ASIN": "B08X"},
            {"LPN": "LPN002", "ASIN": "B08Y"},
        ])
        parser = ManifestParser()
        parser.parse_file(path)
        stats = parser.get_stats()

        assert stats["files_processed"] == 1
        assert stats["rows_parsed"] == 2
        assert stats["files_failed"] == 0


class TestManifestRow:

    def test_has_asin(self):
        row = ManifestRow(asin="B08TEST123")
        assert row.has_asin() is True

    def test_no_asin(self):
        row = ManifestRow(asin="")
        assert row.has_asin() is False

    def test_retail_value_from_total(self):
        row = ManifestRow(total_retail=29.99)
        assert row.retail_value() == 29.99

    def test_retail_value_from_unit(self):
        row = ManifestRow(unit_retail=10.0, qty=3)
        assert row.retail_value() == 30.0

    def test_retail_value_zero_default(self):
        row = ManifestRow()
        assert row.retail_value() == 0.0
