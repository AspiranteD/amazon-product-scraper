"""
Example: Batch scrape multiple products from a JSON file.

Usage:
    python examples/batch_scrape.py
    python examples/batch_scrape.py --data data/sample_items.json --limit 5
    python examples/batch_scrape.py --dry-run
"""
import json
import logging
import sys

sys.path.insert(0, ".")

from src.scraper.amazon_scraper import AmazonScraper
from src.scraper.user_agents import UserAgentManager
from src.queue.scrape_queue import ScrapeQueue, ScrapeItem
from src.processor.batch_processor import BatchProcessor, BatchConfig, ProcessResult

SAMPLE_ITEMS = [
    {"lpn": "LPN-001", "asin": "B07GQSS8RH"},
    {"lpn": "LPN-002", "asin": "B0BN8Y5GNK"},
    {"lpn": "LPN-003", "asin": "B09V3KXJPB"},
]


def progress_callback(current: int, total: int, result: ProcessResult):
    icon = "OK" if result.success else "FAIL"
    print(f"  [{current}/{total}] {icon} {result.lpn} -> {result.status}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    items = [
        ScrapeItem(lpn=row["lpn"], asin=row["asin"])
        for row in SAMPLE_ITEMS
    ]

    ua_manager = UserAgentManager()
    scraper = AmazonScraper(ua_manager.get_all())
    queue = ScrapeQueue(items)

    config = BatchConfig(
        delay=2.0,
        dry_run="--dry-run" in sys.argv,
        limit=int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None,
    )

    processor = BatchProcessor(
        scraper=scraper,
        queue=queue,
        config=config,
        on_progress=progress_callback,
    )

    print(f"\nBatch scraping {len(items)} items")
    print(f"Queue stats: {queue.get_stats()}")
    print("-" * 40)

    summary = processor.run()

    if not config.dry_run:
        print(f"\nResults: {summary['ok']} OK / {summary['fail']} FAIL / {summary['total']} total")

    print("\nUpdated items:")
    for item in items:
        if item.scraped_price is not None or item.amazon_description:
            print(f"  {item.lpn}: price={item.scraped_price}, desc={item.amazon_description[:50] if item.amazon_description else 'N/A'}...")


if __name__ == "__main__":
    main()
