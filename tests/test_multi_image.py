"""Tests for multi-image support in the single command."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from linkedin_sync.sync import (
    _extract_all_local_media,
    cli,
)


# -------------------------------------------------------------------
# _extract_all_local_media
# -------------------------------------------------------------------
class TestExtractAllLocalMedia:
    """Test extraction of multiple local media paths from a message."""

    def test_no_media_returns_empty_list(self):
        clean, media = _extract_all_local_media("Just a plain message")
        assert clean == "Just a plain message"
        assert media == []

    def test_single_image_extracted(self, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake")
        msg = f"Check this out {img} cool"
        clean, media = _extract_all_local_media(msg)
        assert len(media) == 1
        assert media[0][0] == str(img)
        assert str(img) not in clean
        assert clean == "Check this out cool"

    def test_two_images_extracted(self, tmp_path):
        img1 = tmp_path / "one.png"
        img2 = tmp_path / "two.jpg"
        img1.write_bytes(b"fake1")
        img2.write_bytes(b"fake2")
        msg = f"First {img1} and second {img2} done"
        clean, media = _extract_all_local_media(msg)
        assert len(media) == 2
        assert media[0][0] == str(img1)
        assert media[1][0] == str(img2)
        assert str(img1) not in clean
        assert str(img2) not in clean
        assert clean == "First and second done"

    def test_three_images_with_alt_text(self, tmp_path):
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.jpg"
        img3 = tmp_path / "c.webp"
        for img in (img1, img2, img3):
            img.write_bytes(b"fake")
        msg = (
            f"Start {img1} [Alt one] "
            f"middle {img2} [Alt two] "
            f"end {img3} [Alt three]"
        )
        clean, media = _extract_all_local_media(msg)
        assert len(media) == 3
        assert media[0][1] == "Alt one"
        assert media[1][1] == "Alt two"
        assert media[2][1] == "Alt three"
        assert "[Alt one]" not in clean
        assert "[Alt two]" not in clean
        assert "[Alt three]" not in clean

    def test_mixed_alt_and_no_alt(self, tmp_path):
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"fake")
        img2.write_bytes(b"fake")
        msg = f"First {img1} [Has alt] second {img2} done"
        _clean, media = _extract_all_local_media(msg)
        assert media[0][1] == "Has alt"
        assert media[1][1] is None

    def test_char_positions_tracked(self, tmp_path):
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"fake")
        img2.write_bytes(b"fake")
        # img1 near start, img2 near end
        msg = f"{img1} " + "x" * 400 + f" {img2}"
        _clean, media = _extract_all_local_media(msg)
        # First image should have a smaller char position
        assert media[0][2] < media[1][2]

    def test_nonexistent_file_skipped(self, tmp_path):
        img = tmp_path / "real.png"
        img.write_bytes(b"fake")
        msg = f"See {img} and /nonexistent/fake.jpg here"
        _clean, media = _extract_all_local_media(msg)
        assert len(media) == 1
        assert media[0][0] == str(img)

    def test_video_and_image_both_extracted(self, tmp_path):
        img = tmp_path / "photo.png"
        vid = tmp_path / "clip.mp4"
        img.write_bytes(b"fake")
        vid.write_bytes(b"fake")
        msg = f"See {img} and {vid} here"
        _clean, media = _extract_all_local_media(msg)
        assert len(media) == 2

    def test_url_not_matched(self):
        msg = "See https://example.com/image.png for details"
        clean, media = _extract_all_local_media(msg)
        assert media == []
        assert clean == msg


# -------------------------------------------------------------------
# LinkedIn multi-image
# -------------------------------------------------------------------
class TestLinkedInMultiImage:
    """Test LinkedIn client support for multiple images."""

    @patch("linkedin_sync.linkedin_client.requests.Session")
    @patch("linkedin_sync.linkedin_client.requests.put")
    def test_create_post_with_multiple_image_urns(
        self, mock_put, mock_session_cls, monkeypatch
    ):
        monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("LINKEDIN_PERSON_URN", "urn:li:person:test")

        mock_session = MagicMock()
        # Mock userinfo to fail so it falls back to explicit URN
        mock_session.get.return_value = MagicMock(ok=False)
        # Mock create_post response
        post_resp = MagicMock(ok=True)
        post_resp.headers = {"x-restli-id": "urn:li:share:multi"}
        mock_session.post.return_value = post_resp
        mock_session_cls.return_value = mock_session

        from linkedin_sync.linkedin_client import LinkedInClient

        client = LinkedInClient()
        result = client.create_post(
            text="Multiple images",
            image_urns=[
                "urn:li:image:1",
                "urn:li:image:2",
                "urn:li:image:3",
            ],
            image_alt_texts=["Alt 1", "Alt 2", "Alt 3"],
        )
        assert result == "urn:li:share:multi"

        # Verify the POST body uses multiImage
        call_kwargs = mock_session.post.call_args
        body = call_kwargs[1]["json"]
        assert "multiImage" in body["content"]
        images = body["content"]["multiImage"]["images"]
        assert len(images) == 3
        assert images[0]["id"] == "urn:li:image:1"
        assert images[0]["altText"] == "Alt 1"

    @patch("linkedin_sync.linkedin_client.requests.Session")
    @patch("linkedin_sync.linkedin_client.requests.put")
    def test_single_image_urn_in_list_uses_media(
        self, mock_put, mock_session_cls, monkeypatch
    ):
        """A single image in image_urns should use media, not multiImage."""
        monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("LINKEDIN_PERSON_URN", "urn:li:person:test")

        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(ok=False)
        post_resp = MagicMock(ok=True)
        post_resp.headers = {"x-restli-id": "urn:li:share:single"}
        mock_session.post.return_value = post_resp
        mock_session_cls.return_value = mock_session

        from linkedin_sync.linkedin_client import LinkedInClient

        client = LinkedInClient()
        client.create_post(
            text="One image",
            image_urns=["urn:li:image:1"],
            image_alt_texts=["Alt 1"],
        )

        call_kwargs = mock_session.post.call_args
        body = call_kwargs[1]["json"]
        assert "media" in body["content"]
        assert body["content"]["media"]["id"] == "urn:li:image:1"


# -------------------------------------------------------------------
# Bluesky multi-image
# -------------------------------------------------------------------
class TestBlueskyMultiImage:
    """Test Bluesky client support for multiple images."""

    @staticmethod
    def _make_blob_ref():
        from atproto_client.models.blob_ref import BlobRef

        link = "bafkreibme22gw2h7y2h7tg2fhqotaqjucnbc24deqo72b6mkl2egezxhvy"
        return BlobRef(
            mime_type="image/png",
            size=100,
            ref={"$link": link},
        )

    @patch("linkedin_sync.bluesky_client.Client")
    def test_create_post_with_multiple_images(
        self, mock_client_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/xyz"
        )
        blob_ref = self._make_blob_ref()
        mock_client.upload_blob.return_value = MagicMock(blob=blob_ref)
        mock_client_cls.return_value = mock_client

        img1 = tmp_path / "one.png"
        img2 = tmp_path / "two.jpg"
        img1.write_bytes(b"fake-png")
        img2.write_bytes(b"fake-jpg")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_post(
            text="Two images",
            image_paths=[str(img1), str(img2)],
            image_alts=["First", "Second"],
        )

        # Should upload two blobs
        assert mock_client.upload_blob.call_count == 2

        # Embed should have two images
        call_kwargs = mock_client.send_post.call_args[1]
        embed = call_kwargs["embed"]
        assert len(embed.images) == 2
        assert embed.images[0].alt == "First"
        assert embed.images[1].alt == "Second"

    @patch("linkedin_sync.bluesky_client.Client")
    def test_thread_with_images_on_different_chunks(
        self, mock_client_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        resp1 = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/r1", cid="cid1"
        )
        resp2 = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/r2", cid="cid2"
        )
        mock_client.send_post.side_effect = [resp1, resp2]
        blob_ref = self._make_blob_ref()
        mock_client.upload_blob.return_value = MagicMock(blob=blob_ref)
        mock_client_cls.return_value = mock_client

        img1 = tmp_path / "one.png"
        img2 = tmp_path / "two.jpg"
        img1.write_bytes(b"fake1")
        img2.write_bytes(b"fake2")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_thread(
            ["Part 1", "Part 2"],
            images_by_chunk={
                0: [(str(img1), "First")],
                1: [(str(img2), "Second")],
            },
        )

        # Both chunks should have embeds
        calls = mock_client.send_post.call_args_list
        assert calls[0][1]["embed"] is not None
        assert calls[1][1]["embed"] is not None

    @patch("linkedin_sync.bluesky_client.Client")
    def test_thread_multiple_images_on_same_chunk(
        self, mock_client_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        resp = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/r1", cid="cid1"
        )
        mock_client.send_post.return_value = resp
        blob_ref = self._make_blob_ref()
        mock_client.upload_blob.return_value = MagicMock(blob=blob_ref)
        mock_client_cls.return_value = mock_client

        img1 = tmp_path / "one.png"
        img2 = tmp_path / "two.jpg"
        img1.write_bytes(b"fake1")
        img2.write_bytes(b"fake2")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_thread(
            ["Only chunk"],
            images_by_chunk={
                0: [(str(img1), "First"), (str(img2), "Second")],
            },
        )

        call_kwargs = mock_client.send_post.call_args[1]
        embed = call_kwargs["embed"]
        assert len(embed.images) == 2


# -------------------------------------------------------------------
# Mastodon multi-image
# -------------------------------------------------------------------
class TestMastodonMultiImage:
    """Test Mastodon client support for multiple images."""

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_create_post_with_multiple_images(
        self, mock_mastodon_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.media_post.side_effect = [
            {"id": "media-1"},
            {"id": "media-2"},
        ]
        mock_api.status_post.return_value = {
            "url": "https://mastodon.social/@test/123",
            "id": "123",
        }
        mock_mastodon_cls.return_value = mock_api

        img1 = tmp_path / "one.png"
        img2 = tmp_path / "two.jpg"
        img1.write_bytes(b"fake1")
        img2.write_bytes(b"fake2")

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        client.create_post(
            text="Two images",
            image_paths=[str(img1), str(img2)],
            image_alts=["First", "Second"],
        )

        assert mock_api.media_post.call_count == 2
        call_kwargs = mock_api.status_post.call_args[1]
        assert call_kwargs["media_ids"] == ["media-1", "media-2"]

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_thread_with_images_on_different_chunks(
        self, mock_mastodon_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.media_post.side_effect = [
            {"id": "media-1"},
            {"id": "media-2"},
        ]
        mock_api.status_post.side_effect = [
            {"url": "https://mastodon.social/@t/1", "id": "1"},
            {"url": "https://mastodon.social/@t/2", "id": "2"},
        ]
        mock_mastodon_cls.return_value = mock_api

        img1 = tmp_path / "one.png"
        img2 = tmp_path / "two.jpg"
        img1.write_bytes(b"fake1")
        img2.write_bytes(b"fake2")

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        client.create_thread(
            ["Part 1", "Part 2"],
            images_by_chunk={
                0: [(str(img1), "First")],
                1: [(str(img2), "Second")],
            },
        )

        # Both chunks should have media
        calls = mock_api.status_post.call_args_list
        assert calls[0][1]["media_ids"] == ["media-1"]
        assert calls[1][1]["media_ids"] == ["media-2"]


# -------------------------------------------------------------------
# Integration: single command with multiple images
# -------------------------------------------------------------------
class TestSingleCommandMultiImage:
    """Integration tests for the single command with multiple images."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @patch("linkedin_sync.sync._make_clients")
    def test_two_images_uploaded_to_all_platforms(
        self, mock_mc, runner, tmp_path
    ):
        img1 = tmp_path / "one.png"
        img2 = tmp_path / "two.jpg"
        img1.write_bytes(b"fake1")
        img2.write_bytes(b"fake2")

        li = MagicMock()
        li.upload_image.side_effect = [
            "urn:li:image:1",
            "urn:li:image:2",
        ]
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(cli, ["single", f"Two pics {img1} and {img2}"])
        assert result.exit_code == 0

        # LinkedIn should upload both images
        assert li.upload_image.call_count == 2
        li_kwargs = li.create_post.call_args.kwargs
        assert li_kwargs["image_urns"] == [
            "urn:li:image:1",
            "urn:li:image:2",
        ]
        # Image paths should NOT be in the text
        assert str(img1) not in li_kwargs["text"]
        assert str(img2) not in li_kwargs["text"]

        # Bluesky should get image_paths list
        bs_kwargs = bs.create_post.call_args.kwargs
        assert bs_kwargs["image_paths"] == [str(img1), str(img2)]

        # Mastodon should get image_paths list
        md_kwargs = md.create_post.call_args.kwargs
        assert md_kwargs["image_paths"] == [str(img1), str(img2)]

    @patch("linkedin_sync.sync._make_clients")
    def test_multiple_images_with_alt_text(self, mock_mc, runner, tmp_path):
        img1 = tmp_path / "cat.png"
        img2 = tmp_path / "dog.jpg"
        img1.write_bytes(b"fake1")
        img2.write_bytes(b"fake2")

        li = MagicMock()
        li.upload_image.side_effect = [
            "urn:li:image:1",
            "urn:li:image:2",
        ]
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        msg = f"Pets {img1} [A cat] and {img2} [A dog]"
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        # Alt texts passed to LinkedIn
        li_kwargs = li.create_post.call_args.kwargs
        assert li_kwargs["image_alt_texts"] == ["A cat", "A dog"]

        # Alt texts passed to Bluesky
        bs_kwargs = bs.create_post.call_args.kwargs
        assert bs_kwargs["image_alts"] == ["A cat", "A dog"]

        # Alt texts passed to Mastodon
        md_kwargs = md.create_post.call_args.kwargs
        assert md_kwargs["image_alts"] == ["A cat", "A dog"]

    @patch("linkedin_sync.sync._make_clients")
    def test_video_takes_precedence_over_images(
        self, mock_mc, runner, tmp_path
    ):
        """When a video and images are mixed, video wins."""
        img = tmp_path / "photo.png"
        vid = tmp_path / "clip.mp4"
        img.write_bytes(b"fake-img")
        vid.write_bytes(b"fake-vid")

        li = MagicMock()
        li.upload_video.return_value = "urn:li:video:1"
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(cli, ["single", f"Mixed {img} and {vid}"])
        assert result.exit_code == 0

        # LinkedIn should upload video, not images
        li.upload_video.assert_called_once()
        li.upload_image.assert_not_called()

    @patch("linkedin_sync.sync._make_clients")
    def test_multiple_images_in_threaded_bluesky(
        self, mock_mc, runner, tmp_path
    ):
        """Images distributed across thread chunks on Bluesky."""
        img1 = tmp_path / "first.png"
        img2 = tmp_path / "second.jpg"
        img1.write_bytes(b"fake1")
        img2.write_bytes(b"fake2")

        li = MagicMock()
        li.upload_image.side_effect = [
            "urn:li:image:1",
            "urn:li:image:2",
        ]
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_thread.return_value = "https://bsky.app/post/thread"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        # First image near start, second near end (>300 chars for BS)
        prefix = "word " * 5  # 25 chars
        middle = "word " * 60  # 300 chars
        msg = f"{prefix}{img1} {middle}{img2}"
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        bs_kwargs = bs.create_thread.call_args.kwargs
        assert "images_by_chunk" in bs_kwargs
        # Should have images distributed across chunks
        ibc = bs_kwargs["images_by_chunk"]
        assert len(ibc) >= 1
        # Total images across all chunks should be 2
        total = sum(len(v) for v in ibc.values())
        assert total == 2

    @patch("linkedin_sync.sync._make_clients")
    def test_single_image_still_works(self, mock_mc, runner, tmp_path):
        """Backward compat: single image still works fine."""
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake")

        li = MagicMock()
        li.upload_image.return_value = "urn:li:image:1"
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(cli, ["single", f"One pic {img}"])
        assert result.exit_code == 0
        li.upload_image.assert_called_once()

    @patch("linkedin_sync.sync._make_clients")
    def test_dry_run_shows_multiple_images(self, mock_mc, runner, tmp_path):
        img1 = tmp_path / "one.png"
        img2 = tmp_path / "two.jpg"
        img1.write_bytes(b"fake1")
        img2.write_bytes(b"fake2")
        mock_mc.return_value = (MagicMock(), MagicMock(), MagicMock())

        result = runner.invoke(
            cli,
            ["--dry-run", "single", f"Test {img1} and {img2}"],
        )
        assert result.exit_code == 0
        li, _bs, _md = mock_mc.return_value
        li.create_post.assert_not_called()
