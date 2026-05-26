"""Tests for AmazonScraper."""
import pytest
from unittest.mock import patch, MagicMock
from src.scraper.amazon_scraper import AmazonScraper


@pytest.fixture
def scraper():
    return AmazonScraper(user_agents=["TestAgent/1.0", "TestAgent/2.0"])


class TestGetTitle:
    def test_extracts_title(self, scraper):
        from bs4 import BeautifulSoup
        html = '<span id="productTitle"> Samsung Galaxy S24 Ultra </span>'
        soup = BeautifulSoup(html, "html.parser")
        assert scraper._get_title(soup) == "Samsung Galaxy S24 Ultra"

    def test_missing_title(self, scraper):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div></div>", "html.parser")
        assert scraper._get_title(soup) == ""


class TestGetImages:
    def test_extracts_hires_images(self, scraper):
        from bs4 import BeautifulSoup
        html = '<script>"hiRes":"https://img1.jpg","other":"x","hiRes":"https://img2.jpg"</script>'
        response = MagicMock()
        response.text = html
        soup = BeautifulSoup(html, "html.parser")
        images = scraper._get_images(response, soup)
        assert images == ["https://img1.jpg", "https://img2.jpg"]

    def test_fallback_to_landing_image(self, scraper):
        from bs4 import BeautifulSoup
        html = '<img id="landingImage" src="https://fallback.jpg" />'
        response = MagicMock()
        response.text = html
        soup = BeautifulSoup(html, "html.parser")
        images = scraper._get_images(response, soup)
        assert images == ["https://fallback.jpg"]

    def test_no_images(self, scraper):
        from bs4 import BeautifulSoup
        response = MagicMock()
        response.text = "<div>no images</div>"
        soup = BeautifulSoup("<div>no images</div>", "html.parser")
        images = scraper._get_images(response, soup)
        assert images == []

    def test_deduplicates_images(self, scraper):
        from bs4 import BeautifulSoup
        html = '"hiRes":"https://img.jpg","hiRes":"https://img.jpg","hiRes":"https://img.jpg"'
        response = MagicMock()
        response.text = html
        soup = BeautifulSoup(html, "html.parser")
        images = scraper._get_images(response, soup)
        assert images == ["https://img.jpg"]

    def test_max_8_images(self, scraper):
        from bs4 import BeautifulSoup
        entries = ",".join(f'"hiRes":"https://img{i}.jpg"' for i in range(15))
        html = f"<script>{entries}</script>"
        response = MagicMock()
        response.text = html
        soup = BeautifulSoup(html, "html.parser")
        images = scraper._get_images(response, soup)
        assert len(images) == 8


class TestGetPrice:
    def test_core_price_display(self, scraper):
        from bs4 import BeautifulSoup
        html = '''
        <div id="corePriceDisplay_desktop_feature_div">
            <span class="a-price-whole">149</span>
        </div>'''
        soup = BeautifulSoup(html, "html.parser")
        assert scraper._get_price(soup) == 149

    def test_core_price_fallback(self, scraper):
        from bs4 import BeautifulSoup
        html = '''
        <div id="corePrice_feature_div">
            <span class="a-price-whole">89</span>
        </div>'''
        soup = BeautifulSoup(html, "html.parser")
        assert scraper._get_price(soup) == 89

    def test_price_with_dots(self, scraper):
        from bs4 import BeautifulSoup
        html = '''
        <div id="corePriceDisplay_desktop_feature_div">
            <span class="a-price-whole">1.299</span>
        </div>'''
        soup = BeautifulSoup(html, "html.parser")
        assert scraper._get_price(soup) == 1299

    def test_price_with_euro_sign(self, scraper):
        from bs4 import BeautifulSoup
        html = '''
        <div id="corePriceDisplay_desktop_feature_div">
            <span class="a-price-whole">59€</span>
        </div>'''
        soup = BeautifulSoup(html, "html.parser")
        assert scraper._get_price(soup) == 59

    def test_no_price(self, scraper):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div>no price</div>", "html.parser")
        assert scraper._get_price(soup) is None


class TestGetFeatures:
    def test_feature_bullets(self, scraper):
        from bs4 import BeautifulSoup
        html = '''
        <div id="feature-bullets">
            <li>Feature 1</li>
            <li>Feature 2</li>
            <li>Feature 3</li>
        </div>'''
        soup = BeautifulSoup(html, "html.parser")
        features = scraper._get_features(soup)
        assert features == ["Feature 1", "Feature 2", "Feature 3"]

    def test_product_overview_fallback(self, scraper):
        from bs4 import BeautifulSoup
        html = '''
        <div id="productOverview">
            <li>Overview 1</li>
        </div>'''
        soup = BeautifulSoup(html, "html.parser")
        assert scraper._get_features(soup) == ["Overview 1"]

    def test_max_10_features(self, scraper):
        from bs4 import BeautifulSoup
        lis = "".join(f"<li>Feature {i}</li>" for i in range(20))
        html = f'<div id="feature-bullets">{lis}</div>'
        soup = BeautifulSoup(html, "html.parser")
        assert len(scraper._get_features(soup)) == 10

    def test_no_features(self, scraper):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div></div>", "html.parser")
        assert scraper._get_features(soup) == []


class TestScrapeProduct:
    @patch("src.scraper.amazon_scraper.requests.get")
    def test_successful_scrape(self, mock_get, scraper):
        html = '''
        <html>
            <span id="productTitle">Test Product</span>
            <div id="corePriceDisplay_desktop_feature_div">
                <span class="a-price-whole">99</span>
            </div>
            <div id="feature-bullets"><li>Cool</li></div>
        </html>'''
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = html.encode()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = scraper.scrape_product("B0TEST123")
        assert result["_status"] == 200
        assert result["title"] == "Test Product"
        assert result["price"] == 99

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_404_response(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = scraper.scrape_product("B0NOTFOUND")
        assert result == {"_status": 404}

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_network_error_returns_none(self, mock_get, scraper):
        mock_get.side_effect = Exception("Connection timeout")

        result = scraper.scrape_product("B0ERROR")
        assert result is None

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_timeout_returns_none(self, mock_get, scraper):
        from requests.exceptions import Timeout
        mock_get.side_effect = Timeout("Request timed out")

        result = scraper.scrape_product("B0TIMEOUT")
        assert result is None

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_connection_error_returns_none(self, mock_get, scraper):
        from requests.exceptions import ConnectionError
        mock_get.side_effect = ConnectionError("DNS failure")

        result = scraper.scrape_product("B0CONNFAIL")
        assert result is None

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_missing_price_still_returns_200(self, mock_get, scraper):
        html = '<html><span id="productTitle">No Price Item</span></html>'
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = html.encode()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = scraper.scrape_product("B0NOPRICE")
        assert result["_status"] == 200
        assert result["title"] == "No Price Item"
        assert result["price"] is None

    def test_user_agent_rotation(self, scraper):
        headers_seen = set()
        for _ in range(50):
            headers = scraper._get_headers()
            headers_seen.add(headers["User-Agent"])
        assert headers_seen <= {"TestAgent/1.0", "TestAgent/2.0"}
        assert len(headers_seen) >= 1


class TestConstructor:
    def test_empty_user_agents_raises(self):
        with pytest.raises(ValueError):
            AmazonScraper(user_agents=[])

    def test_accepts_single_agent(self):
        scraper = AmazonScraper(user_agents=["OnlyOne/1.0"])
        assert scraper._get_headers()["User-Agent"] == "OnlyOne/1.0"
