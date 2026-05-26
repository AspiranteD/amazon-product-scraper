"""Tests for BatchProcessor with idempotent writes and mark_failures."""
import pytest
from unittest.mock import MagicMock, patch
from src.processor.batch_processor import BatchProcessor, ScrapeResult, PERMANENT_FAIL_ATTEMPTS
from src.scraper.amazon_scraper import AmazonScraper


@pytest.fixture
def mock_scraper():
    return MagicMock(spec=AmazonScraper)


@pytest.fixture
def store():
    return {}


@pytest.fixture
def commits():
    return []


def make_processor(scraper, store, commits, **kwargs):
    def on_result(asin, data, meta):
        store[asin] = {"data": data, "meta": meta}
    def on_commit():
        commits.append(True)
    return BatchProcessor(
        scraper=scraper, on_result=on_result, on_commit=on_commit,
        delay_seconds=0, **kwargs,
    )


class TestSuccessfulScrape:
    @patch("src.processor.batch_processor.time.sleep")
    def test_full_success_with_idempotent_write(self, mock_sleep, mock_scraper, store, commits):
        mock_scraper.scrape_product.return_value = {
            "_status": 200, "title": "New Title", "images": "img.jpg",
            "price": 99, "features": "Cool",
        }
        processor = make_processor(mock_scraper, store, commits)
        items = [{"asin": "B0T", "scraping_attempts": 0}]
        result = processor.process(items)
        assert result.success == 1
        assert store["B0T"]["data"]["amazon_description"] == "New Title"
        assert store["B0T"]["data"]["scraped_price"] == 99
        assert store["B0T"]["meta"]["price_saved"] is True

    @patch("src.processor.batch_processor.time.sleep")
    def test_idempotent_skip_existing_description(self, mock_sleep, mock_scraper, store, commits):
        """If item already has amazon_description, don't overwrite it."""
        mock_scraper.scrape_product.return_value = {
            "_status": 200, "title": "New Title", "images": "img.jpg",
            "price": 50, "features": "F",
        }
        processor = make_processor(mock_scraper, store, commits)
        items = [{"asin": "B0T", "scraping_attempts": 0,
                  "amazon_description": "Existing Title",
                  "image_urls": "existing.jpg"}]
        result = processor.process(items)
        assert "amazon_description" not in store["B0T"]["data"]
        assert "image_urls" not in store["B0T"]["data"]
        assert store["B0T"]["data"].get("scraped_price") == 50

    @patch("src.processor.batch_processor.time.sleep")
    def test_idempotent_skip_existing_price(self, mock_sleep, mock_scraper, store, commits):
        """If item already has scraped_price, don't overwrite."""
        mock_scraper.scrape_product.return_value = {
            "_status": 200, "title": "T", "images": "i",
            "price": 200, "features": "F",
        }
        processor = make_processor(mock_scraper, store, commits)
        items = [{"asin": "B0T", "scraping_attempts": 0, "scraped_price": 100}]
        result = processor.process(items)
        assert "scraped_price" not in store["B0T"]["data"]


class TestFailedScrape:
    @patch("src.processor.batch_processor.time.sleep")
    def test_404_marks_dead(self, mock_sleep, mock_scraper, store, commits):
        mock_scraper.scrape_product.return_value = {"_status": 404}
        processor = make_processor(mock_scraper, store, commits)
        items = [{"asin": "B0GONE", "scraping_attempts": 2}]
        result = processor.process(items)
        assert result.not_found_404 == 1
        assert store["B0GONE"]["meta"]["attempts"] == PERMANENT_FAIL_ATTEMPTS

    @patch("src.processor.batch_processor.time.sleep")
    def test_network_error_increments_attempts(self, mock_sleep, mock_scraper, store, commits):
        mock_scraper.scrape_product.return_value = None
        processor = make_processor(mock_scraper, store, commits)
        items = [{"asin": "B0ERR", "scraping_attempts": 5}]
        result = processor.process(items)
        assert result.failed == 1
        assert store["B0ERR"]["meta"]["attempts"] == 6
        assert store["B0ERR"]["meta"]["status"] == "error"


class TestMarkFailuresFlag:
    @patch("src.processor.batch_processor.time.sleep")
    def test_no_mark_failures_on_network_error(self, mock_sleep, mock_scraper, store, commits):
        """With mark_failures=False, network errors don't increment attempts."""
        mock_scraper.scrape_product.return_value = None
        processor = make_processor(mock_scraper, store, commits, mark_failures=False)
        items = [{"asin": "B0ERR", "scraping_attempts": 3}]
        processor.process(items)
        assert store["B0ERR"]["meta"]["attempts"] == 3  # unchanged
        assert store["B0ERR"]["meta"]["status"] == "error_no_mark"

    @patch("src.processor.batch_processor.time.sleep")
    def test_no_mark_on_missing_price(self, mock_sleep, mock_scraper, store, commits):
        """With mark_failures=False, missing price doesn't increment attempts."""
        mock_scraper.scrape_product.return_value = {
            "_status": 200, "title": "T", "images": "i",
            "price": None, "features": "F",
        }
        processor = make_processor(mock_scraper, store, commits, mark_failures=False)
        items = [{"asin": "B0NP", "scraping_attempts": 2}]
        processor.process(items)
        assert store["B0NP"]["meta"]["attempts"] == 2  # unchanged

    @patch("src.processor.batch_processor.time.sleep")
    def test_mark_failures_increments_on_missing_price(self, mock_sleep, mock_scraper, store, commits):
        """With mark_failures=True (default), missing price DOES increment."""
        mock_scraper.scrape_product.return_value = {
            "_status": 200, "title": "T", "images": "i",
            "price": None, "features": "F",
        }
        processor = make_processor(mock_scraper, store, commits, mark_failures=True)
        items = [{"asin": "B0NP", "scraping_attempts": 2}]
        processor.process(items)
        assert store["B0NP"]["meta"]["attempts"] == 3  # incremented


class TestPriceOnlyMode:
    @patch("src.processor.batch_processor.time.sleep")
    def test_price_only_skips_description_fields(self, mock_sleep, mock_scraper, store, commits):
        mock_scraper.scrape_product.return_value = {
            "_status": 200, "title": "T", "images": "i",
            "price": 42, "features": "F",
        }
        processor = make_processor(mock_scraper, store, commits, price_only=True)
        items = [{"asin": "B0PO", "scraping_attempts": 0}]
        processor.process(items)
        assert "amazon_description" not in store["B0PO"]["data"]
        assert store["B0PO"]["data"]["scraped_price"] == 42


class TestBatchBehavior:
    @patch("src.processor.batch_processor.time.sleep")
    def test_commit_batching(self, mock_sleep, mock_scraper, store, commits):
        mock_scraper.scrape_product.return_value = {
            "_status": 200, "title": "T", "images": "i",
            "price": 10, "features": "F",
        }
        processor = make_processor(mock_scraper, store, commits, commit_batch_size=3)
        items = [{"asin": f"B{i}", "scraping_attempts": 0} for i in range(7)]
        processor.process(items)
        assert len(commits) == 3  # at 3, 6, and final

    @patch("src.processor.batch_processor.time.sleep")
    def test_delay_between_requests(self, mock_sleep, mock_scraper, store, commits):
        mock_scraper.scrape_product.return_value = {
            "_status": 200, "title": "T", "images": "i",
            "price": 10, "features": "F",
        }
        processor = make_processor(mock_scraper, store, commits)
        processor._delay = 2.5
        items = [{"asin": f"B{i}", "scraping_attempts": 0} for i in range(3)]
        processor.process(items)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(2.5)

    @patch("src.processor.batch_processor.time.sleep")
    def test_skips_empty_asin(self, mock_sleep, mock_scraper, store, commits):
        processor = make_processor(mock_scraper, store, commits)
        items = [{"asin": "", "scraping_attempts": 0}]
        result = processor.process(items)
        assert result.skipped == 1
        mock_scraper.scrape_product.assert_not_called()


class TestScrapeResult:
    def test_success_rate(self):
        r = ScrapeResult(total=10, success=7)
        assert r.success_rate == 70.0

    def test_zero_total(self):
        assert ScrapeResult().success_rate == 0.0

    def test_summary_keys(self):
        s = ScrapeResult(total=5, success=3, failed=1, not_found_404=1).summary()
        assert s["success_rate"] == "60.0%"
        assert "no_price" in s


class TestMixedBatch:
    @patch("src.processor.batch_processor.time.sleep")
    def test_realistic_mixed_batch(self, mock_sleep, mock_scraper, store, commits):
        mock_scraper.scrape_product.side_effect = [
            {"_status": 200, "title": "OK", "images": "i", "price": 50, "features": "f"},
            {"_status": 404},
            None,
            {"_status": 200, "title": "P", "images": "i", "price": None, "features": "f"},
        ]
        processor = make_processor(mock_scraper, store, commits)
        items = [
            {"asin": "B0OK", "scraping_attempts": 0},
            {"asin": "B0GONE", "scraping_attempts": 1},
            {"asin": "B0ERR", "scraping_attempts": 2},
            {"asin": "B0NP", "scraping_attempts": 3},
        ]
        result = processor.process(items)
        assert result.success == 2  # B0OK (full) + B0NP (fields written despite no price)
        assert result.not_found_404 == 1
        assert result.failed == 1  # B0ERR (network error)
        assert store["B0GONE"]["meta"]["attempts"] == 99
        assert store["B0ERR"]["meta"]["attempts"] == 3
        assert store["B0NP"]["meta"]["attempts"] == 4  # price=None increments
