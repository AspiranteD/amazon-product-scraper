"""
Resilient Amazon product scraper.

Extracts product data (title, images, price, features) from Amazon product
pages given an ASIN. Handles user-agent rotation, HTTP error codes, timeouts,
and graceful degradation when individual fields are unavailable.
"""
import logging
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

AMAZON_DOMAINS = {
    "es": "https://www.amazon.es/dp/",
    "com": "https://www.amazon.com/dp/",
    "co.uk": "https://www.amazon.co.uk/dp/",
    "de": "https://www.amazon.de/dp/",
    "fr": "https://www.amazon.fr/dp/",
    "it": "https://www.amazon.it/dp/",
}


class AmazonScraper:
    """
    Extracts product data from Amazon given an ASIN.

    Features:
    - User-agent rotation to reduce blocking
    - Configurable domain (amazon.es, amazon.com, etc.)
    - HTTP status tracking (_status field)
    - Graceful handling of missing fields
    - Hi-res image extraction via regex on page source
    """

    def __init__(
        self,
        user_agents: list[str],
        domain: str = "es",
        timeout: int = 10,
        max_images: int = 8,
    ):
        import random
        self._user_agents = user_agents
        self._random = random
        self._base_url = AMAZON_DOMAINS.get(domain, AMAZON_DOMAINS["es"])
        self._timeout = timeout
        self._max_images = max_images

    def _get_headers(self) -> dict:
        return {
            "User-Agent": self._random.choice(self._user_agents),
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    def scrape_product(self, asin: str) -> dict | None:
        """
        Scrape a single Amazon product page.

        Returns:
            Dict with keys: _status, title, images, price, features.
            _status is the HTTP code (200, 404, etc.) or "error".
            Returns None only on network/timeout exceptions.
        """
        url = f"{self._base_url}{asin}"
        logger.info("Scraping ASIN %s (%s)", asin, url)

        try:
            response = requests.get(url, headers=self._get_headers(), timeout=self._timeout)

            if response.status_code == 404:
                logger.warning("ASIN %s -> 404 Not Found", asin)
                return {"_status": 404}

            if response.status_code == 503:
                logger.warning("ASIN %s -> 503 Service Unavailable (likely bot detection)", asin)
                return {"_status": 503}

            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            title = self._extract_title(soup)
            images = self._extract_images(response, soup)
            price = self._extract_price(soup)
            features = self._extract_features(soup)

            logger.info(
                "ASIN %s -> title=%s, images=%d, price=%s, features=%d",
                asin, bool(title), len(images), price, len(features),
            )

            return {
                "_status": 200,
                "title": title,
                "images": "|".join(images[:self._max_images]),
                "price": price,
                "features": "\n".join(features),
            }

        except requests.exceptions.Timeout:
            logger.error("Timeout scraping ASIN %s", asin)
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Connection error scraping ASIN %s", asin)
            return None
        except Exception as e:
            logger.error("Error scraping ASIN %s: %s", asin, e)
            return None

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        tag = soup.find("span", id="productTitle")
        return tag.get_text(strip=True) if tag else ""

    def _extract_images(self, response: requests.Response, soup: BeautifulSoup) -> list[str]:
        """Extract hi-res images from page source, falling back to landing image."""
        try:
            images = re.findall(r'"hiRes":"(.+?)"', response.text)
            if not images:
                img_tag = soup.find(id="landingImage")
                images = [img_tag["src"]] if img_tag else []
            return list(dict.fromkeys(images))[:self._max_images]
        except Exception:
            logger.warning("Error extracting images")
            return []

    @staticmethod
    def _extract_price(soup: BeautifulSoup) -> Optional[int]:
        """Extract price as integer (whole currency units), or None."""
        containers = [
            soup.find(id="corePriceDisplay_desktop_feature_div"),
            soup.find(id="corePrice_feature_div"),
        ]
        for container in containers:
            if not container:
                continue
            price_tag = container.find("span", class_="a-price-whole")
            if price_tag:
                try:
                    return int(
                        price_tag.text.strip()
                        .replace(".", "")
                        .replace(",", "")
                        .replace("€", "")
                        .replace("$", "")
                        .replace("£", "")
                    )
                except ValueError:
                    continue
        return None

    @staticmethod
    def _extract_features(soup: BeautifulSoup) -> list[str]:
        """Extract product feature bullet points."""
        try:
            feature_list = soup.find("div", id="feature-bullets")
            if not feature_list:
                feature_list = soup.find("div", id="productOverview")
            if not feature_list:
                return []
            return [li.get_text(strip=True) for li in feature_list.find_all("li")][:10]
        except Exception:
            logger.warning("Error extracting features")
            return []
