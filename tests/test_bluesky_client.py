"""Tests for the Bluesky client."""

from unittest.mock import MagicMock, patch

import pytest


class TestBlueskyClientInit:
    def test_missing_handle_raises(self, monkeypatch):
        monkeypatch.delenv("BLUESKY_HANDLE", raising=False)
        monkeypatch.delenv("BLUESKY_APP_PASSWORD", raising=False)

        from bluesky_client import BlueskyClient

        with pytest.raises(ValueError, match="handle"):
            BlueskyClient()

    def test_missing_password_raises(self, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.delenv("BLUESKY_APP_PASSWORD", raising=False)

        from bluesky_client import BlueskyClient

        with pytest.raises(ValueError, match="app password"):
            BlueskyClient()

    @patch("bluesky_client.Client")
    def test_init_from_env(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        from bluesky_client import BlueskyClient

        client = BlueskyClient()
        assert client.handle == "test.bsky.social"
        mock_client_cls.return_value.login.assert_called_once_with(
            "test.bsky.social", "test-pass"
        )


class TestBlueskyCreatePost:
    @patch("bluesky_client.Client")
    def test_text_only_post(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/xyz"
        )
        mock_client_cls.return_value = mock_client

        from bluesky_client import BlueskyClient

        client = BlueskyClient()
        url = client.create_post(text="Hello Bluesky")

        assert "bsky.app" in url
        mock_client.send_post.assert_called_once()

    @patch("bluesky_client.Client")
    def test_post_with_link_card(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/xyz"
        )
        mock_client_cls.return_value = mock_client

        from bluesky_client import BlueskyClient

        client = BlueskyClient()
        url = client.create_post(
            text="Check this out",
            link_url="https://eve.gd/post/",
            link_title="My Post",
            link_description="A great post",
        )

        assert "bsky.app" in url
        call_kwargs = mock_client.send_post.call_args[1]
        assert call_kwargs["embed"] is not None


class TestUriToUrl:
    @patch("bluesky_client.Client")
    def test_converts_at_uri(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        from bluesky_client import BlueskyClient

        client = BlueskyClient()
        url = client._uri_to_url(
            "at://did:plc:abc123/app.bsky.feed.post/rkey456"
        )
        assert url == (
            "https://bsky.app/profile/test.bsky.social/post/rkey456"
        )

    @patch("bluesky_client.Client")
    def test_returns_uri_if_no_match(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        from bluesky_client import BlueskyClient

        client = BlueskyClient()
        uri = "at://something/unexpected"
        assert client._uri_to_url(uri) == uri
