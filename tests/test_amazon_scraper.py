"""Tests for AmazonScraper."""
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from src.scraper.amazon_scraper import AmazonScraper


@pytest.fixture
def scraper():
    return AmazonScraper(user_agents=["TestAgent/1.0", "TestAgent/2.0"])


class TestConstructor:
    def test_empty_user_agents_raises(self):
        with pytest.raises(ValueError):
            AmazonScraper(user_agents=[])

    def test_accepts_single_agent(self):
        s = AmazonScraper(user_agents=["Only/1.0"])
        assert s._get_headers()["User-Agent"] == "Only/1.0"


class TestGetTitle:
    def test_extracts_title(self, scraper):
        soup = BeautifulSoup('<span id="productTitle"> Samsung Galaxy </span>', "html.parser")
        assert scraper._get_title(soup) == "Samsung Galaxy"

    def test_missing_title(self, scraper):
        soup = BeautifulSoup("<div></div>", "html.parser")
        assert scraper._get_title(soup) == ""


class TestGetImages:
    def test_hires_regex(self, scraper):
        html = '"hiRes":"https://img1.jpg","x":"y","hiRes":"https://img2.jpg"'
        resp = MagicMock(); resp.text = html
        soup = BeautifulSoup(html, "html.parser")
        assert scraper._get_images(resp, soup) == ["https://img1.jpg", "https://img2.jpg"]

    def test_fallback_landing_image(self, scraper):
        html = '<img id="landingImage" src="https://fb.jpg" />'
        resp = MagicMock(); resp.text = html
        soup = BeautifulSoup(html, "html.parser")
        assert scraper._get_images(resp, soup) == ["https://fb.jpg"]

    def test_no_images(self, scraper):
        resp = MagicMock(); resp.text = "<div></div>"
        soup = BeautifulSoup("<div></div>", "html.parser")
        assert scraper._get_images(resp, soup) == []

    def test_deduplicates(self, scraper):
        html = '"hiRes":"https://dup.jpg","hiRes":"https://dup.jpg"'
        resp = MagicMock(); resp.text = html
        soup = BeautifulSoup(html, "html.parser")
        assert scraper._get_images(resp, soup) == ["https://dup.jpg"]

    def test_max_8(self, scraper):
        entries = ",".join(f'"hiRes":"https://i{i}.jpg"' for i in range(15))
        resp = MagicMock(); resp.text = entries
        soup = BeautifulSoup(entries, "html.parser")
        assert len(scraper._get_images(resp, soup)) == 8


class TestGetPrice:
    def test_core_price_display(self, scraper):
        html = '<div id="corePriceDisplay_desktop_feature_div"><span class="a-price-whole">149</span></div>'
        assert scraper._get_price(BeautifulSoup(html, "html.parser")) == 149

    def test_core_price_fallback(self, scraper):
        html = '<div id="corePrice_feature_div"><span class="a-price-whole">89</span></div>'
        assert scraper._get_price(BeautifulSoup(html, "html.parser")) == 89

    def test_strips_dots(self, scraper):
        html = '<div id="corePriceDisplay_desktop_feature_div"><span class="a-price-whole">1.299</span></div>'
        assert scraper._get_price(BeautifulSoup(html, "html.parser")) == 1299

    def test_strips_euro_sign(self, scraper):
        html = '<div id="corePriceDisplay_desktop_feature_div"><span class="a-price-whole">59€</span></div>'
        assert scraper._get_price(BeautifulSoup(html, "html.parser")) == 59

    def test_no_price(self, scraper):
        assert scraper._get_price(BeautifulSoup("<div></div>", "html.parser")) is None


class TestGetFeatures:
    def test_feature_bullets(self, scraper):
        html = '<div id="feature-bullets"><li>F1</li><li>F2</li></div>'
        assert scraper._get_features(BeautifulSoup(html, "html.parser")) == ["F1", "F2"]

    def test_overview_fallback(self, scraper):
        html = '<div id="productOverview"><li>O1</li></div>'
        assert scraper._get_features(BeautifulSoup(html, "html.parser")) == ["O1"]

    def test_max_10(self, scraper):
        lis = "".join(f"<li>F{i}</li>" for i in range(20))
        html = f'<div id="feature-bullets">{lis}</div>'
        assert len(scraper._get_features(BeautifulSoup(html, "html.parser"))) == 10

    def test_no_features(self, scraper):
        assert scraper._get_features(BeautifulSoup("<div></div>", "html.parser")) == []


class TestScrapeProduct:
    @patch("src.scraper.amazon_scraper.requests.get")
    def test_success(self, mock_get, scraper):
        html = '<span id="productTitle">Prod</span><div id="corePriceDisplay_desktop_feature_div"><span class="a-price-whole">99</span></div>'
        resp = MagicMock(status_code=200, content=html.encode(), text=html)
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp
        result = scraper.scrape_product("B0TEST")
        assert result["_status"] == 200
        assert result["title"] == "Prod"
        assert result["price"] == 99

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_404(self, mock_get, scraper):
        mock_get.return_value = MagicMock(status_code=404)
        assert scraper.scrape_product("B0GONE") == {"_status": 404}

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_network_error(self, mock_get, scraper):
        mock_get.side_effect = Exception("fail")
        assert scraper.scrape_product("B0ERR") is None

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_timeout(self, mock_get, scraper):
        from requests.exceptions import Timeout
        mock_get.side_effect = Timeout()
        assert scraper.scrape_product("B0TO") is None

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_missing_price_returns_200(self, mock_get, scraper):
        html = '<span id="productTitle">NoPriceItem</span>'
        resp = MagicMock(status_code=200, content=html.encode(), text=html)
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp
        result = scraper.scrape_product("B0NP")
        assert result["_status"] == 200
        assert result["price"] is None
