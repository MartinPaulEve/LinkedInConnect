"""Tests for the Mastodon client."""

from unittest.mock import MagicMock, patch

import pytest


class TestMastodonClientInit:
    def test_missing_instance_url_raises(self, monkeypatch):
        monkeypatch.delenv("MASTODON_INSTANCE_URL", raising=False)
        monkeypatch.delenv("MASTODON_ACCESS_TOKEN", raising=False)

        from mastodon_client import MastodonClient

        with pytest.raises(ValueError, match="instance URL"):
            MastodonClient()

    def test_missing_access_token_raises(self, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.delenv("MASTODON_ACCESS_TOKEN", raising=False)

        from mastodon_client import MastodonClient

        with pytest.raises(ValueError, match="access token"):
            MastodonClient()

    @patch("mastodon_client.Mastodon")
    def test_init_from_env(self, mock_mastodon_cls, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        from mastodon_client import MastodonClient

        client = MastodonClient()
        assert client.instance_url == "https://mastodon.social"
        mock_mastodon_cls.assert_called_once_with(
            access_token="test-token",
            api_base_url="https://mastodon.social",
        )

    @patch("mastodon_client.Mastodon")
    def test_strips_trailing_slash(self, mock_mastodon_cls, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social/")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        from mastodon_client import MastodonClient

        client = MastodonClient()
        assert client.instance_url == "https://mastodon.social"


class TestMastodonCreatePost:
    @patch("mastodon_client.Mastodon")
    def test_creates_post(self, mock_mastodon_cls, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.status_post.return_value = {
            "url": "https://mastodon.social/@test/123",
            "id": "123",
        }
        mock_mastodon_cls.return_value = mock_api

        from mastodon_client import MastodonClient

        client = MastodonClient()
        url = client.create_post(text="Hello Mastodon")

        assert url == "https://mastodon.social/@test/123"
        mock_api.status_post.assert_called_once_with(
            "Hello Mastodon",
            visibility="public",
            language="en",
        )

    @patch("mastodon_client.Mastodon")
    def test_custom_visibility(self, mock_mastodon_cls, monkeypatch):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.status_post.return_value = {
            "url": "https://mastodon.social/@test/456",
        }
        mock_mastodon_cls.return_value = mock_api

        from mastodon_client import MastodonClient

        client = MastodonClient()
        client.create_post(text="Private toot", visibility="unlisted")

        mock_api.status_post.assert_called_once_with(
            "Private toot",
            visibility="unlisted",
            language="en",
        )
