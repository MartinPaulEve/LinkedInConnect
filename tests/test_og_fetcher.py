"""Tests for OpenGraph metadata fetcher."""

from unittest.mock import MagicMock, patch

from linkedin_sync.og_fetcher import fetch_og_metadata


class TestFetchOgMetadata:
    """Test OpenGraph metadata extraction from URLs."""

    @patch("linkedin_sync.og_fetcher.requests.get")
    def test_extracts_og_title_description_image(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = (
            "<html><head>"
            '<meta property="og:title" content="My Article" />'
            '<meta property="og:description" content="A great read." />'
            '<meta property="og:image"'
            ' content="https://eve.gd/images/pic.jpg" />'
            "</head></html>"
        )
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        meta = fetch_og_metadata("https://eve.gd/2026/03/23/article/")
        assert meta["title"] == "My Article"
        assert meta["description"] == "A great read."
        assert meta["image"] == "https://eve.gd/images/pic.jpg"

    @patch("linkedin_sync.og_fetcher.requests.get")
    def test_falls_back_to_html_title(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "<html><head><title>Fallback Title</title></head></html>"
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        meta = fetch_og_metadata("https://example.com/page")
        assert meta["title"] == "Fallback Title"
        assert meta["description"] == ""
        assert meta["image"] is None

    @patch("linkedin_sync.og_fetcher.requests.get")
    def test_returns_empty_on_http_error(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")

        meta = fetch_og_metadata("https://example.com/broken")
        assert meta["title"] == ""
        assert meta["description"] == ""
        assert meta["image"] is None

    @patch("linkedin_sync.og_fetcher.requests.get")
    def test_returns_empty_for_none_url(self, mock_get):
        meta = fetch_og_metadata(None)
        assert meta["title"] == ""
        assert meta["image"] is None
        mock_get.assert_not_called()

    @patch("linkedin_sync.og_fetcher.requests.get")
    def test_meta_description_fallback(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = (
            "<html><head>"
            '<meta name="description" content="Meta desc fallback" />'
            "</head></html>"
        )
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        meta = fetch_og_metadata("https://example.com/page")
        assert meta["description"] == "Meta desc fallback"
