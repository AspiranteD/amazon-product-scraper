"""
Priority queue for Amazon scraping jobs.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 10


@dataclass
class ScrapeItem:
    """Represents a physical item that needs Amazon scraping."""
    lpn: str
    asin: str
    amazon_description: Optional[str] = None
    amazon_features: Optional[str] = None
    image_urls: Optional[str] = None
    scraped_price: Optional[int] = None
    scraping_attempts: int = 0
    last_scraped_at: Optional[datetime] = None
    scraping_needs_manual: bool = False
    available: bool = True
    batch_id: Optional[str] = None

    @property
    def has_description(self) -> bool:
        return bool(self.amazon_description)

    @property
    def has_images(self) -> bool:
        return bool(self.image_urls)

    @property
    def has_features(self) -> bool:
        return bool(self.amazon_features)

    @property
    def has_price(self) -> bool:
        return self.scraped_price is not None

    @property
    def is_complete(self) -> bool:
        return self.has_description and self.has_images and self.has_features and self.has_price

    @property
    def is_dead(self) -> bool:
        return self.scraping_attempts >= 99

    @property
    def missing_fields(self) -> list[str]:
        missing = []
        if not self.has_description:
            missing.append("amazon_description")
        if not self.has_images:
            missing.append("image_urls")
        if not self.has_features:
            missing.append("amazon_features")
        if not self.has_price:
            missing.append("scraped_price")
        return missing


class ScrapeQueue:
    """Priority queue for scraping items."""

    def __init__(self, items: list[ScrapeItem], max_attempts: int = DEFAULT_MAX_ATTEMPTS):
        self._all_items = list(items)
        self._max_attempts = max_attempts

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @max_attempts.setter
    def max_attempts(self, value: int) -> None:
        self._max_attempts = value

    def get_pending(self, limit: Optional[int] = None, price_only: bool = False,
                    batch_id: Optional[str] = None, skip_attempt_limit: bool = False) -> list[ScrapeItem]:
        candidates = self._filter(price_only=price_only, batch_id=batch_id,
                                  skip_attempt_limit=skip_attempt_limit)
        candidates = self._sort(candidates)
        if limit and limit > 0:
            candidates = candidates[:limit]
        logger.info("Pending items: %d (filtered from %d total)",
                    len(candidates), len(self._all_items))
        return candidates

    def _filter(self, price_only: bool = False, batch_id: Optional[str] = None,
                skip_attempt_limit: bool = False) -> list[ScrapeItem]:
        result = []
        for item in self._all_items:
            if not item.asin or not item.asin.strip():
                continue
            if not item.available:
                continue
            if not skip_attempt_limit and item.scraping_attempts >= self._max_attempts:
                continue
            if price_only:
                if item.has_price:
                    continue
            else:
                if item.is_complete:
                    continue
            if batch_id is not None and item.batch_id != batch_id:
                continue
            result.append(item)
        return result

    @staticmethod
    def _sort(items: list[ScrapeItem]) -> list[ScrapeItem]:
        def sort_key(item: ScrapeItem):
            attempts = item.scraping_attempts
            ts = datetime.min if item.last_scraped_at is None else item.last_scraped_at
            return (attempts, ts)
        return sorted(items, key=sort_key)

    def get_stats(self) -> dict:
        total = len(self._all_items)
        has_asin = sum(1 for i in self._all_items if i.asin and i.asin.strip())
        available = sum(1 for i in self._all_items if i.available)
        complete = sum(1 for i in self._all_items if i.is_complete)
        dead = sum(1 for i in self._all_items if i.is_dead)
        pending = len(self.get_pending())
        over_max = sum(1 for i in self._all_items
                       if i.scraping_attempts >= self._max_attempts and not i.is_dead)
        missing_price = sum(1 for i in self._all_items if not i.has_price and i.available)
        missing_desc = sum(1 for i in self._all_items if not i.has_description and i.available)
        missing_images = sum(1 for i in self._all_items if not i.has_images and i.available)
        missing_features = sum(1 for i in self._all_items if not i.has_features and i.available)
        return {
            "total": total, "has_asin": has_asin, "available": available,
            "complete": complete, "dead": dead, "pending": pending,
            "over_max_attempts": over_max, "missing_price": missing_price,
            "missing_description": missing_desc, "missing_images": missing_images,
            "missing_features": missing_features,
        }

    def add_items(self, items: list[ScrapeItem]) -> None:
        self._all_items.extend(items)

    def remove_item(self, lpn: str) -> bool:
        for i, item in enumerate(self._all_items):
            if item.lpn == lpn:
                self._all_items.pop(i)
                return True
        return False

    def get_item(self, lpn: str) -> Optional[ScrapeItem]:
        for item in self._all_items:
            if item.lpn == lpn:
                return item
        return None

    def __len__(self) -> int:
        return len(self._all_items)
