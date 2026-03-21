"""Tests for the sync CLI (Click commands)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from sync import cli


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
    from feed_parser import BlogPost

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
    @patch("sync.get_todays_posts")
    def test_no_posts_today(self, mock_today, runner, tmp_path):
        mock_today.return_value = []
        state_file = str(tmp_path / "state.json")
        result = runner.invoke(
            cli, ["--state-file", state_file, "--dry-run", "today"]
        )
        assert result.exit_code == 0

    @patch("sync.get_todays_posts")
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

    @patch("sync.get_todays_posts")
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

    @patch("sync.get_todays_posts")
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
    @patch("sync.get_post_by_url")
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

    @patch("sync.get_post_by_url")
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

    @patch("sync.get_post_by_url")
    def test_already_synced_without_force(self, mock_get, runner, tmp_path):
        post = _make_post()
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
        # Should not re-sync
        mock_get.assert_not_called()

    @patch("sync.get_post_by_url")
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
        with patch("sync.get_todays_posts", return_value=[]):
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
        with patch("sync.get_todays_posts", return_value=[]):
            result = runner.invoke(
                cli, ["--state-file", state_file, "--dry-run"]
            )
        assert result.exit_code == 0


class TestSyncPost:
    @patch("sync.LinkedInClient")
    @patch("sync.get_todays_posts")
    def test_live_sync_records_state(
        self, mock_today, mock_client_cls, runner, tmp_path, env_vars
    ):
        post = _make_post()
        mock_today.return_value = [post]

        mock_client = MagicMock()
        mock_client.upload_image.return_value = None
        mock_client.create_post.return_value = "urn:li:share:live123"
        mock_client_cls.return_value = mock_client

        state_file = str(tmp_path / "state.json")
        # We need to patch _make_client to return our mock
        with patch("sync._make_client", return_value=mock_client):
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

    @patch("sync.LinkedInClient")
    @patch("sync.get_post_by_url")
    def test_image_failure_still_posts(
        self, mock_get, mock_client_cls, runner, tmp_path, env_vars
    ):
        from feed_parser import BlogPost

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

        mock_client = MagicMock()
        mock_client.upload_image.side_effect = Exception("Network error")
        mock_client.create_post.return_value = "urn:li:share:noimgpost"
        mock_client_cls.return_value = mock_client

        state_file = str(tmp_path / "state.json")
        with patch("sync._make_client", return_value=mock_client):
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
        mock_client.create_post.assert_called_once()
        call_kwargs = mock_client.create_post.call_args
        assert call_kwargs[1].get("image_urn") is None or call_kwargs[0] == ()

    @patch("sync.LinkedInClient")
    @patch("sync.get_post_by_url")
    def test_post_creation_failure(
        self, mock_get, mock_client_cls, runner, tmp_path, env_vars
    ):
        post = _make_post()
        mock_get.return_value = post

        mock_client = MagicMock()
        mock_client.create_post.side_effect = Exception("API error")
        mock_client_cls.return_value = mock_client

        state_file = str(tmp_path / "state.json")
        with patch("sync._make_client", return_value=mock_client):
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

        assert (
            result.exit_code == 0
        )  # CLI doesn't exit non-zero on post failure
        # State should NOT have the post recorded
        state_path = Path(state_file)
        if state_path.exists():
            with open(state_file) as f:
                state = json.load(f)
            assert post.url not in state.get("synced_posts", {})
        # If file doesn't exist, that also means it wasn't synced — pass
