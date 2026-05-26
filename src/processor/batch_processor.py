"""
Batch scraping processor.

Orchestrates scraping of a list of items with production-grade behavior:

1. Scrapes each ASIN via AmazonScraper
2. Applies results with IDEMPOTENT writes — never overwrites existing data:
   - Only sets amazon_description if currently empty
   - Only sets image_urls if currently empty
   - Only sets scraped_price if currently None
   - Only sets amazon_features if currently empty
3. Handles HTTP statuses:
   - 200 with data: apply idempotent writes, track what changed
   - 200 without price: data saved, attempts incremented (partial scrape)
   - 404: permanently mark as dead (attempts=99)
   - None (network error): increment attempts if mark_failures is enabled
4. mark_failures flag: when disabled (--no-mark-failures), network errors
   and missing prices do NOT increment attempts — useful for test runs
5. Configurable delay, commit batching, price-only mode, dry-run
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..scraper.amazon_scraper import AmazonScraper

logger = logging.getLogger(__name__)

PERMANENT_FAIL_ATTEMPTS = 99


@dataclass
class ScrapeResult:
    """Aggregate result tracking for a batch scrape run."""
    total: int = 0
    success: int = 0
    failed: int = 0
    not_found_404: int = 0
    no_price: int = 0
    skipped: int = 0

    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total > 0 else 0.0

    def summary(self) -> dict:
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "not_found_404": self.not_found_404,
            "no_price": self.no_price,
            "skipped": self.skipped,
            "success_rate": f"{self.success_rate:.1f}%",
        }


class BatchProcessor:
    """
    Processes a queue of items through AmazonScraper.

    Database-agnostic: uses callbacks for persisting results and committing.
    Mirrors the production system where the processor coordinates
    the scraping loop but delegates persistence to the caller.

    Key production pattern: on_result receives both the scraped data
    AND the current item state, so the caller can implement idempotent
    writes (only update fields that are currently empty).
    """

    def __init__(
        self,
        scraper: AmazonScraper,
        on_result: Callable[[str, dict, dict], None],
        on_commit: Optional[Callable[[], None]] = None,
        delay_seconds: float = 2.0,
        commit_batch_size: int = 10,
        price_only: bool = False,
        mark_failures: bool = True,
    ):
        """
        Args:
            scraper: AmazonScraper instance.
            on_result: Callback(asin, scraped_data, meta).
                meta contains: status, attempts, fields_updated, price_saved.
            on_commit: Called every commit_batch_size items.
            delay_seconds: Sleep between requests.
            commit_batch_size: Items between commits.
            price_only: Only update price field.
            mark_failures: If False, errors don't increment attempts
                (production --no-mark-failures flag).
        """
        self._scraper = scraper
        self._on_result = on_result
        self._on_commit = on_commit
        self._delay = delay_seconds
        self._commit_batch_size = commit_batch_size
        self._price_only = price_only
        self._mark_failures = mark_failures

    def process(self, items: list[dict]) -> ScrapeResult:
        """
        Process a list of items.

        Each item dict must have:
            - "asin": str
            - "scraping_attempts": int
        And optionally (for idempotent write logic):
            - "amazon_description": str or None (existing title)
            - "image_urls": str or None (existing images)
            - "scraped_price": int or None (existing price)
            - "amazon_features": str or None (existing features)
        """
        result = ScrapeResult(total=len(items))

        for idx, item in enumerate(items, 1):
            asin = item.get("asin", "")
            current_attempts = item.get("scraping_attempts", 0)

            if not asin:
                result.skipped += 1
                continue

            logger.info("[%d/%d] Scraping ASIN: %s (attempt %d)",
                        idx, result.total, asin, current_attempts + 1)

            scraped = self._scraper.scrape_product(asin)

            if scraped is None:
                # Network/timeout error
                if self._mark_failures:
                    new_attempts = current_attempts + 1
                    self._on_result(asin, {}, {
                        "status": "error",
                        "attempts": new_attempts,
                    })
                    logger.warning("FAIL ASIN %s - attempt %d", asin, new_attempts)
                else:
                    self._on_result(asin, {}, {
                        "status": "error_no_mark",
                        "attempts": current_attempts,
                    })
                    logger.warning("FAIL ASIN %s - no changes (mark_failures=False)", asin)
                result.failed += 1

            elif scraped.get("_status") == 404:
                result.not_found_404 += 1
                self._on_result(asin, {}, {
                    "status": "not_found",
                    "attempts": PERMANENT_FAIL_ATTEMPTS,
                })
                logger.warning("ASIN %s -> 404, marked attempts=%d", asin, PERMANENT_FAIL_ATTEMPTS)

            elif scraped.get("_status") == 200:
                self._apply_scraped_data(item, scraped, result)

            if self._on_commit and idx % self._commit_batch_size == 0:
                logger.info("Committing batch at item %d", idx)
                self._on_commit()

            if idx < result.total:
                time.sleep(self._delay)

        if self._on_commit:
            self._on_commit()

        logger.info("Batch complete: %s", result.summary())
        return result

    def _apply_scraped_data(self, item: dict, scraped: dict, result: ScrapeResult):
        """
        Apply scraped data with IDEMPOTENT writes.

        Production pattern: only write fields that are currently empty.
        This prevents overwriting manually corrected data.
        """
        asin = item["asin"]
        current_attempts = item.get("scraping_attempts", 0)
        fields_updated = []
        data = {}

        if not self._price_only:
            if scraped.get("title") and not item.get("amazon_description"):
                data["amazon_description"] = scraped["title"]
                fields_updated.append("amazon_description")

            if scraped.get("images") and not item.get("image_urls"):
                data["image_urls"] = scraped["images"]
                fields_updated.append("image_urls")

            if scraped.get("features") and not item.get("amazon_features"):
                data["amazon_features"] = scraped["features"]
                fields_updated.append("amazon_features")

        price = scraped.get("price")
        price_saved = False
        if price is not None and item.get("scraped_price") is None:
            data["scraped_price"] = price
            fields_updated.append("scraped_price")
            price_saved = True

        new_attempts = current_attempts
        if price is None and self._mark_failures and not self._price_only:
            new_attempts = current_attempts + 1

        if price_saved:
            result.success += 1
            logger.info("OK   ASIN %s - price=%s", asin, price)
        elif fields_updated:
            result.success += 1
            logger.info("OK   ASIN %s - fields: %s", asin, fields_updated)
        elif price is None:
            result.no_price += 1
            result.failed += 1
            logger.info("SKIP ASIN %s - no price on Amazon", asin)
        else:
            result.skipped += 1
            logger.info("SKIP ASIN %s - no new data to write", asin)

        self._on_result(asin, data, {
            "status": "success" if fields_updated else ("no_price" if price is None else "skip"),
            "attempts": new_attempts,
            "fields_updated": fields_updated,
            "price_saved": price_saved,
        })
