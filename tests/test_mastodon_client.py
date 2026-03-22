"""Tests for the Mastodon client."""

from unittest.mock import MagicMock, patch

import pytest


class TestMastodonClientInit:
    def test_missing_instance_url_raises(self, monkeypatch):
        monkeypatch.delenv("MASTODON_INSTANCE_URL", raising=False)
        monkeypatch.delenv("MASTODON_ACCESS_TOKEN", raising=False)

        from linkedin_sync.mastodon_client import MastodonClient

        with pytest.raises(ValueError, match="instance URL"):
            MastodonClient()

    def test_missing_access_token_raises(self, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.delenv("MASTODON_ACCESS_TOKEN", raising=False)

        from linkedin_sync.mastodon_client import MastodonClient

        with pytest.raises(ValueError, match="access token"):
            MastodonClient()

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_init_from_env(self, mock_mastodon_cls, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        assert client.instance_url == "https://mastodon.social"
        mock_mastodon_cls.assert_called_once_with(
            access_token="test-token",
            api_base_url="https://mastodon.social",
        )

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_strips_trailing_slash(self, mock_mastodon_cls, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social/")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        assert client.instance_url == "https://mastodon.social"


class TestMastodonCreatePost:
    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_creates_post(self, mock_mastodon_cls, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.status_post.return_value = {
            "url": "https://mastodon.social/@test/123",
            "id": "123",
        }
        mock_mastodon_cls.return_value = mock_api

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        url = client.create_post(text="Hello Mastodon")

        assert url == "https://mastodon.social/@test/123"
        mock_api.status_post.assert_called_once_with(
            "Hello Mastodon",
            visibility="public",
            language="en",
        )

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_custom_visibility(self, mock_mastodon_cls, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.status_post.return_value = {
            "url": "https://mastodon.social/@test/456",
        }
        mock_mastodon_cls.return_value = mock_api

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        client.create_post(text="Private toot", visibility="unlisted")

        mock_api.status_post.assert_called_once_with(
            "Private toot",
            visibility="unlisted",
            language="en",
        )


class TestMastodonCreateThread:
    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_thread_two_chunks(self, mock_mastodon_cls, monkeypatch):
        """Two-chunk thread calls status_post twice with reply."""
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        first_status = {
            "url": "https://mastodon.social/@test/100",
            "id": "100",
        }
        second_status = {
            "url": "https://mastodon.social/@test/101",
            "id": "101",
        }
        mock_api.status_post.side_effect = [first_status, second_status]
        mock_mastodon_cls.return_value = mock_api

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        url = client.create_thread(["Part 1 🧵1/2", "Part 2 🧵2/2"])

        assert url == "https://mastodon.social/@test/100"
        assert mock_api.status_post.call_count == 2

        # First call: no in_reply_to_id
        first_call = mock_api.status_post.call_args_list[0]
        assert first_call[1].get("in_reply_to_id") is None

        # Second call: in_reply_to_id = first status id
        second_call = mock_api.status_post.call_args_list[1]
        assert second_call[1]["in_reply_to_id"] == "100"

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_three_chunk_chain(self, mock_mastodon_cls, monkeypatch):
        """Three-post thread chains IDs correctly."""
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.status_post.side_effect = [
            {"url": "https://mastodon.social/@t/1", "id": "1"},
            {"url": "https://mastodon.social/@t/2", "id": "2"},
            {"url": "https://mastodon.social/@t/3", "id": "3"},
        ]
        mock_mastodon_cls.return_value = mock_api

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        url = client.create_thread(
            ["Part 1 🧵1/3", "Part 2 🧵2/3", "Part 3 🧵3/3"]
        )

        assert url == "https://mastodon.social/@t/1"
        # Post 2 replies to post 1
        calls = mock_api.status_post.call_args_list
        assert calls[1][1]["in_reply_to_id"] == "1"
        # Post 3 replies to post 2
        assert calls[2][1]["in_reply_to_id"] == "2"

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_returns_first_post_url(self, mock_mastodon_cls, monkeypatch):
        """create_thread should return the URL of the first status."""
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.status_post.side_effect = [
            {"url": "https://mastodon.social/@t/first", "id": "first"},
            {"url": "https://mastodon.social/@t/second", "id": "second"},
        ]
        mock_mastodon_cls.return_value = mock_api

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        url = client.create_thread(["Part 1 🧵1/2", "Part 2 🧵2/2"])

        assert url == "https://mastodon.social/@t/first"
