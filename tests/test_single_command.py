"""Tests for the single (ad-hoc message) CLI command."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from linkedin_sync.sync import cli


@pytest.fixture
def runner():
    return CliRunner()


class TestSingleCommand:
    """Tests for the 'single' subcommand."""

    @patch("linkedin_sync.sync._make_clients")
    def test_posts_plain_text_to_all_platforms(self, mock_mc, runner):
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:123"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(cli, ["single", "Just a quick thought"])
        assert result.exit_code == 0

        li.create_post.assert_called_once()
        bs.create_post.assert_called_once()
        md.create_post.assert_called_once()

        # No link card args for plain text
        li_kwargs = li.create_post.call_args
        assert li_kwargs.kwargs.get("article_url") is None

        bs_kwargs = bs.create_post.call_args
        assert bs_kwargs.kwargs.get("link_url") is None

    @patch("linkedin_sync.sync._make_clients")
    def test_message_with_url_creates_link_cards(self, mock_mc, runner):
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/2"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/2"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli,
            [
                "single",
                "Had a hospital appointment today https://example.com/post",
            ],
        )
        assert result.exit_code == 0

        # LinkedIn should get an article embed for the URL
        li_kwargs = li.create_post.call_args.kwargs
        assert li_kwargs["article_url"] == "https://example.com/post"

        # Bluesky should get a link card
        bs_kwargs = bs.create_post.call_args.kwargs
        assert bs_kwargs["link_url"] == "https://example.com/post"

    @patch("linkedin_sync.sync._make_clients")
    def test_multiple_urls_uses_last(self, mock_mc, runner):
        """When multiple URLs appear, the last one is used for link cards."""
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:789"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/3"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/3"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli,
            [
                "single",
                "Check https://first.com and https://second.com",
            ],
        )
        assert result.exit_code == 0

        li_kwargs = li.create_post.call_args.kwargs
        assert li_kwargs["article_url"] == "https://second.com"

    @patch("linkedin_sync.sync._make_clients")
    def test_dry_run_does_not_post(self, mock_mc, runner):
        li = MagicMock()
        bs = MagicMock()
        md = MagicMock()
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(cli, ["--dry-run", "single", "Dry run test"])
        assert result.exit_code == 0

        li.create_post.assert_not_called()
        bs.create_post.assert_not_called()
        md.create_post.assert_not_called()

    @patch("linkedin_sync.sync._make_clients")
    def test_only_flag_limits_platforms(self, mock_mc, runner):
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:999"
        mock_mc.return_value = (li, None, None)

        result = runner.invoke(
            cli,
            ["--only", "linkedin", "single", "LinkedIn only"],
        )
        assert result.exit_code == 0

        li.create_post.assert_called_once()
        # bluesky and mastodon clients are None, so no calls

    @patch("linkedin_sync.sync._make_clients")
    def test_skips_absent_clients(self, mock_mc, runner):
        """When a client is None, the command should not crash."""
        mock_mc.return_value = (None, None, None)

        result = runner.invoke(cli, ["single", "No clients configured"])
        assert result.exit_code == 0

    @patch("linkedin_sync.sync._make_clients")
    def test_client_error_logged_not_fatal(self, mock_mc, runner):
        """If one platform fails, the command still succeeds."""
        li = MagicMock()
        li.create_post.side_effect = RuntimeError("API down")
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/ok"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/ok"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(cli, ["single", "Post despite error"])
        assert result.exit_code == 0

        bs.create_post.assert_called_once()
        md.create_post.assert_called_once()

    @patch("linkedin_sync.sync._make_clients")
    def test_mastodon_receives_full_text(self, mock_mc, runner):
        """Mastodon gets the full message text as-is."""
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:t"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/t"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/t"
        mock_mc.return_value = (li, bs, md)

        msg = "Hello world https://example.com"
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        md_kwargs = md.create_post.call_args.kwargs
        assert md_kwargs["text"] == msg
