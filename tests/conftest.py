"""Shared fixtures for the test suite."""

import json
from datetime import datetime, timezone
from time import struct_time
from unittest.mock import MagicMock

import pytest

from logging_config import configure_logging

configure_logging(json_logs=False)

from feed_parser import BlogPost  # noqa: E402


@pytest.fixture
def sample_blog_post():
    """A realistic BlogPost for testing."""
    return BlogPost(
        id="https://eve.gd/2025/03/17/institutional-stupidity/",
        title="Institutional Stupidity",
        url="https://eve.gd/2025/03/17/institutional-stupidity/",
        published=datetime(2025, 3, 17, 10, 30, 0, tzinfo=timezone.utc),
        updated=datetime(2025, 3, 17, 10, 30, 0, tzinfo=timezone.utc),
        content_html=(
            "<h2>Introduction</h2>"
            "<p>This is a <strong>blog post</strong>"
            " about institutional stupidity.</p>"
            '<p>It has <a href="https://example.com">'
            "a link</a> and more content.</p>"
            '<img src="https://eve.gd/images/featured.jpg"'
            ' alt="Featured" />'
            "<blockquote>A famous quote about institutions.</blockquote>"
            "<ul><li>Point one</li><li>Point two</li><li>Point three</li></ul>"
            '<p>DOI: <a href="https://doi.org/10.1234/test.5678">10.1234/test.5678</a></p>'
        ),
        summary="This is a blog post about institutional stupidity...",
        featured_image_url="https://eve.gd/images/featured.jpg",
        doi="10.1234/test.5678",
        author="Martin Paul Eve",
        tags=["academia", "open-access", "publishing"],
    )


@pytest.fixture
def sample_blog_post_minimal():
    """A minimal BlogPost with no image, DOI, or tags."""
    return BlogPost(
        id="https://eve.gd/2025/01/01/simple-post/",
        title="A Simple Post",
        url="https://eve.gd/2025/01/01/simple-post/",
        published=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        updated=None,
        content_html="<p>Just a simple paragraph.</p>",
        summary="Just a simple paragraph.",
        featured_image_url=None,
        doi=None,
        author="",
        tags=[],
    )


@pytest.fixture
def tmp_state_file(tmp_path):
    """Return a path to a temporary state file."""
    return str(tmp_path / "test_sync_state.json")


@pytest.fixture
def populated_state_file(tmp_path):
    """Return a path to a state file pre-populated with one synced post."""
    state_file = tmp_path / "test_sync_state.json"
    state = {
        "synced_posts": {
            "https://eve.gd/2025/01/01/old-post/": {
                "post_url": "https://eve.gd/2025/01/01/old-post/",
                "post_title": "Old Post",
                "linkedin_post_urn": "urn:li:share:1234567890",
                "synced_at": "2025-01-01T12:00:00+00:00",
                "post_published": "2025-01-01T10:00:00+00:00",
            }
        }
    }
    state_file.write_text(json.dumps(state, indent=2))
    return str(state_file)


@pytest.fixture
def mock_feed_entry():
    """Create a mock feedparser entry with typical fields."""
    entry = MagicMock()
    entry.id = "https://eve.gd/2025/03/20/test-post/"
    entry.title = "Test Post Title"
    entry.link = "https://eve.gd/2025/03/20/test-post/"
    entry.published_parsed = struct_time((2025, 3, 20, 10, 0, 0, 3, 79, 0))
    entry.updated_parsed = struct_time((2025, 3, 20, 10, 0, 0, 3, 79, 0))
    entry.content = [
        {
            "value": "<p>Test content with <strong>bold</strong>.</p>",
            "type": "text/html",
        }
    ]
    entry.summary = "Test content with bold."
    entry.author = "Test Author"
    entry.tags = [{"term": "python"}, {"term": "testing"}]
    entry.media_thumbnail = None
    entry.media_content = None
    entry.enclosures = []
    entry.links = [
        {
            "rel": "alternate",
            "type": "text/html",
            "href": "https://eve.gd/2025/03/20/test-post/",
        }
    ]
    return entry


def make_mock_response(
    status_code=200, json_data=None, headers=None, content=b""
):
    """Helper to create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.json.return_value = json_data or {}
    resp.content = content
    resp.text = (
        content.decode() if isinstance(content, bytes) else str(content)
    )
    resp.raise_for_status.return_value = None
    if status_code >= 400:
        from requests.exceptions import HTTPError

        resp.raise_for_status.side_effect = HTTPError(response=resp)
    return resp
