"""Tests for the Amazon product scraper."""
from unittest.mock import patch, MagicMock

from src.scraper import AmazonScraper


def _make_scraper(**kwargs):
    return AmazonScraper(
        user_agents=["TestAgent/1.0"],
        **kwargs,
    )


class TestScrapeProduct:

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_successful_scrape(self, mock_get):
        html = """
        <html><body>
        <span id="productTitle">Sony WH-1000XM4 Headphones</span>
        <div id="corePriceDisplay_desktop_feature_div">
            <span class="a-price-whole">279</span>
        </div>
        <div id="feature-bullets">
            <li>Noise Cancelling</li>
            <li>30h Battery</li>
        </div>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = html.encode()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        scraper = _make_scraper()
        result = scraper.scrape_product("B0863TXGM3")

        assert result is not None
        assert result["_status"] == 200
        assert result["title"] == "Sony WH-1000XM4 Headphones"
        assert result["price"] == 279
        assert "Noise Cancelling" in result["features"]

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_404_returns_status(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        scraper = _make_scraper()
        result = scraper.scrape_product("B000INVALID")

        assert result is not None
        assert result["_status"] == 404

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_503_returns_status(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_get.return_value = mock_response

        scraper = _make_scraper()
        result = scraper.scrape_product("B000BLOCKED")

        assert result is not None
        assert result["_status"] == 503

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_timeout_returns_none(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        scraper = _make_scraper()
        result = scraper.scrape_product("B000TIMEOUT")

        assert result is None

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_connection_error_returns_none(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        scraper = _make_scraper()
        result = scraper.scrape_product("B000NOCONN")

        assert result is None

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_hires_images_extracted(self, mock_get):
        html = '''
        <html><body>
        <span id="productTitle">Test Product</span>
        "hiRes":"https://images-na.ssl-images-amazon.com/images/I/71abc.jpg"
        "hiRes":"https://images-na.ssl-images-amazon.com/images/I/71def.jpg"
        </body></html>
        '''
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = html.encode()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        scraper = _make_scraper()
        result = scraper.scrape_product("B000IMAGES")

        assert result is not None
        images = result["images"].split("|")
        assert len(images) == 2
        assert "71abc.jpg" in images[0]

    @patch("src.scraper.amazon_scraper.requests.get")
    def test_missing_price_returns_none_price(self, mock_get):
        html = """
        <html><body>
        <span id="productTitle">No Price Product</span>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = html.encode()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        scraper = _make_scraper()
        result = scraper.scrape_product("B000NOPRICE")

        assert result is not None
        assert result["_status"] == 200
        assert result["price"] is None
        assert result["title"] == "No Price Product"

    def test_configurable_domain(self):
        scraper = _make_scraper(domain="com")
        assert scraper._base_url == "https://www.amazon.com/dp/"

    def test_default_domain_is_es(self):
        scraper = _make_scraper()
        assert scraper._base_url == "https://www.amazon.es/dp/"
