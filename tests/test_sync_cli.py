"""Tests for the sync CLI (Click commands)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from linkedin_sync.sync import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def env_vars(monkeypatch):
    """Set required env vars so LinkedInClient doesn't complain."""
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("LINKEDIN_PERSON_URN", "urn:li:person:test")


def _make_post(
    title="Test Post", url="https://eve.gd/2025/03/20/test/", published=None
):
    """Helper to build a mock BlogPost."""
    from linkedin_sync.feed_parser import BlogPost

    return BlogPost(
        id=url,
        title=title,
        url=url,
        published=published
        or datetime(2025, 3, 20, 10, 0, tzinfo=timezone.utc),
        updated=None,
        content_html=f"<p>{title} content.</p>",
        summary=f"{title} content.",
        featured_image_url=None,
        doi=None,
        tags=["test"],
    )


class TestCliToday:
    @patch("linkedin_sync.sync.get_todays_posts")
    def test_no_posts_today(self, mock_today, runner, tmp_path):
        mock_today.return_value = []
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli, ["--state-file", state_file, "--dry-run", "today"]
        )
        assert result.exit_code == 0

    @patch("linkedin_sync.sync.get_todays_posts")
    def test_dry_run_today(self, mock_today, runner, tmp_path):
        mock_today.return_value = [_make_post()]
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "--no-summary",
                "today",
            ],
        )
        assert result.exit_code == 0

    @patch("linkedin_sync.sync.get_todays_posts")
    def test_skips_already_synced(self, mock_today, runner, tmp_path):
        post = _make_post()
        mock_today.return_value = [post]
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "synced_posts": {
                        post.url: {
                            "post_url": post.url,
                            "post_title": post.title,
                            "linkedin_post_urn": "urn:li:share:old",
                            "synced_at": "2025-03-20T12:00:00+00:00",
                            "post_published": "2025-03-20T10:00:00+00:00",
                        }
                    }
                }
            )
        )
        result = runner.invoke(
            cli, ["--state-file", str(state_file), "--dry-run", "today"]
        )
        assert result.exit_code == 0

    @patch("linkedin_sync.sync.get_todays_posts")
    def test_force_resyncs(self, mock_today, runner, tmp_path):
        post = _make_post()
        mock_today.return_value = [post]
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "synced_posts": {
                        post.url: {
                            "post_url": post.url,
                            "post_title": post.title,
                            "linkedin_post_urn": "urn:li:share:old",
                            "synced_at": "2025-03-20T12:00:00+00:00",
                            "post_published": "2025-03-20T10:00:00+00:00",
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
                "today",
            ],
        )
        assert result.exit_code == 0


class TestCliPost:
    @patch("linkedin_sync.sync.get_post_by_url")
    def test_dry_run_specific_post(self, mock_get, runner, tmp_path):
        mock_get.return_value = _make_post()
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "--no-summary",
                "post",
                "https://eve.gd/2025/03/20/test/",
            ],
        )
        assert result.exit_code == 0

    @patch("linkedin_sync.sync.get_post_by_url")
    def test_post_not_found(self, mock_get, runner, tmp_path):
        mock_get.return_value = None
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "post",
                "https://eve.gd/nonexistent/",
            ],
        )
        assert result.exit_code != 0

    @patch("linkedin_sync.sync.get_post_by_url")
    def test_already_synced_without_force(self, mock_get, runner, tmp_path):
        post = _make_post()
        mock_get.return_value = post
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "synced_posts": {
                        post.url: {
                            "post_url": post.url,
                            "post_title": post.title,
                            "linkedin_post_urn": "urn:x",
                            "synced_at": "2025-03-20T12:00:00+00:00",
                            "post_published": "2025-03-20T10:00:00+00:00",
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
                "post",
                post.url,
            ],
        )
        assert result.exit_code == 0

    @patch("linkedin_sync.sync.get_post_by_url")
    def test_force_resync_specific_post(self, mock_get, runner, tmp_path):
        post = _make_post()
        mock_get.return_value = post
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "synced_posts": {
                        post.url: {
                            "post_url": post.url,
                            "post_title": post.title,
                            "linkedin_post_urn": "urn:x",
                            "synced_at": "2025-03-20T12:00:00+00:00",
                            "post_published": "2025-03-20T10:00:00+00:00",
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
                "post",
                post.url,
            ],
        )
        assert result.exit_code == 0

    def test_post_with_local_file_dry_run(self, runner, tmp_path):
        """post command accepts a local .md file path."""
        md = tmp_path / "post.md"
        md.write_text(
            "---\n"
            "title: Local Post\n"
            "url: https://example.com/local\n"
            "date: 2026-03-21\n"
            "---\n"
            "\n"
            "Some content here.\n"
        )
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "--no-summary",
                "post",
                str(md),
            ],
        )
        assert result.exit_code == 0

    def test_post_with_local_file_shows_preview(self, runner, tmp_path):
        """post with local file in dry-run shows platform previews."""
        md = tmp_path / "post.md"
        md.write_text(
            "---\n"
            "title: Preview Post\n"
            "url: https://example.com/preview\n"
            "date: 2026-03-21\n"
            "tags: python, testing\n"
            "---\n"
            "\n"
            "A blog post about testing.\n"
        )
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "--no-summary",
                "post",
                str(md),
            ],
        )
        assert result.exit_code == 0


class TestCliOnly:
    """Tests for the --only platform filter."""

    @patch("linkedin_sync.sync.get_post_by_url")
    def test_only_linkedin(self, mock_get, runner, tmp_path):
        mock_get.return_value = _make_post()
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "--no-summary",
                "--only",
                "linkedin",
                "post",
                "https://eve.gd/2025/03/20/test/",
            ],
        )
        assert result.exit_code == 0

    @patch("linkedin_sync.sync.get_post_by_url")
    def test_only_multiple_platforms(self, mock_get, runner, tmp_path):
        mock_get.return_value = _make_post()
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "--no-summary",
                "--only",
                "bluesky,mastodon",
                "post",
                "https://eve.gd/2025/03/20/test/",
            ],
        )
        assert result.exit_code == 0

    def test_only_invalid_platform(self, runner, tmp_path):
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "--only",
                "twitter",
                "today",
            ],
        )
        assert result.exit_code != 0
        assert "twitter" in result.output.lower()


class TestVerify:
    @patch("linkedin_sync.sync.MastodonClient", create=True)
    @patch("linkedin_sync.sync.BlueskyClient", create=True)
    @patch("linkedin_sync.sync.LinkedInClient", create=True)
    def test_verify_command(
        self, mock_li_cls, mock_bs_cls, mock_md_cls, runner, tmp_path
    ):
        mock_li_cls.return_value.get_profile.return_value = {
            "name": "Martin Eve",
            "sub": "abc123",
        }
        mock_bs_cls.return_value.handle = "test.bsky.social"
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(cli, ["--state-file", state_file, "verify"])
        assert result.exit_code == 0


class TestCliList:
    def test_list_empty(self, runner, tmp_path):
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(cli, ["--state-file", state_file, "list"])
        assert result.exit_code == 0

    def test_list_with_posts(self, runner, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "synced_posts": {
                        "https://eve.gd/a/": {
                            "post_url": "https://eve.gd/a/",
                            "post_title": "Post A",
                            "linkedin_post_urn": "urn:li:share:aaa",
                            "synced_at": "2025-03-20T12:00:00+00:00",
                            "post_published": "2025-03-20T10:00:00+00:00",
                        },
                        "https://eve.gd/b/": {
                            "post_url": "https://eve.gd/b/",
                            "post_title": "Post B",
                            "linkedin_post_urn": "urn:li:share:bbb",
                            "synced_at": "2025-03-21T12:00:00+00:00",
                            "post_published": "2025-03-21T10:00:00+00:00",
                        },
                    }
                }
            )
        )
        result = runner.invoke(cli, ["--state-file", str(state_file), "list"])
        assert result.exit_code == 0


class TestCliOptions:
    def test_json_logs_flag(self, runner, tmp_path):
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli, ["--json-logs", "--state-file", state_file, "list"]
        )
        assert result.exit_code == 0

    def test_verbose_flag(self, runner, tmp_path):
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(cli, ["-v", "--state-file", state_file, "list"])
        assert result.exit_code == 0

    def test_custom_feed_url(self, runner, tmp_path):
        state_file = str(tmp_path / "state.json")
        with patch("linkedin_sync.sync.get_todays_posts", return_value=[]):
            result = runner.invoke(
                cli,
                [
                    "--feed-url",
                    "https://custom.example.com/feed.atom",
                    "--state-file",
                    state_file,
                    "--dry-run",
                    "today",
                ],
            )
        assert result.exit_code == 0

    def test_default_command_is_today(self, runner, tmp_path):
        state_file = str(tmp_path / "state.json")
        with patch("linkedin_sync.sync.get_todays_posts", return_value=[]):
            result = runner.invoke(
                cli, ["--state-file", state_file, "--dry-run"]
            )
        assert result.exit_code == 0


class TestSyncPost:
    @patch("linkedin_sync.sync._make_clients")
    @patch("linkedin_sync.sync.get_todays_posts")
    def test_live_sync_records_state(
        self, mock_today, mock_make_clients, runner, tmp_path, env_vars
    ):
        post = _make_post()
        mock_today.return_value = [post]

        mock_li = MagicMock()
        mock_li.upload_image.return_value = None
        mock_li.create_post.return_value = "urn:li:share:live123"
        mock_make_clients.return_value = (mock_li, None, None)

        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            ["--state-file", state_file, "--no-summary", "today"],
        )

        assert result.exit_code == 0
        # Verify state was written
        with open(state_file) as f:
            state = json.load(f)
        assert post.url in state["synced_posts"]
        assert (
            state["synced_posts"][post.url]["linkedin_post_urn"]
            == "urn:li:share:live123"
        )

    @patch("linkedin_sync.sync._make_clients")
    @patch("linkedin_sync.sync.get_post_by_url")
    def test_image_failure_still_posts(
        self, mock_get, mock_make_clients, runner, tmp_path, env_vars
    ):
        from linkedin_sync.feed_parser import BlogPost

        post = BlogPost(
            id="https://eve.gd/img-post/",
            title="Image Post",
            url="https://eve.gd/img-post/",
            published=datetime(2025, 3, 20, 10, 0, tzinfo=timezone.utc),
            updated=None,
            content_html="<p>Content</p>",
            summary="Content",
            featured_image_url="https://eve.gd/images/broken.jpg",
            doi=None,
            tags=[],
        )
        mock_get.return_value = post

        mock_li = MagicMock()
        mock_li.upload_image.side_effect = Exception("Network error")
        mock_li.create_post.return_value = "urn:li:share:noimgpost"
        mock_make_clients.return_value = (mock_li, None, None)

        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--no-summary",
                "post",
                post.url,
            ],
        )

        assert result.exit_code == 0
        # Post should still have been created (without image)
        mock_li.create_post.assert_called_once()

    @patch("linkedin_sync.sync._make_clients")
    @patch("linkedin_sync.sync.get_post_by_url")
    def test_post_creation_failure(
        self, mock_get, mock_make_clients, runner, tmp_path, env_vars
    ):
        post = _make_post()
        mock_get.return_value = post

        mock_li = MagicMock()
        mock_li.create_post.side_effect = Exception("API error")
        mock_make_clients.return_value = (mock_li, None, None)

        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--no-summary",
                "post",
                post.url,
            ],
        )

        assert result.exit_code == 0
        # State should NOT have the post recorded
        state_path = Path(state_file)
        if state_path.exists():
            with open(state_file) as f:
                state = json.load(f)
            assert post.url not in state.get("synced_posts", {})


class TestMultiPlatformSync:
    @patch("linkedin_sync.sync.summarize_post_short")
    @patch("linkedin_sync.sync.summarize_post")
    @patch("linkedin_sync.sync._make_clients")
    @patch("linkedin_sync.sync.get_post_by_url")
    def test_all_platforms_success(
        self,
        mock_get,
        mock_make_clients,
        mock_summarize,
        mock_short,
        runner,
        tmp_path,
        env_vars,
    ):
        post = _make_post()
        mock_get.return_value = post
        mock_summarize.return_value = "LinkedIn summary"
        mock_short.return_value = "Short summary https://eve.gd/test/"

        mock_li = MagicMock()
        mock_li.create_post.return_value = "urn:li:share:multi"
        mock_bs = MagicMock()
        mock_bs.create_post.return_value = "https://bsky.app/profile/x/post/1"
        mock_md = MagicMock()
        mock_md.create_post.return_value = "https://mastodon.social/@x/1"
        mock_make_clients.return_value = (mock_li, mock_bs, mock_md)

        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "post",
                post.url,
            ],
        )

        assert result.exit_code == 0
        with open(state_file) as f:
            state = json.load(f)
        record = state["synced_posts"][post.url]
        assert record["linkedin_post_urn"] == "urn:li:share:multi"
        assert (
            record["bluesky_post_url"] == "https://bsky.app/profile/x/post/1"
        )
        assert record["mastodon_post_url"] == "https://mastodon.social/@x/1"

    @patch("linkedin_sync.sync.summarize_post_short")
    @patch("linkedin_sync.sync.summarize_post")
    @patch("linkedin_sync.sync._make_clients")
    @patch("linkedin_sync.sync.get_post_by_url")
    def test_partial_failure(
        self,
        mock_get,
        mock_make_clients,
        mock_summarize,
        mock_short,
        runner,
        tmp_path,
        env_vars,
    ):
        post = _make_post()
        mock_get.return_value = post
        mock_summarize.return_value = "LinkedIn summary"
        mock_short.return_value = "Short summary https://eve.gd/test/"

        mock_li = MagicMock()
        mock_li.create_post.return_value = "urn:li:share:partial"
        mock_bs = MagicMock()
        mock_bs.create_post.side_effect = Exception("Bluesky down")
        mock_md = MagicMock()
        mock_md.create_post.return_value = "https://mastodon.social/@x/2"
        mock_make_clients.return_value = (mock_li, mock_bs, mock_md)

        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "post",
                post.url,
            ],
        )

        assert result.exit_code == 0
        with open(state_file) as f:
            state = json.load(f)
        record = state["synced_posts"][post.url]
        assert record["linkedin_post_urn"] == "urn:li:share:partial"
        assert record["bluesky_post_url"] == ""
        assert record["mastodon_post_url"] == "https://mastodon.social/@x/2"

    @patch("linkedin_sync.sync.summarize_post_short")
    @patch("linkedin_sync.sync.summarize_post")
    @patch("linkedin_sync.sync._make_clients")
    @patch("linkedin_sync.sync.get_post_by_url")
    def test_all_platforms_fail_no_state(
        self,
        mock_get,
        mock_make_clients,
        mock_summarize,
        mock_short,
        runner,
        tmp_path,
        env_vars,
    ):
        post = _make_post()
        mock_get.return_value = post
        mock_summarize.return_value = "LinkedIn summary"
        mock_short.return_value = "Short summary https://eve.gd/test/"

        mock_li = MagicMock()
        mock_li.create_post.side_effect = Exception("fail")
        mock_bs = MagicMock()
        mock_bs.create_post.side_effect = Exception("fail")
        mock_md = MagicMock()
        mock_md.create_post.side_effect = Exception("fail")
        mock_make_clients.return_value = (mock_li, mock_bs, mock_md)

        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "post",
                post.url,
            ],
        )

        assert result.exit_code == 0
        state_path = Path(state_file)
        if state_path.exists():
            with open(state_file) as f:
                state = json.load(f)
            assert post.url not in state.get("synced_posts", {})


def test_version_flag(runner):
    """--version flag prints the version and exits."""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "linkedin-blog-sync" in result.output
    # Should contain a version-like string
    import re

    assert re.search(r"\d+\.\d+\.\d+", result.output)


def test_version_command(runner):
    """version subcommand prints the version and exits."""
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "linkedin-blog-sync" in result.output
    import re

    assert re.search(r"\d+\.\d+\.\d+", result.output)


class TestAutoImageCheck:
    """Test auto image-check when processing local markdown files."""

    @patch("linkedin_sync.sync.resize_image")
    @patch("linkedin_sync.sync.extract_image_paths")
    def test_file_command_runs_image_check(
        self, mock_extract, mock_resize, runner, tmp_path
    ):
        """The file command should auto-resize images before syncing."""
        md_file = tmp_path / "post.md"
        md_file.write_text(
            "---\n"
            "title: Image Post\n"
            "url: https://example.com/img-post\n"
            "date: 2026-03-21\n"
            "---\n"
            "\n"
            "![photo](photo.jpg)\n"
        )
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"fake-image")
        mock_extract.return_value = [img]

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
        mock_extract.assert_called_once_with(str(md_file))
        mock_resize.assert_called_once_with(img)

    @patch("linkedin_sync.sync.resize_image")
    @patch("linkedin_sync.sync.extract_image_paths")
    def test_post_command_with_local_file_runs_image_check(
        self, mock_extract, mock_resize, runner, tmp_path
    ):
        """The post command with a local file should auto-resize images."""
        md_file = tmp_path / "post.md"
        md_file.write_text(
            "---\n"
            "title: Image Post\n"
            "url: https://example.com/img-post2\n"
            "date: 2026-03-21\n"
            "---\n"
            "\n"
            "![photo](photo.jpg)\n"
        )
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"fake-image")
        mock_extract.return_value = [img]

        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "--no-summary",
                "post",
                str(md_file),
            ],
        )
        assert result.exit_code == 0
        mock_extract.assert_called_once_with(str(md_file))
        mock_resize.assert_called_once_with(img)

    @patch("linkedin_sync.sync.resize_image")
    @patch("linkedin_sync.sync.extract_image_paths")
    def test_post_command_with_url_skips_image_check(
        self, mock_extract, mock_resize, runner, tmp_path
    ):
        """The post command with a URL should NOT run image-check."""
        state_file = str(tmp_path / "state.json")
        runner.invoke(
            cli,
            [
                "--state-file",
                state_file,
                "--dry-run",
                "--no-summary",
                "post",
                "https://example.com/some-post",
            ],
        )
        # Exits with error (post not in feed), but should not call image check
        mock_extract.assert_not_called()
        mock_resize.assert_not_called()

    @patch("linkedin_sync.sync.resize_image")
    @patch("linkedin_sync.sync.extract_image_paths")
    def test_file_command_handles_no_images(
        self, mock_extract, mock_resize, runner, tmp_path
    ):
        """If no images found, resize should not be called."""
        md_file = tmp_path / "post.md"
        md_file.write_text(
            "---\n"
            "title: No Images\n"
            "url: https://example.com/no-img\n"
            "date: 2026-03-21\n"
            "---\n"
            "\n"
            "Just text.\n"
        )
        mock_extract.return_value = []

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
        mock_extract.assert_called_once()
        mock_resize.assert_not_called()

    @patch("linkedin_sync.sync.resize_image")
    @patch("linkedin_sync.sync.extract_image_paths")
    def test_file_command_skips_missing_images(
        self, mock_extract, mock_resize, runner, tmp_path
    ):
        """Images that don't exist on disk should be skipped."""
        md_file = tmp_path / "post.md"
        md_file.write_text(
            "---\n"
            "title: Missing Image\n"
            "url: https://example.com/missing\n"
            "date: 2026-03-21\n"
            "---\n"
            "\n"
            "![photo](photo.jpg)\n"
        )
        nonexistent = tmp_path / "photo.jpg"  # does NOT exist
        mock_extract.return_value = [nonexistent]

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
        mock_resize.assert_not_called()

    @patch("linkedin_sync.sync.resize_image")
    @patch("linkedin_sync.sync.extract_image_paths")
    def test_file_command_multiple_images_all_resized(
        self, mock_extract, mock_resize, runner, tmp_path
    ):
        """All found images should be resized."""
        md_file = tmp_path / "post.md"
        md_file.write_text(
            "---\n"
            "title: Multi Image\n"
            "url: https://example.com/multi\n"
            "date: 2026-03-21\n"
            "---\n"
            "\n"
            "![a](a.jpg)\n![b](b.png)\n"
        )
        img_a = tmp_path / "a.jpg"
        img_b = tmp_path / "b.png"
        img_a.write_bytes(b"fake-a")
        img_b.write_bytes(b"fake-b")
        mock_extract.return_value = [img_a, img_b]

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
        assert mock_resize.call_count == 2
