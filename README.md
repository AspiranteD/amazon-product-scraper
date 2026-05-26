# Amazon Product Scraper

Production-grade web scraper for Amazon ES (amazon.es) product pages. Designed for high-volume batch scraping of thousands of ASINs with built-in resilience, priority queuing, idempotent writes, and anti-rate-limiting.

## Architecture

```
src/
├── scraper/
│   ├── amazon_scraper.py     # Core scraper: title, images, price, features extraction
│   └── user_agents.py        # UA rotation with usage tracking and hot-reload
├── queue/
│   └── scrape_queue.py       # Priority queue with real field names (lpn, asin, etc.)
├── processor/
│   └── batch_processor.py    # Orchestrates batch scraping with idempotent writes
├── cli/
│   └── scrape_batch.py       # CLI entry point with full argument parsing
└── examples/
    ├── scrape_single.py      # Single ASIN scrape demo
    └── batch_scrape.py       # Full pipeline demo with queue + processor
```

## Key Technical Features

### Multi-Selector Price Parsing
Amazon A/B tests different price display components. The scraper tries four container selectors in sequence (`corePriceDisplay_desktop_feature_div`, `corePrice_feature_div`) to handle all variants. Prices are parsed as integer euros from `.a-price-whole` spans, stripping dots, commas, and euro signs.

### High-Resolution Image Extraction
Primary extraction uses regex to find `"hiRes":"<url>"` patterns in the raw page source (Amazon embeds image gallery data in inline scripts). Falls back to `#landingImage` src attribute. Images are deduplicated via `dict.fromkeys()` and capped at 8.

### Priority Queue System
`ScrapeQueue` implements production-level prioritization using real database field names:
- **Sort**: `(scraping_attempts ASC, last_scraped_at ASC NULLS FIRST)` — fresh items first, then oldest retries
- **Filters**: by `available` status, `batch_id` (truckload codes), `price_only` mode, `max_attempts` threshold, `skip_attempt_limit`
- **Dead marking**: items with `attempts=99` are permanently excluded (confirmed 404s)
- **Field tracking**: `has_description`, `has_images`, `has_features`, `has_price`, `is_complete`, `missing_fields`

### Idempotent Writes
The `BatchProcessor` implements the critical production pattern of **never overwriting existing data**:
- Only sets `amazon_description` if currently empty
- Only sets `image_urls` if currently empty
- Only sets `scraped_price` if currently `None`
- Only sets `amazon_features` if currently empty

This prevents accidental overwrites of manually corrected data.

### Intelligent Retry Logic
- **200 with price**: full success, no attempt increment
- **200 without price**: data saved but **attempts incremented** — item retried with lower priority
- **404**: permanently marked with `attempts=99`, never retried
- **Network error**: attempts incremented (or not, via `mark_failures` flag)

### `--no-mark-failures` Mode
Production flag that prevents incrementing `scraping_attempts` on errors. Useful for test runs or when scraping infrastructure issues are expected — items stay at original priority for the next real run.

### User Agent Rotation
- 6 built-in real Chrome/Firefox/Safari user agents
- External loading from JSON file
- Per-agent usage tracking (count + timestamp)
- Hot-reload without restart
- Graceful fallback on errors

### Batch Processing
- Configurable delay between requests (anti-rate-limiting)
- Commit batching: persistence callback every N items
- Database-agnostic callbacks: `on_result(asin, data, meta)` and `on_commit()`
- Price-only mode for targeted re-scraping
- Dry-run mode

## Usage

### Single Product
```python
from src.scraper import AmazonScraper, UserAgentManager

ua = UserAgentManager()
scraper = AmazonScraper(user_agents=ua.get_all())
result = scraper.scrape_product("B09V3KXJPB")
```

### Batch with Priority Queue
```python
from src.queue import ScrapeQueue, ScrapeItem
from src.processor import BatchProcessor

items = [ScrapeItem(lpn="LPN001", asin="B0ABC"), ...]
queue = ScrapeQueue(items, max_attempts=10)
pending = queue.get_pending(limit=100, price_only=True)

processor = BatchProcessor(
    scraper=scraper,
    on_result=lambda asin, data, meta: db.update(asin, data, meta),
    on_commit=lambda: db.commit(),
    delay_seconds=3.0,
    mark_failures=True,
)

result = processor.process([
    {"asin": item.asin, "scraping_attempts": item.scraping_attempts,
     "amazon_description": item.amazon_description,
     "scraped_price": item.scraped_price}
    for item in pending
])
```

### CLI
```bash
python -m src.cli.scrape_batch --limit 50 --delay 3
python -m src.cli.scrape_batch --a2z A2Z33838,A2Z33839 --limit 100
python -m src.cli.scrape_batch --price-only --limit 200
python -m src.cli.scrape_batch --dry-run
```

## Setup

```bash
pip install -r requirements.txt
```

## Tests

```bash
python -m pytest tests/ -v
```

74 tests covering: scraper parsing, image dedup, price selectors, queue sorting/filtering, idempotent writes, mark_failures flag, batch processing, mixed scenarios.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Integer prices (no decimals) | Amazon ES products in this domain are whole-euro; simplifies downstream |
| `attempts=99` for 404 | Convention: distinguishes confirmed-gone products from retry-eligible failures |
| Regex for hiRes images | More reliable than DOM — Amazon embeds gallery JSON in script tags |
| 8 image limit | Target marketplace (Wallapop) listing maximum |
| Idempotent writes | Never overwrite manually corrected data in production |
| `mark_failures` flag | Test runs shouldn't penalize items for infrastructure issues |
| `dict.fromkeys()` dedup | Preserves insertion order (Python 3.7+) while removing duplicates |
| Callback-based persistence | Keeps scraper database-agnostic; caller controls storage |
