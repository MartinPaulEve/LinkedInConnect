"""Tests for local markdown file parsing and the file CLI subcommand."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from linkedin_sync.feed_parser import parse_markdown_file
from linkedin_sync.sync import cli

SAMPLE_MARKDOWN = """\
---
title: My Test Post
url: https://eve.gd/2025/04/01/my-test-post/
date: 2025-04-01
tags:
  - python
  - testing
image: https://eve.gd/images/test.jpg
doi: 10.1234/test.5678
author: Test Author
---

# Introduction

This is a **test post** with some content.

- Item one
- Item two

Read more at [example](https://example.com).
"""

MINIMAL_MARKDOWN = """\
---
title: Minimal Post
url: https://eve.gd/2025/01/01/minimal/
---

Just a paragraph.
"""


class TestParseMarkdownFile:
    def test_full_front_matter(self, tmp_path):
        md_file = tmp_path / "post.md"
        md_file.write_text(SAMPLE_MARKDOWN)

        post = parse_markdown_file(str(md_file))

        assert post.title == "My Test Post"
        assert post.url == "https://eve.gd/2025/04/01/my-test-post/"
        assert post.published == datetime(2025, 4, 1, tzinfo=timezone.utc)
        assert post.tags == ["python", "testing"]
        assert post.featured_image_url == "https://eve.gd/images/test.jpg"
        assert post.doi == "10.1234/test.5678"
        assert post.author == "Test Author"
        assert "<strong>test post</strong>" in post.content_html
        assert post.id == post.url

    def test_minimal_front_matter(self, tmp_path):
        md_file = tmp_path / "minimal.md"
        md_file.write_text(MINIMAL_MARKDOWN)

        post = parse_markdown_file(str(md_file))

        assert post.title == "Minimal Post"
        assert post.url == "https://eve.gd/2025/01/01/minimal/"
        assert post.featured_image_url is None
        assert post.doi is None
        assert post.tags == []

    def test_missing_title_raises(self, tmp_path):
        md_file = tmp_path / "bad.md"
        md_file.write_text("---\nurl: https://example.com\n---\nHello\n")

        with pytest.raises(ValueError, match="title"):
            parse_markdown_file(str(md_file))

    def test_missing_url_inferred_from_jekyll_filename(self, tmp_path):
        """URL is inferred from Jekyll-style filename YYYY-MM-DD-slug.md."""
        md_file = tmp_path / "2026-03-21-my-cool-post.markdown"
        md_file.write_text(
            "---\ntitle: Cool Post\ndate: 2026-03-21\n---\nHello\n"
        )

        post = parse_markdown_file(str(md_file))
        assert post.url == "https://eve.gd/2026/03/21/my-cool-post/"
        assert post.title == "Cool Post"

    def test_missing_url_inferred_custom_site_url(self, tmp_path):
        """URL inference uses a custom site_url when provided."""
        md_file = tmp_path / "2026-01-15-other-post.md"
        md_file.write_text("---\ntitle: Other\ndate: 2026-01-15\n---\nHi\n")

        post = parse_markdown_file(
            str(md_file), site_url="https://blog.example.com"
        )
        assert post.url == "https://blog.example.com/2026/01/15/other-post/"

    def test_missing_url_non_jekyll_filename_raises(self, tmp_path):
        md_file = tmp_path / "bad.md"
        md_file.write_text("---\ntitle: No URL\n---\nHello\n")

        with pytest.raises(ValueError, match="url"):
            parse_markdown_file(str(md_file))

    def test_nested_image_dict(self, tmp_path):
        """Handle Jekyll-style image front matter with nested feature key."""
        md_file = tmp_path / "2026-03-21-img-post.markdown"
        md_file.write_text(
            "---\n"
            "title: Image Post\n"
            "url: https://eve.gd/2026/03/21/img-post/\n"
            "image:\n"
            "  feature: yubico.png\n"
            "  credit: Yubico\n"
            "---\n"
            "Content\n"
        )
        post = parse_markdown_file(str(md_file))
        assert post.featured_image_url == "https://eve.gd/images/yubico.png"

    def test_absolute_image_url_not_modified(self, tmp_path):
        """Absolute image URLs are left unchanged."""
        md_file = tmp_path / "post.md"
        md_file.write_text(
            "---\n"
            "title: Abs Image\n"
            "url: https://eve.gd/abs/\n"
            "image: https://cdn.example.com/photo.jpg\n"
            "---\nContent\n"
        )
        post = parse_markdown_file(str(md_file))
        assert post.featured_image_url == "https://cdn.example.com/photo.jpg"

    def test_relative_image_resolved_to_images_dir(self, tmp_path):
        """Bare filename images resolve to site_url/images/."""
        md_file = tmp_path / "post.md"
        md_file.write_text(
            "---\n"
            "title: Rel Image\n"
            "url: https://eve.gd/rel/\n"
            "image: photo.jpg\n"
            "---\nContent\n"
        )
        post = parse_markdown_file(str(md_file))
        assert post.featured_image_url == "https://eve.gd/images/photo.jpg"

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_markdown_file(str(tmp_path / "nonexistent.md"))

    def test_no_front_matter_raises(self, tmp_path):
        md_file = tmp_path / "plain.md"
        md_file.write_text("# Just a heading\n\nNo front matter here.\n")

        with pytest.raises(ValueError, match="title"):
            parse_markdown_file(str(md_file))

    def test_permalink_as_url(self, tmp_path):
        md_file = tmp_path / "perm.md"
        md_file.write_text(
            "---\ntitle: Perm Post\n"
            "permalink: https://eve.gd/perm/\n---\nContent\n"
        )

        post = parse_markdown_file(str(md_file))
        assert post.url == "https://eve.gd/perm/"

    def test_datetime_string_with_time(self, tmp_path):
        md_file = tmp_path / "dt.md"
        md_file.write_text(
            "---\ntitle: DT Post\nurl: https://eve.gd/dt/\n"
            "date: 2025-06-15 14:30:00\n---\nContent\n"
        )

        post = parse_markdown_file(str(md_file))
        assert post.published.hour == 14
        assert post.published.minute == 30

    def test_comma_separated_tags(self, tmp_path):
        md_file = tmp_path / "tags.md"
        md_file.write_text(
            "---\ntitle: Tags Post\nurl: https://eve.gd/tags/\n"
            "tags: python, testing, code\n---\nContent\n"
        )

        post = parse_markdown_file(str(md_file))
        assert post.tags == ["python", "testing", "code"]


class TestCliFile:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_dry_run_file(self, runner, tmp_path):
        md_file = tmp_path / "post.md"
        md_file.write_text(SAMPLE_MARKDOWN)
        state_file = str(tmp_path / "state.json")

        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "--no-summary",
                "file",
                str(md_file),
            ],
        )
        assert result.exit_code == 0

    def test_file_not_found(self, runner, tmp_path):
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "file",
                str(tmp_path / "nope.md"),
            ],
        )
        assert result.exit_code != 0

    def test_file_already_synced(self, runner, tmp_path):
        md_file = tmp_path / "post.md"
        md_file.write_text(SAMPLE_MARKDOWN)
        state_file = tmp_path / "state.json"
        url = "https://eve.gd/2025/04/01/my-test-post/"
        state_file.write_text(
            json.dumps(
                {
                    "synced_posts": {
                        url: {
                            "post_url": url,
                            "post_title": "My Test Post",
                            "linkedin_post_urn": "urn:li:share:old",
                            "synced_at": "2025-04-01T12:00:00+00:00",
                            "post_published": "2025-04-01T00:00:00+00:00",
                        }
                    }
                }
            )
        )

        result = runner.invoke(
            cli,
            [
                "--state-file",
                str(state_file),
                "--dry-run",
                "--no-summary",
                "file",
                str(md_file),
            ],
        )
        assert result.exit_code == 0

    def test_file_force_resync(self, runner, tmp_path):
        md_file = tmp_path / "post.md"
        md_file.write_text(SAMPLE_MARKDOWN)
        state_file = tmp_path / "state.json"
        url = "https://eve.gd/2025/04/01/my-test-post/"
        state_file.write_text(
            json.dumps(
                {
                    "synced_posts": {
                        url: {
                            "post_url": url,
                            "post_title": "My Test Post",
                            "linkedin_post_urn": "urn:li:share:old",
                            "synced_at": "2025-04-01T12:00:00+00:00",
                            "post_published": "2025-04-01T00:00:00+00:00",
                        }
                    }
                }
            )
        )

        result = runner.invoke(
            cli,
            [
                "--state-file",
                str(state_file),
                "--dry-run",
                "--force",
                "--no-summary",
                "file",
                str(md_file),
            ],
        )
        assert result.exit_code == 0

    @patch("linkedin_sync.sync._make_clients")
    def test_live_sync_from_file(self, mock_make_clients, runner, tmp_path):
        md_file = tmp_path / "post.md"
        md_file.write_text(SAMPLE_MARKDOWN)
        state_file = str(tmp_path / "state.json")

        mock_li = MagicMock()
        mock_li.upload_image.return_value = "urn:li:image:123"
        mock_li.create_post.return_value = "urn:li:share:file123"
        mock_make_clients.return_value = (mock_li, None, None)

        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--no-summary",
                "file",
                str(md_file),
            ],
        )
        assert result.exit_code == 0

        with open(state_file) as f:
            state = json.load(f)
        url = "https://eve.gd/2025/04/01/my-test-post/"
        assert url in state["synced_posts"]
        assert (
            state["synced_posts"][url]["linkedin_post_urn"]
            == "urn:li:share:file123"
        )
