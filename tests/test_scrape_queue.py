"""Tests for ScrapeQueue priority system."""
import pytest
from datetime import datetime, timedelta
from src.queue.scrape_queue import ScrapeQueue, ScrapeItem


class TestScrapeItemProperties:
    def test_needs_full_scrape_when_missing_all(self):
        item = ScrapeItem(asin="B0TEST")
        assert item.needs_full_scrape is True

    def test_needs_full_scrape_when_missing_price(self):
        item = ScrapeItem(asin="B0TEST", has_title=True, has_images=True, has_features=True)
        assert item.needs_full_scrape is True

    def test_complete_item_does_not_need_scrape(self):
        item = ScrapeItem(asin="B0TEST", has_title=True, has_images=True,
                         has_price=True, has_features=True)
        assert item.needs_full_scrape is False

    def test_needs_price_only(self):
        item = ScrapeItem(asin="B0TEST", has_title=True, has_images=True,
                         has_price=False, has_features=True)
        assert item.needs_price_only is True

    def test_not_price_only_when_missing_title(self):
        item = ScrapeItem(asin="B0TEST", has_images=True, has_features=True)
        assert item.needs_price_only is False

    def test_permanently_failed(self):
        item = ScrapeItem(asin="B0TEST", scraping_attempts=99)
        assert item.is_permanently_failed is True

    def test_not_permanently_failed(self):
        item = ScrapeItem(asin="B0TEST", scraping_attempts=5)
        assert item.is_permanently_failed is False

    def test_permanently_failed_above_99(self):
        item = ScrapeItem(asin="B0TEST", scraping_attempts=100)
        assert item.is_permanently_failed is True


class TestSortKey:
    def test_fewer_attempts_first(self):
        item_0 = ScrapeItem(asin="A", scraping_attempts=0)
        item_3 = ScrapeItem(asin="B", scraping_attempts=3)
        assert item_0.sort_key < item_3.sort_key

    def test_never_scraped_before_scraped_same_attempts(self):
        never = ScrapeItem(asin="A", scraping_attempts=1, last_scraped_at=None)
        old = ScrapeItem(asin="B", scraping_attempts=1,
                        last_scraped_at=datetime(2024, 1, 1))
        assert never.sort_key < old.sort_key

    def test_older_scrape_before_newer_same_attempts(self):
        old = ScrapeItem(asin="A", scraping_attempts=2,
                        last_scraped_at=datetime(2024, 1, 1))
        new = ScrapeItem(asin="B", scraping_attempts=2,
                        last_scraped_at=datetime(2024, 6, 1))
        assert old.sort_key < new.sort_key

    def test_attempts_take_priority_over_timestamp(self):
        low_attempt_recent = ScrapeItem(asin="A", scraping_attempts=1,
                                       last_scraped_at=datetime(2024, 12, 1))
        high_attempt_old = ScrapeItem(asin="B", scraping_attempts=5,
                                     last_scraped_at=datetime(2020, 1, 1))
        assert low_attempt_recent.sort_key < high_attempt_old.sort_key


class TestQueueBuild:
    def _make_items(self):
        now = datetime.now()
        return [
            ScrapeItem(asin="FRESH", scraping_attempts=0),
            ScrapeItem(asin="RETRY1", scraping_attempts=2,
                      last_scraped_at=now - timedelta(hours=5)),
            ScrapeItem(asin="RETRY2", scraping_attempts=2,
                      last_scraped_at=now - timedelta(hours=1)),
            ScrapeItem(asin="FAILED404", scraping_attempts=99),
            ScrapeItem(asin="COMPLETE", has_title=True, has_images=True,
                      has_price=True, has_features=True),
            ScrapeItem(asin="PRICE_ONLY", has_title=True, has_images=True,
                      has_features=True, scraping_attempts=1),
        ]

    def test_excludes_permanently_failed(self):
        items = self._make_items()
        queue = ScrapeQueue(items)
        result = queue.build()
        asins = [i.asin for i in result]
        assert "FAILED404" not in asins

    def test_excludes_complete_items(self):
        items = self._make_items()
        queue = ScrapeQueue(items)
        result = queue.build()
        asins = [i.asin for i in result]
        assert "COMPLETE" not in asins

    def test_priority_order(self):
        items = self._make_items()
        queue = ScrapeQueue(items)
        result = queue.build()
        asins = [i.asin for i in result]
        assert asins[0] == "FRESH"
        assert asins.index("RETRY1") < asins.index("RETRY2")

    def test_limit(self):
        items = self._make_items()
        queue = ScrapeQueue(items)
        result = queue.build(limit=2)
        assert len(result) == 2

    def test_price_only_filter(self):
        items = self._make_items()
        queue = ScrapeQueue(items, price_only=True)
        result = queue.build()
        assert len(result) == 1
        assert result[0].asin == "PRICE_ONLY"

    def test_a2z_filter(self):
        items = [
            ScrapeItem(asin="A1", id_a2z="A2Z001"),
            ScrapeItem(asin="A2", id_a2z="A2Z002"),
            ScrapeItem(asin="A3", id_a2z="A2Z001"),
            ScrapeItem(asin="A4"),
        ]
        queue = ScrapeQueue(items, filter_a2z=["A2Z001"])
        result = queue.build()
        asins = [i.asin for i in result]
        assert set(asins) == {"A1", "A3"}

    def test_a2z_filter_multiple_codes(self):
        items = [
            ScrapeItem(asin="A1", id_a2z="A2Z001"),
            ScrapeItem(asin="A2", id_a2z="A2Z002"),
            ScrapeItem(asin="A3", id_a2z="A2Z003"),
        ]
        queue = ScrapeQueue(items, filter_a2z=["A2Z001", "A2Z003"])
        result = queue.build()
        asins = [i.asin for i in result]
        assert set(asins) == {"A1", "A3"}

    def test_max_attempts_filter(self):
        items = [
            ScrapeItem(asin="OK", scraping_attempts=5),
            ScrapeItem(asin="TOOMANY", scraping_attempts=50),
        ]
        queue = ScrapeQueue(items, max_attempts=10)
        result = queue.build()
        asins = [i.asin for i in result]
        assert "OK" in asins
        assert "TOOMANY" not in asins

    def test_empty_items(self):
        queue = ScrapeQueue([])
        result = queue.build()
        assert result == []

    def test_all_complete_returns_empty(self):
        items = [
            ScrapeItem(asin="A", has_title=True, has_images=True,
                      has_price=True, has_features=True),
        ]
        queue = ScrapeQueue(items)
        result = queue.build()
        assert result == []


class TestQueueStats:
    def test_stats_counts(self):
        items = [
            ScrapeItem(asin="A"),
            ScrapeItem(asin="B", scraping_attempts=99),
            ScrapeItem(asin="C", has_title=True, has_images=True, has_features=True),
            ScrapeItem(asin="D", has_title=True, has_images=True,
                      has_price=True, has_features=True),
        ]
        queue = ScrapeQueue(items)
        stats = queue.stats()
        assert stats["total_items"] == 4
        assert stats["permanently_failed_404"] == 1
        assert stats["need_price_only"] == 1

    def test_never_scraped_count(self):
        items = [
            ScrapeItem(asin="A"),
            ScrapeItem(asin="B", last_scraped_at=datetime.now()),
            ScrapeItem(asin="C", scraping_attempts=99),
        ]
        queue = ScrapeQueue(items)
        stats = queue.stats()
        assert stats["never_scraped"] == 1
