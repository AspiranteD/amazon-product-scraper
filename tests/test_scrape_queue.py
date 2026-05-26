"""Tests for ScrapeQueue and ScrapeItem."""
import pytest
from datetime import datetime, timedelta
from src.queue.scrape_queue import ScrapeQueue, ScrapeItem


class TestScrapeItemProperties:
    def test_new_item_is_not_complete(self):
        item = ScrapeItem(lpn="LPN001", asin="B0TEST")
        assert item.is_complete is False

    def test_complete_item(self):
        item = ScrapeItem(
            lpn="LPN001", asin="B0TEST",
            amazon_description="Title", image_urls="img.jpg",
            amazon_features="Feature", scraped_price=99,
        )
        assert item.is_complete is True

    def test_has_description(self):
        assert ScrapeItem(lpn="L", asin="A", amazon_description="T").has_description is True
        assert ScrapeItem(lpn="L", asin="A", amazon_description="").has_description is False
        assert ScrapeItem(lpn="L", asin="A").has_description is False

    def test_has_price(self):
        assert ScrapeItem(lpn="L", asin="A", scraped_price=10).has_price is True
        assert ScrapeItem(lpn="L", asin="A", scraped_price=0).has_price is True
        assert ScrapeItem(lpn="L", asin="A").has_price is False

    def test_is_dead_at_99(self):
        assert ScrapeItem(lpn="L", asin="A", scraping_attempts=99).is_dead is True
        assert ScrapeItem(lpn="L", asin="A", scraping_attempts=5).is_dead is False

    def test_missing_fields(self):
        item = ScrapeItem(lpn="L", asin="A", amazon_description="T")
        missing = item.missing_fields
        assert "amazon_description" not in missing
        assert "image_urls" in missing
        assert "amazon_features" in missing
        assert "scraped_price" in missing


class TestScrapeQueueSorting:
    def test_fewer_attempts_first(self):
        items = [
            ScrapeItem(lpn="L2", asin="A2", scraping_attempts=3),
            ScrapeItem(lpn="L1", asin="A1", scraping_attempts=0),
        ]
        queue = ScrapeQueue(items)
        result = queue.get_pending()
        assert result[0].lpn == "L1"

    def test_nulls_first_on_last_scraped(self):
        items = [
            ScrapeItem(lpn="L1", asin="A1", scraping_attempts=1,
                      last_scraped_at=datetime(2024, 1, 1)),
            ScrapeItem(lpn="L2", asin="A2", scraping_attempts=1,
                      last_scraped_at=None),
        ]
        queue = ScrapeQueue(items)
        result = queue.get_pending()
        assert result[0].lpn == "L2"

    def test_older_scrape_before_newer(self):
        items = [
            ScrapeItem(lpn="L2", asin="A2", scraping_attempts=2,
                      last_scraped_at=datetime(2024, 6, 1)),
            ScrapeItem(lpn="L1", asin="A1", scraping_attempts=2,
                      last_scraped_at=datetime(2024, 1, 1)),
        ]
        queue = ScrapeQueue(items)
        result = queue.get_pending()
        assert result[0].lpn == "L1"


class TestScrapeQueueFiltering:
    def test_excludes_complete_items(self):
        items = [
            ScrapeItem(lpn="L1", asin="A1"),
            ScrapeItem(lpn="L2", asin="A2", amazon_description="T",
                      image_urls="i", amazon_features="f", scraped_price=10),
        ]
        queue = ScrapeQueue(items)
        result = queue.get_pending()
        assert len(result) == 1
        assert result[0].lpn == "L1"

    def test_excludes_over_max_attempts(self):
        items = [
            ScrapeItem(lpn="L1", asin="A1", scraping_attempts=5),
            ScrapeItem(lpn="L2", asin="A2", scraping_attempts=15),
        ]
        queue = ScrapeQueue(items, max_attempts=10)
        result = queue.get_pending()
        assert len(result) == 1
        assert result[0].lpn == "L1"

    def test_excludes_empty_asin(self):
        items = [
            ScrapeItem(lpn="L1", asin=""),
            ScrapeItem(lpn="L2", asin="B0OK"),
        ]
        queue = ScrapeQueue(items)
        result = queue.get_pending()
        assert len(result) == 1

    def test_excludes_unavailable(self):
        items = [
            ScrapeItem(lpn="L1", asin="A1", available=False),
            ScrapeItem(lpn="L2", asin="A2", available=True),
        ]
        queue = ScrapeQueue(items)
        result = queue.get_pending()
        assert len(result) == 1
        assert result[0].lpn == "L2"

    def test_price_only_mode(self):
        items = [
            ScrapeItem(lpn="L1", asin="A1", scraped_price=50),
            ScrapeItem(lpn="L2", asin="A2", scraped_price=None),
            ScrapeItem(lpn="L3", asin="A3"),
        ]
        queue = ScrapeQueue(items)
        result = queue.get_pending(price_only=True)
        lpns = [i.lpn for i in result]
        assert "L1" not in lpns
        assert "L2" in lpns
        assert "L3" in lpns

    def test_batch_id_filter(self):
        items = [
            ScrapeItem(lpn="L1", asin="A1", batch_id="A2Z001"),
            ScrapeItem(lpn="L2", asin="A2", batch_id="A2Z002"),
            ScrapeItem(lpn="L3", asin="A3", batch_id="A2Z001"),
        ]
        queue = ScrapeQueue(items)
        result = queue.get_pending(batch_id="A2Z001")
        assert len(result) == 2
        assert all(i.batch_id == "A2Z001" for i in result)

    def test_skip_attempt_limit(self):
        items = [
            ScrapeItem(lpn="L1", asin="A1", scraping_attempts=50),
        ]
        queue = ScrapeQueue(items, max_attempts=10)
        assert len(queue.get_pending()) == 0
        assert len(queue.get_pending(skip_attempt_limit=True)) == 1

    def test_limit(self):
        items = [ScrapeItem(lpn=f"L{i}", asin=f"A{i}") for i in range(20)]
        queue = ScrapeQueue(items)
        result = queue.get_pending(limit=5)
        assert len(result) == 5

    def test_empty_queue(self):
        queue = ScrapeQueue([])
        assert queue.get_pending() == []


class TestScrapeQueueStats:
    def test_stats(self):
        items = [
            ScrapeItem(lpn="L1", asin="A1"),
            ScrapeItem(lpn="L2", asin="A2", scraping_attempts=99),
            ScrapeItem(lpn="L3", asin="A3", amazon_description="T",
                      image_urls="i", amazon_features="f", scraped_price=10),
            ScrapeItem(lpn="L4", asin="A4", available=False),
        ]
        queue = ScrapeQueue(items)
        stats = queue.get_stats()
        assert stats["total"] == 4
        assert stats["dead"] == 1
        assert stats["complete"] == 1


class TestScrapeQueueCRUD:
    def test_add_items(self):
        queue = ScrapeQueue([])
        queue.add_items([ScrapeItem(lpn="L1", asin="A1")])
        assert len(queue) == 1

    def test_remove_item(self):
        queue = ScrapeQueue([ScrapeItem(lpn="L1", asin="A1")])
        assert queue.remove_item("L1") is True
        assert len(queue) == 0
        assert queue.remove_item("NONEXIST") is False

    def test_get_item(self):
        item = ScrapeItem(lpn="L1", asin="A1")
        queue = ScrapeQueue([item])
        assert queue.get_item("L1") is item
        assert queue.get_item("NONEXIST") is None
