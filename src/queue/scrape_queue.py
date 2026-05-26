"""
Priority queue for scraping jobs.

Implements the same prioritization logic from the production system:
- Items are sorted by (scraping_attempts ASC, last_scraped_at ASC NULLS FIRST)
- Items with fewer attempts go first (fresh items prioritized)
- Among same attempt count, older scrapes go first
- Items that have never been scraped (last_scraped_at=None) have highest priority within
  their attempt tier

Supports filtering by:
- id_a2z: filter items by truckload/manifest batch codes
- price_only: only re-scrape items that have all data except price
- max_attempts: skip items that have been attempted too many times (default: 98)
  Items with attempts=99 are permanently marked as unavailable (404s).
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ScrapeItem:
    """Represents an item pending scraping."""
    asin: str
    scraping_attempts: int = 0
    last_scraped_at: Optional[datetime] = None
    has_title: bool = False
    has_images: bool = False
    has_price: bool = False
    has_features: bool = False
    id_a2z: Optional[str] = None

    @property
    def needs_full_scrape(self) -> bool:
        return not (self.has_title and self.has_images and self.has_price and self.has_features)

    @property
    def needs_price_only(self) -> bool:
        return self.has_title and self.has_images and not self.has_price and self.has_features

    @property
    def is_permanently_failed(self) -> bool:
        return self.scraping_attempts >= 99

    @property
    def sort_key(self) -> tuple:
        never_scraped = 0 if self.last_scraped_at is None else 1
        ts = self.last_scraped_at or datetime.min
        return (self.scraping_attempts, never_scraped, ts)


class ScrapeQueue:
    def __init__(self, items, filter_a2z=None, price_only=False, max_attempts=98):
        self._raw_items = items
        self._filter_a2z = filter_a2z
        self._price_only = price_only
        self._max_attempts = max_attempts

    def build(self, limit=None):
        candidates = [i for i in self._raw_items if i.scraping_attempts <= self._max_attempts]
        if self._filter_a2z:
            candidates = [i for i in candidates if i.id_a2z and i.id_a2z in self._filter_a2z]
        if self._price_only:
            candidates = [i for i in candidates if i.needs_price_only]
        else:
            candidates = [i for i in candidates if i.needs_full_scrape]
        candidates.sort(key=lambda i: i.sort_key)
        if limit:
            candidates = candidates[:limit]
        return candidates

    def stats(self):
        total = len(self._raw_items)
        return {
            "total_items": total,
            "need_full_scrape": sum(1 for i in self._raw_items if i.needs_full_scrape),
            "need_price_only": sum(1 for i in self._raw_items if i.needs_price_only),
            "permanently_failed_404": sum(1 for i in self._raw_items if i.is_permanently_failed),
            "never_scraped": sum(1 for i in self._raw_items if i.last_scraped_at is None and not i.is_permanently_failed),
        }
