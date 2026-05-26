"""
CLI entry point for batch scraping.

Usage:
    python -m src.cli.scrape_batch --limit 50 --delay 3
    python -m src.cli.scrape_batch --a2z A2Z33838,A2Z33839 --limit 100
    python -m src.cli.scrape_batch --price-only --limit 200
    python -m src.cli.scrape_batch --no-mark-failures --limit 100
    python -m src.cli.scrape_batch --dry-run

Mirrors the production batch system (amazon_scraping.py) with:
- Priority queue construction (scraping_attempts ASC, last_scraped_at ASC NULLS FIRST)
- Configurable filters (--a2z, --price-only)
- Rate limiting (--delay)
- Batch commit size (--commit-batch)
- Dry-run mode (builds queue and prints stats, no scraping)
- --no-mark-failures: errors don't increment attempts (useful for test runs)
- JSON results file output
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..scraper.amazon_scraper import AmazonScraper
from ..scraper.user_agents import UserAgentManager
from ..queue.scrape_queue import ScrapeQueue, ScrapeItem
from ..processor.batch_processor import BatchProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch Amazon product scraper with priority queue"
    )
    parser.add_argument("--limit", type=int, default=50,
                        help="Max items to scrape (default: 50)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds between requests (default: 2.0)")
    parser.add_argument("--commit-batch", type=int, default=10,
                        help="Commit every N items (default: 10)")
    parser.add_argument("--a2z", type=str, default=None,
                        help="Comma-separated batch_id codes to filter (e.g. A2Z48030,A2Z47750)")
    parser.add_argument("--price-only", action="store_true",
                        help="Only scrape items missing price")
    parser.add_argument("--no-mark-failures", action="store_true",
                        help="Don't increment scraping_attempts on errors or missing price")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build queue and show stats without scraping")
    parser.add_argument("--ua-file", type=str, default=None,
                        help="Path to user agents JSON file")
    parser.add_argument("--output", type=str, default=None,
                        help="Path to write JSON results")
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    load_items: Callable[[], list[ScrapeItem]],
    save_result: Callable[[str, dict, dict], None],
    commit: Callable[[], None] | None = None,
):
    """
    Main batch scraping entrypoint.

    Args:
        args: Parsed CLI args.
        load_items: Callable returning list of ScrapeItem (from DB, file, etc.).
        save_result: Callback(asin, scraped_data, meta) for persistence.
        commit: Optional commit callback.
    """
    raw_items = load_items()
    logger.info("Loaded %d items from source", len(raw_items))

    batch_id = args.a2z.split(",")[0].strip() if args.a2z else None

    queue = ScrapeQueue(items=raw_items)

    queue_stats = queue.get_stats()
    logger.info("Queue stats: %s", json.dumps(queue_stats, indent=2))

    prioritized = queue.get_pending(
        limit=args.limit,
        price_only=args.price_only,
        batch_id=batch_id,
    )
    logger.info("Queue built with %d items", len(prioritized))

    if args.dry_run:
        logger.info("DRY RUN - showing queue preview")
        for i, item in enumerate(prioritized[:10], 1):
            logger.info(
                "  [%d] LPN=%s ASIN=%s attempts=%d price=%s last=%s",
                i, item.lpn, item.asin, item.scraping_attempts,
                "YES" if item.has_price else "NO",
                item.last_scraped_at,
            )
        if len(prioritized) > 10:
            logger.info("  ... and %d more", len(prioritized) - 10)
        logger.info("DRY RUN - no changes made")
        return

    ua_manager = UserAgentManager(source_path=args.ua_file)
    scraper = AmazonScraper(user_agents=ua_manager.get_all())

    mark_failures = not args.no_mark_failures

    processor = BatchProcessor(
        scraper=scraper,
        on_result=save_result,
        on_commit=commit,
        delay_seconds=args.delay,
        commit_batch_size=args.commit_batch,
        price_only=args.price_only,
        mark_failures=mark_failures,
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
        for item in prioritized
    ]

    result = processor.process(item_dicts)

    summary = result.summary()
    summary["timestamp"] = datetime.now().isoformat()
    summary["queue_stats"] = queue_stats
    summary["mark_failures"] = mark_failures

    logger.info("=" * 60)
    logger.info("RESULTS: %d OK / %d FAIL / %d total",
                result.success, result.failed, result.total)
    logger.info("=" * 60)
    logger.info(json.dumps(summary, indent=2))

    if args.output:
        Path(args.output).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        logger.info("Results written to %s", args.output)


def main():
    """Demo main with mock data source."""
    args = parse_args()

    results_store: dict[str, dict] = {}

    def mock_load_items() -> list[ScrapeItem]:
        return [
            ScrapeItem(lpn="LPN001", asin="B0EXAMPLE1"),
            ScrapeItem(
                lpn="LPN002", asin="B0EXAMPLE2", scraping_attempts=1,
                amazon_description="Existing title",
                image_urls="img.jpg",
                amazon_features="Features here",
            ),
            ScrapeItem(lpn="LPN003", asin="B0EXAMPLE3", scraping_attempts=3),
        ]

    def mock_save_result(asin: str, data: dict, meta: dict):
        results_store[asin] = {"data": data, "meta": meta}
        logger.info("Saved result for %s: status=%s", asin, meta.get("status"))

    run(args, load_items=mock_load_items, save_result=mock_save_result)


if __name__ == "__main__":
    main()
