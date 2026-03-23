"""Tests for OpenGraph metadata fetcher."""

from unittest.mock import MagicMock, patch

import requests

from linkedin_sync.og_fetcher import (
    _fetch_doi_metadata,
    fetch_og_metadata,
)


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

    @patch("linkedin_sync.og_fetcher._fetch_doi_metadata")
    @patch("linkedin_sync.og_fetcher.requests.get")
    def test_doi_url_falls_back_to_doi_api_on_og_failure(
        self, mock_get, mock_doi
    ):
        """When OG fetch fails for a DOI URL, fall back to DOI API."""
        mock_get.side_effect = requests.HTTPError("403 Forbidden")
        mock_doi.return_value = {
            "title": "DOI Title",
            "description": "DOI abstract text.",
            "image": None,
        }

        meta = fetch_og_metadata("https://doi.org/10.16995/orbit.24920")
        assert meta["title"] == "DOI Title"
        assert meta["description"] == "DOI abstract text."
        mock_doi.assert_called_once_with("10.16995/orbit.24920")

    @patch("linkedin_sync.og_fetcher._fetch_doi_metadata")
    @patch("linkedin_sync.og_fetcher.requests.get")
    def test_non_doi_url_does_not_fall_back_to_doi_api(
        self, mock_get, mock_doi
    ):
        """Non-DOI URLs should not trigger DOI fallback."""
        mock_get.side_effect = requests.HTTPError("403 Forbidden")

        meta = fetch_og_metadata("https://example.com/article")
        assert meta["title"] == ""
        mock_doi.assert_not_called()

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


class TestFetchDoiMetadata:
    """Test DOI content-negotiation metadata fetcher."""

    @patch("linkedin_sync.og_fetcher.requests.get")
    def test_extracts_title_and_abstract(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "title": [
                "From Punk to Cyberpunk"
            ],
            "abstract": "<p>This article examines...</p>",
        }
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        meta = _fetch_doi_metadata("10.16995/orbit.24920")
        assert meta["title"] == "From Punk to Cyberpunk"
        assert "This article examines" in meta["description"]
        assert meta["image"] is None

        # Verify content negotiation header
        call_headers = mock_get.call_args.kwargs.get(
            "headers", {}
        )
        assert (
            call_headers.get("Accept")
            == "application/citeproc+json"
        )

    @patch("linkedin_sync.og_fetcher.requests.get")
    def test_handles_string_title(self, mock_get):
        """Some DOI providers return title as a string."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "title": "A String Title",
        }
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        meta = _fetch_doi_metadata("10.1234/test")
        assert meta["title"] == "A String Title"

    @patch("linkedin_sync.og_fetcher.requests.get")
    def test_returns_empty_on_failure(self, mock_get):
        mock_get.side_effect = Exception("Network error")

        meta = _fetch_doi_metadata("10.1234/broken")
        assert meta["title"] == ""
        assert meta["description"] == ""
        assert meta["image"] is None

    @patch("linkedin_sync.og_fetcher.requests.get")
    def test_strips_html_from_abstract(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "title": ["Test"],
            "abstract": (
                "<jats:p>Abstract with "
                "<jats:italic>markup</jats:italic>.</jats:p>"
            ),
        }
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        meta = _fetch_doi_metadata("10.1234/html")
        assert meta["description"] == "Abstract with markup."
