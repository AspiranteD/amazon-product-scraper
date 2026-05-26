"""
Batch scraping processor with production-grade behavior.

Handles: 200 (success/partial), 404 (permanent fail at attempts=99),
None (network error, increment attempts). Configurable delay,
commit batching, price-only mode.
"""
import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

from ..scraper.amazon_scraper import AmazonScraper

logger = logging.getLogger(__name__)

PERMANENT_FAIL_ATTEMPTS = 99


@dataclass
class ScrapeResult:
    total: int = 0
    success: int = 0
    failed: int = 0
    not_found_404: int = 0
    no_price: int = 0
    skipped: int = 0

    @property
    def success_rate(self):
        return (self.success / self.total * 100) if self.total > 0 else 0.0

    def summary(self):
        return {
            "total": self.total, "success": self.success, "failed": self.failed,
            "not_found_404": self.not_found_404, "no_price": self.no_price,
            "skipped": self.skipped, "success_rate": f"{self.success_rate:.1f}%",
        }


class BatchProcessor:
    def __init__(self, scraper, on_result, on_commit=None, delay_seconds=2.0, commit_batch_size=10, price_only=False):
        self._scraper = scraper
        self._on_result = on_result
        self._on_commit = on_commit
        self._delay = delay_seconds
        self._commit_batch_size = commit_batch_size
        self._price_only = price_only

    def process(self, items):
        result = ScrapeResult(total=len(items))
        for idx, item in enumerate(items, 1):
            asin = item.get("asin", "")
            current_attempts = item.get("scraping_attempts", 0)
            if not asin:
                result.skipped += 1
                continue

            scraped = self._scraper.scrape_product(asin)

            if scraped is None:
                result.failed += 1
                self._on_result(asin, {}, {"status": "error", "attempts": current_attempts + 1})
            elif scraped.get("_status") == 404:
                result.not_found_404 += 1
                self._on_result(asin, {}, {"status": "not_found", "attempts": PERMANENT_FAIL_ATTEMPTS})
            elif scraped.get("_status") == 200:
                has_price = scraped.get("price") is not None
                new_attempts = current_attempts + (0 if has_price else 1)
                if not has_price:
                    result.no_price += 1
                if self._price_only:
                    data = {"price": scraped.get("price")} if has_price else {}
                else:
                    data = {"title": scraped.get("title", ""), "images": scraped.get("images", ""),
                            "price": scraped.get("price"), "features": scraped.get("features", "")}
                self._on_result(asin, data, {"status": "success" if has_price else "partial", "attempts": new_attempts})
                if has_price:
                    result.success += 1
                else:
                    result.failed += 1

            if self._on_commit and idx % self._commit_batch_size == 0:
                self._on_commit()
            if idx < result.total:
                time.sleep(self._delay)

        if self._on_commit:
            self._on_commit()
        return result
