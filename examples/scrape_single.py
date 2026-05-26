#!/usr/bin/env python3
"""
Example: Scrape a single Amazon product by ASIN.

Usage:
    python examples/scrape_single.py B08N5WRWNW
    python examples/scrape_single.py B08N5WRWNW --domain com
"""
import sys
import os
import argparse
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scraper import AmazonScraper, UserAgentRotator


def main():
    parser = argparse.ArgumentParser(description="Scrape an Amazon product by ASIN")
    parser.add_argument("asin", help="Amazon ASIN to scrape (e.g. B08N5WRWNW)")
    parser.add_argument("--domain", default="es", help="Amazon domain: es, com, co.uk, de, fr, it (default: es)")
    args = parser.parse_args()

    rotator = UserAgentRotator()
    scraper = AmazonScraper(user_agents=rotator.get_all(), domain=args.domain)

    print(f"Scraping ASIN {args.asin} from amazon.{args.domain}...")
    result = scraper.scrape_product(args.asin)

    if result is None:
        print("ERROR: Network/timeout error. No response received.")
        sys.exit(1)

    if result["_status"] == 404:
        print(f"NOT FOUND: ASIN {args.asin} does not exist on amazon.{args.domain}")
        sys.exit(1)

    if result["_status"] == 503:
        print("BLOCKED: Amazon returned 503 (bot detection). Try again later.")
        sys.exit(1)

    print(f"\nTitle:    {result['title']}")
    print(f"Price:    {result['price']}")
    print(f"Images:   {len(result['images'].split('|')) if result['images'] else 0}")
    print(f"Features: {len(result['features'].splitlines()) if result['features'] else 0}")

    print(f"\n{json.dumps(result, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
