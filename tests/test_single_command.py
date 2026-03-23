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

    @patch("linkedin_sync.sync._make_clients")
    def test_long_message_threads_on_bluesky(self, mock_mc, runner):
        """A message over 300 chars should use create_thread on Bluesky."""
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:t"
        bs = MagicMock()
        bs.create_thread.return_value = "https://bsky.app/post/thread"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/t"
        mock_mc.return_value = (li, bs, md)

        # 350+ chars, exceeds Bluesky's 300 limit
        msg = "word " * 71  # 355 chars
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        bs.create_post.assert_not_called()
        bs.create_thread.assert_called_once()
        # Verify chunks were passed
        chunks = bs.create_thread.call_args[0][0]
        assert len(chunks) >= 2
        for chunk in chunks:
            assert "🧵" in chunk

    @patch("linkedin_sync.sync._make_clients")
    def test_long_message_threads_on_mastodon(self, mock_mc, runner):
        """A message over 500 chars should use create_thread on Mastodon."""
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:t"
        bs = MagicMock()
        bs.create_thread.return_value = "https://bsky.app/post/thread"
        md = MagicMock()
        md.create_thread.return_value = "https://mastodon.social/@u/thread"
        mock_mc.return_value = (li, bs, md)

        # 600+ chars, exceeds Mastodon's 500 limit
        msg = "word " * 121  # 605 chars
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        md.create_post.assert_not_called()
        md.create_thread.assert_called_once()
        chunks = md.create_thread.call_args[0][0]
        assert len(chunks) >= 2

    @patch("linkedin_sync.sync._make_clients")
    def test_short_message_does_not_thread(self, mock_mc, runner):
        """A short message should use create_post, not create_thread."""
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:t"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/t"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/t"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(cli, ["single", "Short message"])
        assert result.exit_code == 0

        bs.create_post.assert_called_once()
        bs.create_thread.assert_not_called()
        md.create_post.assert_called_once()
        md.create_thread.assert_not_called()

    @patch("linkedin_sync.sync._make_clients")
    def test_linkedin_never_threads(self, mock_mc, runner):
        """LinkedIn should always use create_post, even for long messages."""
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:t"
        bs = MagicMock()
        bs.create_thread.return_value = "https://bsky.app/post/thread"
        md = MagicMock()
        md.create_thread.return_value = "https://mastodon.social/@u/thread"
        mock_mc.return_value = (li, bs, md)

        msg = "word " * 200  # 1000 chars
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        li.create_post.assert_called_once()
        li.create_thread.assert_not_called()

    @patch("linkedin_sync.sync._make_clients")
    def test_bluesky_thread_gets_link_url(self, mock_mc, runner):
        """When threading on Bluesky, link_url should be passed."""
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:t"
        bs = MagicMock()
        bs.create_thread.return_value = "https://bsky.app/post/thread"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/t"
        mock_mc.return_value = (li, bs, md)

        msg = "word " * 60 + "https://example.com/article"
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        bs_kwargs = bs.create_thread.call_args[1]
        assert bs_kwargs["link_url"] == "https://example.com/article"

    @patch("linkedin_sync.sync._make_clients")
    def test_dry_run_shows_threading_breakdown(self, mock_mc, runner):
        """Dry run for long message should show thread chunk info."""
        mock_mc.return_value = (MagicMock(), MagicMock(), MagicMock())

        msg = "word " * 71  # 355 chars, threads on Bluesky
        result = runner.invoke(cli, ["--dry-run", "single", msg])
        assert result.exit_code == 0

        # Should not have posted anything
        li, bs, md = mock_mc.return_value
        li.create_post.assert_not_called()
        bs.create_post.assert_not_called()
        bs.create_thread.assert_not_called()
        md.create_post.assert_not_called()
        md.create_thread.assert_not_called()

    @patch("linkedin_sync.sync.fetch_og_metadata")
    @patch("linkedin_sync.sync._make_clients")
    def test_url_message_fetches_og_and_passes_to_platforms(
        self, mock_mc, mock_og, runner
    ):
        """When a URL is present, OG metadata should be fetched and
        passed to Bluesky (thumbnail_url, link_title, link_description)
        and LinkedIn (article_title, article_description)."""
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:789"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/3"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/3"
        mock_mc.return_value = (li, bs, md)

        mock_og.return_value = {
            "title": "OG Title",
            "description": "OG Desc",
            "image": "https://eve.gd/images/thumb.jpg",
        }

        result = runner.invoke(
            cli,
            [
                "single",
                "Check this out https://eve.gd/2026/03/23/article/",
            ],
        )
        assert result.exit_code == 0

        # Bluesky should receive OG metadata
        bs_kwargs = bs.create_post.call_args.kwargs
        assert bs_kwargs["link_url"] == "https://eve.gd/2026/03/23/article/"
        assert bs_kwargs["thumbnail_url"] == "https://eve.gd/images/thumb.jpg"
        assert bs_kwargs["link_title"] == "OG Title"
        assert bs_kwargs["link_description"] == "OG Desc"

        # LinkedIn should receive OG title/description
        li_kwargs = li.create_post.call_args.kwargs
        assert li_kwargs["article_url"] == "https://eve.gd/2026/03/23/article/"
        assert li_kwargs["article_title"] == "OG Title"
        assert li_kwargs["article_description"] == "OG Desc"

    @patch("linkedin_sync.sync.fetch_og_metadata")
    @patch("linkedin_sync.sync._make_clients")
    def test_og_not_fetched_when_no_url(self, mock_mc, mock_og, runner):
        """OG metadata should not be fetched for plain text messages."""
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:999"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/4"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/4"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(cli, ["single", "No URL here"])
        assert result.exit_code == 0
        mock_og.assert_not_called()

    @patch("linkedin_sync.sync.fetch_og_metadata")
    @patch("linkedin_sync.sync._make_clients")
    def test_og_not_fetched_when_local_images_present(
        self, mock_mc, mock_og, runner, tmp_path
    ):
        """OG fetch should be skipped when local images are attached."""
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:111"
        li.upload_image.return_value = "urn:li:image:111"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/5"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/5"
        mock_mc.return_value = (li, bs, md)

        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        result = runner.invoke(
            cli,
            [
                "single",
                f"Nice pic https://example.com/post {img}",
            ],
        )
        assert result.exit_code == 0
        mock_og.assert_not_called()
