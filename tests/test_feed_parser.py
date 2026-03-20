"""Tests for feed_parser module."""

from datetime import date, datetime, timezone
from time import struct_time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from feed_parser import (
    BlogPost,
    _extract_doi,
    _extract_featured_image,
    _html_to_text_summary,
    _parse_entry,
    get_post_by_url,
    get_todays_posts,
    parse_feed,
)


class TestBlogPost:
    def test_published_date_property(self, sample_blog_post):
        assert sample_blog_post.published_date == date(2025, 3, 17)

    def test_published_date_utc(self):
        post = BlogPost(
            id="x",
            title="x",
            url="x",
            published=datetime(2025, 6, 15, 23, 59, 59, tzinfo=timezone.utc),
            updated=None,
            content_html="",
            summary="",
            featured_image_url=None,
            doi=None,
        )
        assert post.published_date == date(2025, 6, 15)


class TestExtractDoi:
    def test_doi_org_url(self):
        html = '<a href="https://doi.org/10.1234/test.5678">DOI</a>'
        assert _extract_doi(html) == "10.1234/test.5678"

    def test_doi_prefix_colon(self):
        html = "DOI: 10.5555/abcdefg"
        assert _extract_doi(html) == "10.5555/abcdefg"

    def test_doi_lowercase(self):
        html = "doi: 10.9999/xyz.123"
        assert _extract_doi(html) == "10.9999/xyz.123"

    def test_bare_doi_in_text(self):
        html = "The paper is 10.1000/test"
        assert _extract_doi(html) == "10.1000/test"

    def test_doi_strips_trailing_punctuation(self):
        html = "See doi.org/10.1234/test.5678."
        assert _extract_doi(html) == "10.1234/test.5678"

    def test_no_doi(self):
        html = "<p>No DOI in this content.</p>"
        assert _extract_doi(html) is None

    def test_doi_in_title(self):
        assert _extract_doi("", title="Paper 10.1234/foo") == "10.1234/foo"

    def test_empty_input(self):
        assert _extract_doi("") is None
        assert _extract_doi("", "") is None


class TestExtractFeaturedImage:
    def test_media_thumbnail(self):
        entry = SimpleNamespace(
            media_thumbnail=[{"url": "https://example.com/thumb.jpg"}],
        )
        assert (
            _extract_featured_image(entry, "")
            == "https://example.com/thumb.jpg"
        )

    def test_media_content_image(self):
        entry = SimpleNamespace(
            media_thumbnail=None,
            media_content=[
                {"medium": "image", "url": "https://example.com/img.png"}
            ],
        )
        assert (
            _extract_featured_image(entry, "") == "https://example.com/img.png"
        )

    def test_media_content_by_type(self):
        entry = SimpleNamespace(
            media_thumbnail=None,
            media_content=[
                {"type": "image/jpeg", "url": "https://example.com/img.jpg"}
            ],
        )
        assert (
            _extract_featured_image(entry, "") == "https://example.com/img.jpg"
        )

    def test_enclosure(self):
        entry = SimpleNamespace(
            media_thumbnail=None,
            media_content=None,
            enclosures=[
                {"type": "image/png", "href": "https://example.com/enc.png"}
            ],
            links=[],
        )
        assert (
            _extract_featured_image(entry, "") == "https://example.com/enc.png"
        )

    def test_link_enclosure(self):
        entry = SimpleNamespace(
            media_thumbnail=None,
            media_content=None,
            enclosures=[],
            links=[
                {
                    "rel": "enclosure",
                    "type": "image/jpeg",
                    "href": "https://example.com/link.jpg",
                }
            ],
        )
        assert (
            _extract_featured_image(entry, "")
            == "https://example.com/link.jpg"
        )

    def test_image_in_content_html(self):
        entry = SimpleNamespace(
            media_thumbnail=None,
            media_content=None,
            enclosures=[],
            links=[],
        )
        html = '<p>Some text</p><img src="https://example.com/content.jpg" />'
        assert (
            _extract_featured_image(entry, html)
            == "https://example.com/content.jpg"
        )

    def test_no_image_anywhere(self):
        entry = SimpleNamespace(
            media_thumbnail=None,
            media_content=None,
            enclosures=[],
            links=[],
        )
        assert _extract_featured_image(entry, "<p>No images here.</p>") is None

    def test_empty_content(self):
        entry = SimpleNamespace(
            media_thumbnail=None,
            media_content=None,
            enclosures=[],
            links=[],
        )
        assert _extract_featured_image(entry, "") is None


class TestHtmlToTextSummary:
    def test_basic_html(self):
        result = _html_to_text_summary("<p>Hello <b>world</b></p>")
        assert result == "Hello world"

    def test_truncation(self):
        html = "<p>" + "word " * 100 + "</p>"
        result = _html_to_text_summary(html, max_length=50)
        assert len(result) <= 54  # 50 + "..."
        assert result.endswith("...")

    def test_empty_html(self):
        assert _html_to_text_summary("") == ""

    def test_short_text_not_truncated(self):
        result = _html_to_text_summary("<p>Short.</p>", max_length=300)
        assert result == "Short."
        assert "..." not in result


class TestParseEntry:
    def test_valid_entry(self, mock_feed_entry):
        post = _parse_entry(mock_feed_entry)
        assert post is not None
        assert post.title == "Test Post Title"
        assert post.url == "https://eve.gd/2025/03/20/test-post/"
        assert post.author == "Test Author"
        assert post.tags == ["python", "testing"]
        assert "bold" in post.content_html

    def test_entry_no_date_returns_none(self):
        entry = SimpleNamespace(
            id="x",
            title="No Date Post",
            link="https://example.com",
            published_parsed=None,
            updated_parsed=None,
        )
        assert _parse_entry(entry) is None

    def test_entry_falls_back_to_updated_date(self):
        entry = MagicMock()
        entry.id = "x"
        entry.title = "Updated Only"
        entry.link = "https://example.com"
        entry.published_parsed = None
        entry.updated_parsed = struct_time((2025, 6, 1, 12, 0, 0, 0, 0, 0))
        entry.content = []
        entry.summary = "Summary text"
        entry.tags = []
        entry.author = ""
        entry.media_thumbnail = None
        entry.media_content = None
        entry.enclosures = []
        entry.links = []
        post = _parse_entry(entry)
        assert post is not None
        assert post.published_date == date(2025, 6, 1)

    def test_entry_prefers_content_over_summary(self, mock_feed_entry):
        mock_feed_entry.content = [{"value": "<p>Full content here.</p>"}]
        mock_feed_entry.summary = "Short summary"
        post = _parse_entry(mock_feed_entry)
        assert "Full content here" in post.content_html

    def test_entry_uses_summary_when_no_content(self, mock_feed_entry):
        del mock_feed_entry.content
        mock_feed_entry.summary = "<p>Summary fallback</p>"
        post = _parse_entry(mock_feed_entry)
        assert "Summary fallback" in post.content_html


class TestParseFeed:
    @patch("feed_parser.feedparser.parse")
    def test_returns_posts(self, mock_parse, mock_feed_entry):
        mock_parse.return_value = MagicMock(
            entries=[mock_feed_entry], bozo=False
        )
        posts = parse_feed("https://example.com/feed.atom")
        assert len(posts) == 1
        assert posts[0].title == "Test Post Title"

    @patch("feed_parser.feedparser.parse")
    def test_empty_feed(self, mock_parse):
        mock_parse.return_value = MagicMock(entries=[], bozo=False)
        posts = parse_feed("https://example.com/feed.atom")
        assert posts == []

    @patch("feed_parser.feedparser.parse")
    def test_skips_entries_without_dates(self, mock_parse):
        bad_entry = SimpleNamespace(
            id="x",
            title="Bad",
            link="https://example.com",
            published_parsed=None,
            updated_parsed=None,
        )
        mock_parse.return_value = MagicMock(entries=[bad_entry], bozo=False)
        posts = parse_feed("https://example.com/feed.atom")
        assert posts == []


class TestGetTodaysPosts:
    @patch("feed_parser.parse_feed")
    @patch("feed_parser.date")
    def test_filters_to_today(self, mock_date, mock_parse):
        mock_date.today.return_value = date(2025, 3, 17)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        posts = [
            BlogPost(
                id="a",
                title="Today",
                url="https://eve.gd/today",
                published=datetime(2025, 3, 17, 10, 0, tzinfo=timezone.utc),
                updated=None,
                content_html="",
                summary="",
                featured_image_url=None,
                doi=None,
            ),
            BlogPost(
                id="b",
                title="Yesterday",
                url="https://eve.gd/yesterday",
                published=datetime(2025, 3, 16, 10, 0, tzinfo=timezone.utc),
                updated=None,
                content_html="",
                summary="",
                featured_image_url=None,
                doi=None,
            ),
        ]
        mock_parse.return_value = posts
        result = get_todays_posts("https://example.com/feed.atom")
        assert len(result) == 1
        assert result[0].title == "Today"


class TestGetPostByUrl:
    @patch("feed_parser.parse_feed")
    def test_finds_by_url(self, mock_parse, sample_blog_post):
        mock_parse.return_value = [sample_blog_post]
        result = get_post_by_url(
            sample_blog_post.url, "https://example.com/feed.atom"
        )
        assert result is not None
        assert result.title == sample_blog_post.title

    @patch("feed_parser.parse_feed")
    def test_finds_by_id(self, mock_parse, sample_blog_post):
        mock_parse.return_value = [sample_blog_post]
        result = get_post_by_url(
            sample_blog_post.id, "https://example.com/feed.atom"
        )
        assert result is not None

    @patch("feed_parser.parse_feed")
    def test_returns_none_when_not_found(self, mock_parse, sample_blog_post):
        mock_parse.return_value = [sample_blog_post]
        result = get_post_by_url(
            "https://eve.gd/nonexistent/", "https://example.com/feed.atom"
        )
        assert result is None
