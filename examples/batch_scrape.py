"""
Example: Batch scrape multiple products using the full pipeline.

Demonstrates the priority queue + batch processor + idempotent writes
pattern from the production system.

Usage:
    python examples/batch_scrape.py
    python examples/batch_scrape.py --dry-run
"""
import json
import logging
import sys

sys.path.insert(0, ".")

from src.scraper.amazon_scraper import AmazonScraper
from src.scraper.user_agents import UserAgentManager
from src.queue.scrape_queue import ScrapeQueue, ScrapeItem
from src.processor.batch_processor import BatchProcessor

SAMPLE_ITEMS = [
    ScrapeItem(lpn="LPN-001", asin="B07GQSS8RH"),
    ScrapeItem(lpn="LPN-002", asin="B0BN8Y5GNK"),
    ScrapeItem(lpn="LPN-003", asin="B09V3KXJPB", scraping_attempts=2),
    ScrapeItem(
        lpn="LPN-004", asin="B08N5WRWNW",
        amazon_description="Already has title",
        image_urls="existing.jpg",
    ),
]


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    dry_run = "--dry-run" in sys.argv

    queue = ScrapeQueue(SAMPLE_ITEMS, max_attempts=10)
    print(f"\nQueue stats: {json.dumps(queue.get_stats(), indent=2)}")

    pending = queue.get_pending(limit=10)
    print(f"Pending items: {len(pending)}")

    if dry_run:
        for i, item in enumerate(pending, 1):
            print(f"  [{i}] LPN={item.lpn} ASIN={item.asin} "
                  f"attempts={item.scraping_attempts} missing={item.missing_fields}")
        print("DRY RUN - no scraping performed")
        return

    ua_manager = UserAgentManager()
    scraper = AmazonScraper(ua_manager.get_all())

    results_db: dict[str, dict] = {}

    def on_result(asin: str, data: dict, meta: dict):
        results_db[asin] = {"data": data, "meta": meta}
        status = meta.get("status", "unknown")
        fields = meta.get("fields_updated", [])
        print(f"  -> {asin}: {status} (fields: {fields})")

    commit_count = [0]
    def on_commit():
        commit_count[0] += 1

    processor = BatchProcessor(
        scraper=scraper,
        on_result=on_result,
        on_commit=on_commit,
        delay_seconds=3.0,
        commit_batch_size=5,
        mark_failures=True,
    )

    item_dicts = [
        {
            "asin": item.asin,
            "scraping_attempts": item.scraping_attempts,
            "amazon_description": item.amazon_description,
            "image_urls": item.image_urls,
            "scraped_price": item.scraped_price,
            "amazon_features": item.amazon_features,
        }
        for item in pending
    ]

    print(f"\nScraping {len(item_dicts)} items...")
    print("-" * 40)
    result = processor.process(item_dicts)

    print(f"\n{'=' * 40}")
    print(f"Results: {json.dumps(result.summary(), indent=2)}")
    print(f"Commits: {commit_count[0]}")


if __name__ == "__main__":
    main()
