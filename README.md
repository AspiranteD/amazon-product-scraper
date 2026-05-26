# Amazon Product Scraper

Production-grade Amazon ES product scraper that extracts titles, prices, images, and features from product pages by ASIN. Built for batch processing thousands of items with a priority queue, dead-product detection, idempotent writes, and user-agent rotation.

Extracted from a real inventory management system that processes truckloads of returned Amazon merchandise.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        CLI Layer                             │
│  scrape_batch.py (argparse: --limit, --dry-run, --delay,    │
│                   --batch-id, --price-only, --no-mark-fail)  │
└──────────────┬───────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────┐
│                   BatchProcessor                             │
│  • Orchestrates queue → scrape → apply loop                  │
│  • Configurable delay between requests                       │
│  • 404 → mark dead (attempts=99)                             │
│  • Network error → increment attempts                        │
│  • Success → idempotent writes (only fill empty fields)      │
│  • Price None → increment attempts (exists but no price)     │
│  • Progress callback + batch commit pattern                  │
└──────┬───────────────────┬───────────────────────────────────┘
       │                   │
┌──────▼──────┐    ┌───────▼────────┐
│ ScrapeQueue │    │ AmazonScraper  │
│             │    │                │
│ Priority:   │    │ • GET amazon   │
│  attempts↑  │    │   .es/dp/ASIN  │
│  nulls first│    │ • Parse HTML   │
│             │    │ • Multi-select │
│ Filters:    │    │   price parse  │
│  • has ASIN │    │ • Regex hiRes  │
│  • available│    │   images       │
│  • < max    │    │ • Dedup images │
│    attempts │    │ • Fallback     │
│  • price    │    │   selectors    │
│    only     │    │ • 404 detect   │
│  • batch_id │    │ • Timeout 10s  │
└─────────────┘    └───────┬────────┘
                           │
                   ┌───────▼────────┐
                   │ UserAgent      │
                   │ Manager        │
                   │                │
                   │ • 6 defaults   │
                   │ • File/DB load │
                   │ • Random rot.  │
                   │ • Usage stats  │
                   │ • Hot reload   │
                   └────────────────┘
```

## Key Design Decisions

| Decision | Why |
|---|---|
| **Priority queue** (attempts ASC, NULLS FIRST) | Never-scraped items always go first; failed items are retried later with lower priority |
| **404 dead-marking** (attempts=99) | Products removed from Amazon are permanently excluded without blocking the queue |
| **Idempotent writes** | Only fill empty fields — re-running is safe, never overwrites existing data |
| **Multi-selector price parsing** | Amazon uses different container IDs across page layouts; trying 4 selectors covers edge cases |
| **hiRes regex + landingImage fallback** | The `"hiRes":"url"` pattern in JavaScript gives full-resolution images; `#landingImage` is the fallback for simpler pages |
| **dict.fromkeys() dedup** | Preserves insertion order while removing duplicate image URLs — cleaner than `set()` |
| **User-agent rotation** | Reduces detection risk; supports file-based or DB-based loading with graceful fallback |
| **Price as integer** | Whole euros only (production domain); stripping `.`, `,`, `€` handles locale formatting |
| **Configurable mark_failures** | Some runs are exploratory — `--no-mark-failures` prevents polluting attempt counts |

## Project Structure

```
src/
  scraper/
    amazon_scraper.py     # Core scraper: GET + BeautifulSoup parsing
    user_agents.py        # User agent manager with rotation and stats
  queue/
    scrape_queue.py       # Priority queue with filtering and sorting
  processor/
    batch_processor.py    # Batch orchestrator with all business logic
  cli/
    scrape_batch.py       # CLI entry point with argparse
data/                     # Input data (JSON files with items)
tests/                    # 80+ unit tests with mocked HTTP
examples/
  scrape_single.py        # Scrape one ASIN
  batch_scrape.py         # Batch scrape from code
```

## Installation

```bash
git clone https://github.com/yourusername/amazon-product-scraper.git
cd amazon-product-scraper
pip install -r requirements.txt
```

## Usage

### Single product

```bash
python examples/scrape_single.py B07GQSS8RH
```

### Batch CLI

```bash
# Scrape up to 50 items with 2s delay
python -m src.cli.scrape_batch --data data/items.json --limit 50

# Dry run (list pending without scraping)
python -m src.cli.scrape_batch --data data/items.json --dry-run

# Price-only mode for a specific batch
python -m src.cli.scrape_batch --data data/items.json --price-only --batch-id A2Z48030

# Don't mark failures (exploratory run)
python -m src.cli.scrape_batch --data data/items.json --no-mark-failures --delay 3.0
```

### From code

```python
from src.scraper.amazon_scraper import AmazonScraper
from src.scraper.user_agents import UserAgentManager
from src.queue.scrape_queue import ScrapeQueue, ScrapeItem
from src.processor.batch_processor import BatchProcessor, BatchConfig

# Setup
ua_manager = UserAgentManager()
scraper = AmazonScraper(ua_manager.get_all())

# Build queue
items = [ScrapeItem(lpn="LPN-001", asin="B07GQSS8RH")]
queue = ScrapeQueue(items)

# Run batch
config = BatchConfig(delay=2.0, limit=10)
processor = BatchProcessor(scraper, queue, config)
summary = processor.run()
print(f"OK: {summary['ok']}, FAIL: {summary['fail']}")
```

### Input data format

```json
[
  {
    "lpn": "LPN-001",
    "asin": "B07GQSS8RH",
    "amazon_description": null,
    "image_urls": null,
    "amazon_features": null,
    "scraped_price": null,
    "scraping_attempts": 0,
    "batch_id": "A2Z48030",
    "available": true
  }
]
```

## Running Tests

```bash
python -m pytest tests/ -v --tb=short
```

## Tech Stack

- **Python 3.11+**
- **requests** — HTTP client with timeout and error handling
- **BeautifulSoup4** — HTML parsing with CSS selectors
- **pytest** — Testing framework with mocking

## Domain Context

This scraper was built for a returns-processing business that receives truckloads of Amazon merchandise. Each item has a unique LPN (License Plate Number) and an ASIN. The scraper enriches inventory records with Amazon product data to enable pricing, cataloging, and resale operations.

Field mapping:
- `lpn` — unique item identifier in the warehouse
- `asin` — Amazon Standard Identification Number
- `amazon_description` — product title from Amazon
- `amazon_features` — bullet-point features
- `image_urls` — pipe-separated hi-res image URLs (up to 8)
- `scraped_price` — integer price in euros
- `scraping_attempts` — retry counter (99 = dead product)
- `last_scraped_at` — timestamp of last scrape attempt
- `batch_id` — truckload identifier for batch filtering
