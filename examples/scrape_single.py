"""
Example: Scrape a single Amazon product by ASIN.

Usage:
    python examples/scrape_single.py B07GQSS8RH
    python examples/scrape_single.py B0BN8Y5GNK --verbose
"""
import argparse
import json
import logging
import sys

sys.path.insert(0, ".")

from src.scraper.amazon_scraper import AmazonScraper
from src.scraper.user_agents import UserAgentManager


def main():
    parser = argparse.ArgumentParser(description="Scrape a single Amazon product")
    parser.add_argument("asin", help="The ASIN to scrape")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    ua_manager = UserAgentManager()
    scraper = AmazonScraper(ua_manager.get_all())

    print(f"\nScraping ASIN: {args.asin}")
    print("-" * 40)

    result = scraper.scrape_product(args.asin)

    if result is None:
        print("ERROR: Network error or timeout")
        return 1

    if result.get("_status") == 404:
        print("NOT FOUND: Product does not exist on Amazon")
        return 1

    print(f"Title:    {result.get('title', 'N/A')}")
    print(f"Price:    {result.get('price', 'N/A')} EUR")
    print(f"Images:   {len(result.get('images', '').split('|'))} found")
    print(f"Features: {len(result.get('features', '').split(chr(10)))} found")
    print(f"\nFull response:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
