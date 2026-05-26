"""
Core Amazon product scraper.

Extracts product data (title, images, price, features) from Amazon ES
product pages given an ASIN. Faithfully ported from production code with
multi-selector price parsing, hiRes regex image extraction, dedup, and
robust error handling.
"""
import logging
import re
import random
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

AMAZON_BASE_URL = "https://www.amazon.es/dp/"
REQUEST_TIMEOUT = 10
MAX_IMAGES = 8
MAX_FEATURES = 10
IMAGE_SEPARATOR = "|"


class AmazonScraper:
    """Extracts product data from Amazon given an ASIN.

    Uses rotating user agents, multi-container price parsing, regex-based
    hi-res image extraction with fallback, and dual-selector feature
    extraction.
    """

    def __init__(self, user_agents: list[str]):
        if not user_agents:
            raise ValueError("user_agents list cannot be empty")
        self._user_agents = list(user_agents)
        self._rng = random.Random()

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._rng.choice(self._user_agents),
            "Accept-Language": "es-ES,es;q=0.9",
        }

    def scrape_product(self, asin: str) -> Optional[dict]:
        """Scrape an Amazon product page by ASIN.

        Returns:
            dict with keys: _status (int), title (str), images (str),
                 price (int|None), features (str)
            {"_status": 404} if the product page returns 404
            None if a network/timeout error occurs
        """
        url = f"{AMAZON_BASE_URL}{asin}"
        logger.info("Scraping ASIN %s (%s)", asin, url)

        try:
            response = requests.get(
                url, headers=self._get_headers(), timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 404:
                logger.warning("ASIN %s -> 404 Not Found", asin)
                return {"_status": 404}

            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            title = self._get_title(soup)
            images = self._get_images(response, soup)
            price = self._get_price(soup)
            features = self._get_features(soup)

            logger.info(
                "ASIN %s -> title=%s, images=%d, price=%s, features=%d items",
                asin,
                "yes" if title else "no",
                len(images),
                price,
                len(features),
            )

            return {
                "_status": 200,
                "title": title,
                "images": IMAGE_SEPARATOR.join(images[:MAX_IMAGES]),
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
    def _get_title(soup: BeautifulSoup) -> str:
        """Extract product title from span#productTitle."""
        tag = soup.find("span", id="productTitle")
        return tag.get_text(strip=True) if tag else ""

    @staticmethod
    def _get_images(response: requests.Response, soup: BeautifulSoup) -> list[str]:
        """Extract hi-res image URLs via regex, with landingImage fallback.

        Uses dict.fromkeys() for dedup while preserving order. Limited to 8.
        """
        try:
            images = re.findall(r'"hiRes":"(.+?)"', response.text)
            if not images:
                img_tag = soup.find(id="landingImage")
                images = [img_tag["src"]] if img_tag else []
            return list(dict.fromkeys(images))[:MAX_IMAGES]
        except Exception:
            logger.warning("Error extracting images")
            return []

    @staticmethod
    def _get_price(soup: BeautifulSoup) -> Optional[int]:
        """Extract price as integer (euros) trying multiple container selectors.

        Tries four selectors in sequence -- the same containers Amazon uses
        across different page layouts. Strips dots, commas, and euro sign
        before parsing to int.
        """
        containers = [
            soup.find(id="corePriceDisplay_desktop_feature_div"),
            soup.find(id="corePrice_feature_div"),
            soup.select_one("#corePriceDisplay_desktop_feature_div"),
            soup.select_one("#corePrice_feature_div"),
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
                        .replace("\u20ac", "")
                    )
                except ValueError:
                    continue
        return None

    @staticmethod
    def _get_features(soup: BeautifulSoup) -> list[str]:
        """Extract feature bullets, with productOverview fallback.

        Looks for #feature-bullets first (most common layout), falls back
        to #productOverview. Returns up to 10 features.
        """
        try:
            feature_list = soup.find("div", id="feature-bullets")
            if not feature_list:
                feature_list = soup.find("div", id="productOverview")
            if not feature_list:
                return []
            return [
                li.get_text(strip=True) for li in feature_list.find_all("li")
            ][:MAX_FEATURES]
        except Exception:
            logger.warning("Error extracting features")
            return []
