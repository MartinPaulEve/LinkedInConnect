"""Tests for video upload support in the single command."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from linkedin_sync.sync import _extract_local_media, cli
from linkedin_sync.video import (
    MediaType,
    classify_media,
    needs_transcode,
    transcode_video,
)


# ---------------------------------------------------------------------------
# classify_media
# ---------------------------------------------------------------------------
class TestClassifyMedia:
    """Test media type classification by file extension."""

    @pytest.mark.parametrize("ext", ["png", "jpg", "jpeg", "gif", "webp"])
    def test_image_extensions(self, ext):
        assert classify_media(f"/tmp/file.{ext}") == MediaType.IMAGE

    @pytest.mark.parametrize(
        "ext", ["mp4", "mov", "mkv", "avi", "webm", "m4v"]
    )
    def test_video_extensions(self, ext):
        assert classify_media(f"/tmp/file.{ext}") == MediaType.VIDEO

    def test_case_insensitive(self):
        assert classify_media("/tmp/file.MP4") == MediaType.VIDEO
        assert classify_media("/tmp/file.PNG") == MediaType.IMAGE

    def test_unknown_extension(self):
        assert classify_media("/tmp/file.txt") is None
        assert classify_media("/tmp/file.pdf") is None


# ---------------------------------------------------------------------------
# needs_transcode
# ---------------------------------------------------------------------------
class TestNeedsTranscode:
    """Test whether a video needs transcoding for platform upload."""

    def test_mp4_does_not_need_transcode(self):
        assert needs_transcode("/tmp/clip.mp4") is False

    def test_m4v_does_not_need_transcode(self):
        assert needs_transcode("/tmp/clip.m4v") is False

    def test_mov_needs_transcode(self):
        assert needs_transcode("/tmp/clip.mov") is True

    def test_mkv_needs_transcode(self):
        assert needs_transcode("/tmp/clip.mkv") is True

    def test_avi_needs_transcode(self):
        assert needs_transcode("/tmp/clip.avi") is True

    def test_webm_needs_transcode(self):
        assert needs_transcode("/tmp/clip.webm") is True


# ---------------------------------------------------------------------------
# transcode_video
# ---------------------------------------------------------------------------
class TestTranscodeVideo:
    """Test ffmpeg transcoding to MP4/H.264."""

    @patch("linkedin_sync.video.subprocess.run")
    def test_transcode_creates_mp4(self, mock_run, tmp_path):
        src = tmp_path / "clip.mkv"
        src.write_bytes(b"fake-mkv")
        mock_run.return_value = MagicMock(returncode=0)

        result = transcode_video(str(src))
        assert result.endswith(".mp4")
        assert result != str(src)

        # Check ffmpeg was called with correct args
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "ffmpeg"
        assert "-i" in args
        assert str(src) in args

    @patch("linkedin_sync.video.subprocess.run")
    def test_transcode_failure_raises(self, mock_run, tmp_path):
        src = tmp_path / "clip.avi"
        src.write_bytes(b"fake-avi")
        mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg")

        with pytest.raises(RuntimeError, match="transcode"):
            transcode_video(str(src))

    def test_mp4_returns_same_path(self, tmp_path):
        src = tmp_path / "clip.mp4"
        src.write_bytes(b"fake-mp4")

        result = transcode_video(str(src))
        assert result == str(src)


# ---------------------------------------------------------------------------
# _extract_local_media (generalized from _extract_local_image)
# ---------------------------------------------------------------------------
class TestExtractLocalMedia:
    """Test extraction of both image and video paths from messages."""

    def test_no_media(self):
        clean, path, alt = _extract_local_media("Just text")
        assert clean == "Just text"
        assert path is None
        assert alt is None

    def test_image_still_works(self, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake")
        msg = f"Check {img} out"
        clean, path, _alt = _extract_local_media(msg)
        assert path == str(img)
        assert str(img) not in clean

    def test_video_extracted(self, tmp_path):
        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4")
        msg = f"Watch {vid} now"
        clean, path, _alt = _extract_local_media(msg)
        assert path == str(vid)
        assert str(vid) not in clean
        assert clean == "Watch now"

    def test_video_with_alt_text(self, tmp_path):
        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4")
        msg = f"Post {vid} [A funny cat video]"
        clean, path, alt = _extract_local_media(msg)
        assert path == str(vid)
        assert alt == "A funny cat video"
        assert "[A funny cat video]" not in clean
        assert clean == "Post"

    def test_mov_video(self, tmp_path):
        vid = tmp_path / "recording.mov"
        vid.write_bytes(b"fake-mov")
        msg = f"See {vid} here"
        clean, path, _alt = _extract_local_media(msg)
        assert path == str(vid)
        assert clean == "See here"

    def test_mkv_video(self, tmp_path):
        vid = tmp_path / "demo.mkv"
        vid.write_bytes(b"fake-mkv")
        msg = f"Demo {vid}"
        _clean, path, _alt = _extract_local_media(msg)
        assert path == str(vid)

    def test_webm_video(self, tmp_path):
        vid = tmp_path / "screen.webm"
        vid.write_bytes(b"fake-webm")
        msg = f"Here {vid}"
        _clean, path, _alt = _extract_local_media(msg)
        assert path == str(vid)

    def test_avi_video(self, tmp_path):
        vid = tmp_path / "old.avi"
        vid.write_bytes(b"fake-avi")
        msg = f"Watch {vid}"
        _clean, path, _alt = _extract_local_media(msg)
        assert path == str(vid)

    def test_nonexistent_video_ignored(self):
        msg = "See /nonexistent/clip.mp4 here"
        clean, path, _alt = _extract_local_media(msg)
        assert path is None
        assert clean == msg

    def test_url_with_video_not_matched(self):
        msg = "See https://example.com/clip.mp4 here"
        clean, path, _alt = _extract_local_media(msg)
        assert path is None
        assert clean == msg


# ---------------------------------------------------------------------------
# Integration: single command with video
# ---------------------------------------------------------------------------
class TestSingleCommandWithVideo:
    """Integration tests for the single command with video uploads."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @patch("linkedin_sync.sync.transcode_video")
    @patch("linkedin_sync.sync._make_clients")
    def test_video_uploaded_to_linkedin(
        self, mock_mc, mock_transcode, runner, tmp_path
    ):
        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4")
        mock_transcode.return_value = str(vid)

        li = MagicMock()
        li.upload_video.return_value = "urn:li:video:123"
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli, ["single", f"Watch this {vid}"]
        )
        assert result.exit_code == 0

        li.upload_video.assert_called_once_with(video_path=str(vid))
        li_kwargs = li.create_post.call_args.kwargs
        assert li_kwargs["video_urn"] == "urn:li:video:123"
        assert str(vid) not in li_kwargs["text"]

    @patch("linkedin_sync.sync.transcode_video")
    @patch("linkedin_sync.sync._make_clients")
    def test_video_uploaded_to_bluesky(
        self, mock_mc, mock_transcode, runner, tmp_path
    ):
        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4")
        mock_transcode.return_value = str(vid)

        li = MagicMock()
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli, ["single", f"Watch {vid}"]
        )
        assert result.exit_code == 0

        bs_kwargs = bs.create_post.call_args.kwargs
        assert bs_kwargs["video_path"] == str(vid)
        assert str(vid) not in bs_kwargs["text"]

    @patch("linkedin_sync.sync.transcode_video")
    @patch("linkedin_sync.sync._make_clients")
    def test_video_uploaded_to_mastodon(
        self, mock_mc, mock_transcode, runner, tmp_path
    ):
        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4")
        mock_transcode.return_value = str(vid)

        li = MagicMock()
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli, ["single", f"Watch {vid}"]
        )
        assert result.exit_code == 0

        md_kwargs = md.create_post.call_args.kwargs
        assert md_kwargs["video_path"] == str(vid)

    @patch("linkedin_sync.sync.transcode_video")
    @patch("linkedin_sync.sync._make_clients")
    def test_video_alt_text_passed(
        self, mock_mc, mock_transcode, runner, tmp_path
    ):
        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4")
        mock_transcode.return_value = str(vid)

        li = MagicMock()
        li.upload_video.return_value = "urn:li:video:123"
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        msg = f"Watch {vid} [A cat dancing]"
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        # Alt text stripped from posted text
        li_kwargs = li.create_post.call_args.kwargs
        assert "[A cat dancing]" not in li_kwargs["text"]

        # Alt text passed to all platforms
        bs_kwargs = bs.create_post.call_args.kwargs
        assert bs_kwargs["video_alt"] == "A cat dancing"
        md_kwargs = md.create_post.call_args.kwargs
        assert md_kwargs["video_alt"] == "A cat dancing"

    @patch("linkedin_sync.sync.transcode_video")
    @patch("linkedin_sync.sync._make_clients")
    def test_video_transcode_called_for_mkv(
        self, mock_mc, mock_transcode, runner, tmp_path
    ):
        vid = tmp_path / "clip.mkv"
        vid.write_bytes(b"fake-mkv")
        transcoded = tmp_path / "clip.mp4"
        transcoded.write_bytes(b"fake-mp4")
        mock_transcode.return_value = str(transcoded)

        li = MagicMock()
        li.upload_video.return_value = "urn:li:video:123"
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli, ["single", f"Watch {vid}"]
        )
        assert result.exit_code == 0
        mock_transcode.assert_called_once_with(str(vid))

    @patch("linkedin_sync.sync.transcode_video")
    @patch("linkedin_sync.sync._make_clients")
    def test_video_in_thread_bluesky(
        self, mock_mc, mock_transcode, runner, tmp_path
    ):
        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4")
        mock_transcode.return_value = str(vid)

        li = MagicMock()
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_thread.return_value = "https://bsky.app/post/t"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        prefix = "word " * 80
        msg = f"{prefix}{vid} [Demo video]"
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        bs_kwargs = bs.create_thread.call_args.kwargs
        assert bs_kwargs["video_path"] == str(vid)
        assert bs_kwargs["video_alt"] == "Demo video"

    @patch("linkedin_sync.sync.transcode_video")
    @patch("linkedin_sync.sync._make_clients")
    def test_linkedin_video_upload_failure_still_posts(
        self, mock_mc, mock_transcode, runner, tmp_path
    ):
        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4")
        mock_transcode.return_value = str(vid)

        li = MagicMock()
        li.upload_video.side_effect = RuntimeError("Upload failed")
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli, ["single", f"Watch {vid}"]
        )
        assert result.exit_code == 0
        li.create_post.assert_called_once()


# ---------------------------------------------------------------------------
# Bluesky video embed
# ---------------------------------------------------------------------------
class TestBlueskyVideoUpload:
    """Tests for Bluesky video upload and embed in posts."""

    @staticmethod
    def _make_blob_ref():
        from atproto_client.models.blob_ref import BlobRef

        link = (
            "bafkreibme22gw2h7y2h7tg2fhqotaq"
            "jucnbc24deqo72b6mkl2egezxhvy"
        )
        return BlobRef(
            mime_type="video/mp4",
            size=1000,
            ref={"$link": link},
        )

    @patch("linkedin_sync.bluesky_client.Client")
    def test_create_post_with_video(
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

        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4-bytes")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        url = client.create_post(
            text="Watch this", video_path=str(vid)
        )

        assert "bsky.app" in url
        mock_client.upload_blob.assert_called_once()
        call_kwargs = mock_client.send_post.call_args[1]
        embed = call_kwargs["embed"]
        assert embed is not None
        assert embed.video == blob_ref

    @patch("linkedin_sync.bluesky_client.Client")
    def test_video_alt_text_set(
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

        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_post(
            text="Watch", video_path=str(vid), video_alt="A cat"
        )

        call_kwargs = mock_client.send_post.call_args[1]
        embed = call_kwargs["embed"]
        assert embed.alt == "A cat"

    @patch("linkedin_sync.bluesky_client.Client")
    def test_video_takes_precedence_over_link(
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

        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_post(
            text="Watch",
            video_path=str(vid),
            link_url="https://example.com",
        )

        call_kwargs = mock_client.send_post.call_args[1]
        embed = call_kwargs["embed"]
        # Should be a video embed, not a link embed
        assert embed.video == blob_ref

    @patch("linkedin_sync.bluesky_client.Client")
    def test_thread_with_video_on_chunk(
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

        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_thread(
            ["Part 1 🧵1/2", "Part 2 🧵2/2"],
            video_path=str(vid),
            video_chunk_index=1,
        )

        first_call = mock_client.send_post.call_args_list[0]
        assert first_call[1].get("embed") is None

        second_call = mock_client.send_post.call_args_list[1]
        assert second_call[1]["embed"] is not None
        assert second_call[1]["embed"].video == blob_ref


# ---------------------------------------------------------------------------
# Mastodon video upload
# ---------------------------------------------------------------------------
class TestMastodonVideoUpload:
    """Tests for Mastodon video upload in posts."""

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_create_post_with_video(
        self, mock_mastodon_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv(
            "MASTODON_INSTANCE_URL", "https://mastodon.social"
        )
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.media_post.return_value = {"id": "media-v1"}
        mock_api.status_post.return_value = {
            "url": "https://mastodon.social/@test/123",
            "id": "123",
        }
        mock_mastodon_cls.return_value = mock_api

        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4")

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        url = client.create_post(
            text="Watch this", video_path=str(vid)
        )

        assert url == "https://mastodon.social/@test/123"
        mock_api.media_post.assert_called_once_with(str(vid))

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_video_with_alt_text(
        self, mock_mastodon_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv(
            "MASTODON_INSTANCE_URL", "https://mastodon.social"
        )
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.media_post.return_value = {"id": "media-v2"}
        mock_api.status_post.return_value = {
            "url": "https://mastodon.social/@test/456",
            "id": "456",
        }
        mock_mastodon_cls.return_value = mock_api

        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4")

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        client.create_post(
            text="Watch",
            video_path=str(vid),
            video_alt="A dancing cat",
        )

        mock_api.media_post.assert_called_once_with(
            str(vid), description="A dancing cat"
        )

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_thread_with_video_on_chunk(
        self, mock_mastodon_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv(
            "MASTODON_INSTANCE_URL", "https://mastodon.social"
        )
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.media_post.return_value = {"id": "media-v3"}
        mock_api.status_post.side_effect = [
            {"url": "https://mastodon.social/@t/1", "id": "1"},
            {"url": "https://mastodon.social/@t/2", "id": "2"},
        ]
        mock_mastodon_cls.return_value = mock_api

        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"fake-mp4")

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        client.create_thread(
            ["Part 1 🧵1/2", "Part 2 🧵2/2"],
            video_path=str(vid),
            video_chunk_index=1,
        )

        mock_api.media_post.assert_called_once()

        first_call = mock_api.status_post.call_args_list[0]
        assert first_call[1].get("media_ids") is None

        second_call = mock_api.status_post.call_args_list[1]
        assert second_call[1]["media_ids"] == ["media-v3"]


# ---------------------------------------------------------------------------
# LinkedIn video upload
# ---------------------------------------------------------------------------
class TestLinkedInVideoUpload:
    """Tests for LinkedIn video upload."""

    @patch("linkedin_sync.linkedin_client.requests.put")
    @patch(
        "linkedin_sync.linkedin_client.LinkedInClient._resolve_person_urn"
    )
    def test_upload_video(
        self, mock_resolve, mock_put, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "test-token")
        mock_resolve.return_value = "urn:li:person:abc"

        from linkedin_sync.linkedin_client import LinkedInClient

        client = LinkedInClient()

        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"a" * 100)

        # Mock the init upload response
        init_resp = MagicMock()
        init_resp.ok = True
        init_resp.json.return_value = {
            "value": {
                "video": "urn:li:video:v123",
                "uploadInstructions": [
                    {"uploadUrl": "https://upload.example.com/part1"}
                ],
            }
        }

        # Mock the finalize response
        finalize_resp = MagicMock()
        finalize_resp.ok = True

        client._session = MagicMock()
        client._session.post.side_effect = [init_resp, finalize_resp]

        mock_put.return_value = MagicMock(status_code=200)
        mock_put.return_value.raise_for_status = MagicMock()

        urn = client.upload_video(video_path=str(vid))

        assert urn == "urn:li:video:v123"
        # Init upload was called
        init_call = client._session.post.call_args_list[0]
        assert "videos" in init_call[0][0]

    @patch(
        "linkedin_sync.linkedin_client.LinkedInClient._resolve_person_urn"
    )
    def test_upload_video_nonexistent_raises(
        self, mock_resolve, monkeypatch
    ):
        monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "test-token")
        mock_resolve.return_value = "urn:li:person:abc"

        from linkedin_sync.linkedin_client import LinkedInClient

        client = LinkedInClient()

        with pytest.raises(FileNotFoundError):
            client.upload_video(video_path="/nonexistent/clip.mp4")

    @patch(
        "linkedin_sync.linkedin_client.LinkedInClient._resolve_person_urn"
    )
    def test_create_post_with_video_urn(
        self, mock_resolve, monkeypatch
    ):
        monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "test-token")
        mock_resolve.return_value = "urn:li:person:abc"

        from linkedin_sync.linkedin_client import LinkedInClient

        client = LinkedInClient()

        resp = MagicMock()
        resp.ok = True
        resp.headers = {"x-restli-id": "urn:li:share:789"}
        client._session = MagicMock()
        client._session.post.return_value = resp

        urn = client.create_post(
            text="Watch this",
            video_urn="urn:li:video:v123",
        )

        assert urn == "urn:li:share:789"
        body = client._session.post.call_args[1]["json"]
        assert body["content"]["media"]["id"] == "urn:li:video:v123"
