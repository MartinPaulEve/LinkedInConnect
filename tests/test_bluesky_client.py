"""Tests for the Bluesky client."""

from unittest.mock import MagicMock, patch

import pytest
import requests


class TestBlueskyClientInit:
    def test_missing_handle_raises(self, monkeypatch):
        monkeypatch.delenv("BLUESKY_HANDLE", raising=False)
        monkeypatch.delenv("BLUESKY_APP_PASSWORD", raising=False)

        from linkedin_sync.bluesky_client import BlueskyClient

        with pytest.raises(ValueError, match="handle"):
            BlueskyClient()

    def test_missing_password_raises(self, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.delenv("BLUESKY_APP_PASSWORD", raising=False)

        from linkedin_sync.bluesky_client import BlueskyClient

        with pytest.raises(ValueError, match="app password"):
            BlueskyClient()

    @patch("linkedin_sync.bluesky_client.Client")
    def test_init_from_env(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        assert client.handle == "test.bsky.social"
        mock_client_cls.return_value.login.assert_called_once_with(
            "test.bsky.social", "test-pass"
        )


class TestBlueskyCreatePost:
    @patch("linkedin_sync.bluesky_client.Client")
    def test_text_only_post(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/xyz"
        )
        mock_client_cls.return_value = mock_client

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        url = client.create_post(text="Hello Bluesky")

        assert "bsky.app" in url
        mock_client.send_post.assert_called_once()

    @patch("linkedin_sync.bluesky_client.Client")
    def test_post_with_link_card(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/xyz"
        )
        mock_client_cls.return_value = mock_client

        from linkedin_sync.bluesky_client import BlueskyClient

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


class TestBlueskyThumbnail:
    @patch("linkedin_sync.bluesky_client.requests.get")
    @patch("linkedin_sync.bluesky_client.Client")
    def test_post_with_thumbnail(
        self, mock_client_cls, mock_requests_get, monkeypatch
    ):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        from atproto_client.models.blob_ref import BlobRef

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/xyz"
        )
        mock_blob = MagicMock(spec=BlobRef)
        mock_client.upload_blob.return_value = MagicMock(blob=mock_blob)
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = b"fake-image-bytes"
        mock_response.raise_for_status = MagicMock()
        mock_requests_get.return_value = mock_response

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        url = client.create_post(
            text="Check this out",
            link_url="https://eve.gd/post/",
            link_title="My Post",
            link_description="A great post",
            thumbnail_url="https://eve.gd/image.jpg",
        )

        assert "bsky.app" in url
        mock_requests_get.assert_called_once_with(
            "https://eve.gd/image.jpg", timeout=15
        )
        mock_client.upload_blob.assert_called_once_with(b"fake-image-bytes")
        call_kwargs = mock_client.send_post.call_args[1]
        assert call_kwargs["embed"].external.thumb == mock_blob

    @patch("linkedin_sync.bluesky_client.requests.get")
    @patch("linkedin_sync.bluesky_client.Client")
    def test_thumbnail_failure_still_posts(
        self, mock_client_cls, mock_requests_get, monkeypatch
    ):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/xyz"
        )
        mock_client_cls.return_value = mock_client

        mock_requests_get.side_effect = requests.RequestException("timeout")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        url = client.create_post(
            text="Check this out",
            link_url="https://eve.gd/post/",
            link_title="My Post",
            thumbnail_url="https://eve.gd/broken.jpg",
        )

        # Post should still succeed, just without thumbnail
        assert "bsky.app" in url
        call_kwargs = mock_client.send_post.call_args[1]
        assert call_kwargs["embed"].external.thumb is None

    @patch("linkedin_sync.bluesky_client.Client")
    def test_post_without_thumbnail(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/xyz"
        )
        mock_client_cls.return_value = mock_client

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        url = client.create_post(
            text="Check this out",
            link_url="https://eve.gd/post/",
            link_title="My Post",
        )

        assert "bsky.app" in url
        call_kwargs = mock_client.send_post.call_args[1]
        assert call_kwargs["embed"].external.thumb is None


class TestBuildTextWithLinks:
    def test_plain_text_no_links(self):
        from linkedin_sync.bluesky_client import _build_text_with_links

        builder = _build_text_with_links("Hello world")
        assert builder.build_text() == "Hello world"

    def test_text_with_url_creates_facet(self):
        from linkedin_sync.bluesky_client import _build_text_with_links

        text = "Check out https://eve.gd/post/ for details"
        builder = _build_text_with_links(text)
        built = builder.build_text()
        assert "https://eve.gd/post/" in built

    def test_text_with_trailing_url(self):
        from linkedin_sync.bluesky_client import _build_text_with_links

        text = "My summary.\n\nhttps://eve.gd/2026/03/21/test/"
        builder = _build_text_with_links(text)
        built = builder.build_text()
        assert "https://eve.gd/2026/03/21/test/" in built


class TestBlueskyCreateThread:
    @patch("linkedin_sync.bluesky_client.Client")
    def test_thread_two_chunks(self, mock_client_cls, monkeypatch):
        """Two-chunk thread calls send_post twice, second with reply_to."""
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        first_resp = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/first",
            cid="cid-first",
        )
        second_resp = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/second",
            cid="cid-second",
        )
        mock_client.send_post.side_effect = [first_resp, second_resp]
        mock_client_cls.return_value = mock_client

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_thread(["Part one 🧵1/2", "Part two 🧵2/2"])

        assert mock_client.send_post.call_count == 2
        # First call should have no reply_to
        first_call = mock_client.send_post.call_args_list[0]
        assert first_call[1].get("reply_to") is None
        # Second call should have reply_to
        second_call = mock_client.send_post.call_args_list[1]
        assert second_call[1].get("reply_to") is not None

    @patch("linkedin_sync.bluesky_client.Client")
    def test_first_post_gets_embed(self, mock_client_cls, monkeypatch):
        """Only the first post in a thread should get the link card embed."""
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/xyz",
            cid="cid-xyz",
        )
        mock_client_cls.return_value = mock_client

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_thread(
            ["Part 1 🧵1/2", "Part 2 🧵2/2"],
            link_url="https://eve.gd/post/",
            link_title="My Post",
        )

        first_call = mock_client.send_post.call_args_list[0]
        assert first_call[1]["embed"] is not None
        second_call = mock_client.send_post.call_args_list[1]
        assert second_call[1].get("embed") is None

    @patch("linkedin_sync.bluesky_client.Client")
    def test_returns_first_post_url(self, mock_client_cls, monkeypatch):
        """create_thread should return the URL of the first post."""
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/first",
            cid="cid-first",
        )
        mock_client_cls.return_value = mock_client

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        url = client.create_thread(["Part 1 🧵1/2", "Part 2 🧵2/2"])

        assert "bsky.app" in url
        assert "first" in url

    @patch("linkedin_sync.bluesky_client.Client")
    def test_reply_ref_references_root_and_parent(
        self, mock_client_cls, monkeypatch
    ):
        """For a 3-post thread, post 3 should ref root=post1, parent=post2."""
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        resp1 = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/r1", cid="cid1"
        )
        resp2 = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/r2", cid="cid2"
        )
        resp3 = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/r3", cid="cid3"
        )
        mock_client.send_post.side_effect = [resp1, resp2, resp3]
        mock_client_cls.return_value = mock_client

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_thread(
            ["Part 1 🧵1/3", "Part 2 🧵2/3", "Part 3 🧵3/3"]
        )

        assert mock_client.send_post.call_count == 3
        # Third call's reply_to should reference root and parent
        third_call = mock_client.send_post.call_args_list[2]
        reply_to = third_call[1]["reply_to"]
        assert reply_to.root.uri == resp1.uri
        assert reply_to.parent.uri == resp2.uri


class TestUriToUrl:
    @patch("linkedin_sync.bluesky_client.Client")
    def test_converts_at_uri(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        url = client._uri_to_url(
            "at://did:plc:abc123/app.bsky.feed.post/rkey456"
        )
        assert url == (
            "https://bsky.app/profile/test.bsky.social/post/rkey456"
        )

    @patch("linkedin_sync.bluesky_client.Client")
    def test_returns_uri_if_no_match(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        uri = "at://something/unexpected"
        assert client._uri_to_url(uri) == uri
