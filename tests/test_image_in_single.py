"""Tests for local image support in the single command."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from linkedin_sync.sync import (
    _extract_local_image,
    _image_chunk_index,
    cli,
)


class TestExtractLocalImage:
    """Test detection and extraction of local image paths from messages."""

    def test_no_image_returns_none(self):
        clean, path, _alt = _extract_local_image("Just a plain message")
        assert clean == "Just a plain message"
        assert path is None

    def test_absolute_path_png(self, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake-png")
        msg = f"Check this out {img} cool right"
        clean, path, _alt = _extract_local_image(msg)
        assert path == str(img)
        assert str(img) not in clean
        assert clean == "Check this out cool right"

    def test_absolute_path_jpg(self, tmp_path):
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"fake-jpg")
        msg = f"Look at {img}"
        clean, path, _alt = _extract_local_image(msg)
        assert path == str(img)
        assert str(img) not in clean
        assert clean == "Look at"

    def test_absolute_path_jpeg(self, tmp_path):
        img = tmp_path / "photo.jpeg"
        img.write_bytes(b"fake-jpeg")
        msg = f"{img} is great"
        clean, path, _alt = _extract_local_image(msg)
        assert path == str(img)
        assert clean == "is great"

    def test_tilde_path(self, tmp_path, monkeypatch):
        img = tmp_path / "image.png"
        img.write_bytes(b"fake")
        monkeypatch.setenv("HOME", str(tmp_path))
        msg = "Here is ~/image.png for you"
        clean, path, _alt = _extract_local_image(msg)
        assert path == str(img)
        assert "~/image.png" not in clean
        assert clean == "Here is for you"

    def test_relative_dot_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        img = tmp_path / "pic.gif"
        img.write_bytes(b"fake-gif")
        msg = "Look ./pic.gif nice"
        clean, path, _alt = _extract_local_image(msg)
        assert path == str(img)
        assert clean == "Look nice"

    def test_relative_dotdot_path(self, tmp_path, monkeypatch):
        sub = tmp_path / "subdir"
        sub.mkdir()
        monkeypatch.chdir(sub)
        img = tmp_path / "pic.webp"
        img.write_bytes(b"fake-webp")
        msg = "See ../pic.webp here"
        clean, path, _alt = _extract_local_image(msg)
        assert path == str(img)
        assert clean == "See here"

    def test_nonexistent_file_ignored(self):
        msg = "Look at /nonexistent/path/image.png nice"
        clean, path, _alt = _extract_local_image(msg)
        assert path is None
        assert clean == msg

    def test_url_not_matched(self):
        msg = "See https://example.com/image.png for details"
        clean, path, _alt = _extract_local_image(msg)
        assert path is None
        assert clean == msg

    def test_supported_extensions(self, tmp_path):
        for ext in ("png", "jpg", "jpeg", "gif", "webp"):
            img = tmp_path / f"test.{ext}"
            img.write_bytes(b"fake")
            msg = f"Image {img} here"
            _clean, path, _alt = _extract_local_image(msg)
            assert path == str(img), f"Failed for .{ext}"

    def test_cleans_double_spaces(self, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake")
        msg = f"Before {img} after"
        clean, _path, _alt = _extract_local_image(msg)
        assert "  " not in clean
        assert clean == "Before after"

    def test_image_at_start(self, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake")
        msg = f"{img} is the image"
        clean, _path, _alt = _extract_local_image(msg)
        assert clean == "is the image"

    def test_image_at_end(self, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake")
        msg = f"Look at this {img}"
        clean, _path, _alt = _extract_local_image(msg)
        assert clean == "Look at this"

    def test_returns_char_position_for_chunk_mapping(
        self, tmp_path
    ):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake")
        # Image appears later in the message
        prefix = "A" * 200 + " "
        msg = f"{prefix}{img} end"
        _clean, path, _alt = _extract_local_image(msg)
        assert path == str(img)

    def test_alt_text_extracted(self, tmp_path):
        img = tmp_path / "bear.jpeg"
        img.write_bytes(b"fake")
        msg = f"A post. {img} [An image of a bear]"
        clean, path, alt = _extract_local_image(msg)
        assert path == str(img)
        assert alt == "An image of a bear"
        assert "[An image of a bear]" not in clean
        assert str(img) not in clean
        assert clean == "A post."

    def test_alt_text_with_space_before_bracket(self, tmp_path):
        img = tmp_path / "cat.png"
        img.write_bytes(b"fake")
        msg = f"Look {img} [A fluffy cat] nice"
        clean, _path, alt = _extract_local_image(msg)
        assert alt == "A fluffy cat"
        assert clean == "Look nice"

    def test_no_alt_text_returns_none(self, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake")
        msg = f"Just {img} here"
        clean, path, alt = _extract_local_image(msg)
        assert path == str(img)
        assert alt is None
        assert clean == "Just here"

    def test_alt_text_empty_brackets(self, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake")
        msg = f"Post {img} [] more"
        clean, _path, alt = _extract_local_image(msg)
        assert alt is None
        assert clean == "Post more"

    def test_alt_text_not_immediately_after(self, tmp_path):
        """Brackets not right after image are not alt text."""
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake")
        msg = f"Post {img} some words [not alt]"
        clean, _path, alt = _extract_local_image(msg)
        assert alt is None
        assert "[not alt]" in clean

    def test_alt_text_at_end_of_message(self, tmp_path):
        img = tmp_path / "spencer.jpeg"
        img.write_bytes(b"fake")
        msg = f"A post. {img} [An image of a bear]"
        clean, _path, alt = _extract_local_image(msg)
        assert alt == "An image of a bear"
        assert clean == "A post."


class TestImageChunkIndex:
    """Test mapping image position to thread chunk index."""

    def test_single_chunk_returns_zero(self):
        assert _image_chunk_index(0, 100, 1) == 0

    def test_image_at_start_returns_zero(self):
        assert _image_chunk_index(0, 600, 3) == 0

    def test_image_at_end_returns_last(self):
        assert _image_chunk_index(550, 600, 3) == 2

    def test_image_in_middle(self):
        # 300 chars into a 600-char message split into 3 chunks
        assert _image_chunk_index(300, 600, 3) == 1

    def test_clamps_to_last_chunk(self):
        assert _image_chunk_index(600, 600, 3) == 2

    def test_zero_length_message(self):
        assert _image_chunk_index(0, 0, 1) == 0


class TestSingleCommandWithImage:
    """Integration tests for the single command with local images."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @patch("linkedin_sync.sync._make_clients")
    def test_image_uploaded_to_linkedin(self, mock_mc, runner, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake-png-data")

        li = MagicMock()
        li.upload_image.return_value = "urn:li:image:123"
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli, ["single", f"Check this out {img}"]
        )
        assert result.exit_code == 0

        # LinkedIn should upload image and create post with image_urn
        li.upload_image.assert_called_once_with(image_path=str(img))
        li_kwargs = li.create_post.call_args.kwargs
        assert li_kwargs["image_urn"] == "urn:li:image:123"
        # Image path should NOT be in the text
        assert str(img) not in li_kwargs["text"]

    @patch("linkedin_sync.sync._make_clients")
    def test_image_uploaded_to_bluesky(self, mock_mc, runner, tmp_path):
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"fake-jpg-data")

        li = MagicMock()
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli, ["single", f"Nice picture {img}"]
        )
        assert result.exit_code == 0

        bs_kwargs = bs.create_post.call_args.kwargs
        assert bs_kwargs["image_path"] == str(img)
        assert str(img) not in bs_kwargs["text"]

    @patch("linkedin_sync.sync._make_clients")
    def test_image_uploaded_to_mastodon(self, mock_mc, runner, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake-png-data")

        li = MagicMock()
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli, ["single", f"My photo {img}"]
        )
        assert result.exit_code == 0

        md_kwargs = md.create_post.call_args.kwargs
        assert md_kwargs["image_path"] == str(img)
        assert str(img) not in md_kwargs["text"]

    @patch("linkedin_sync.sync._make_clients")
    def test_no_image_no_upload(self, mock_mc, runner):
        li = MagicMock()
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(cli, ["single", "No image here"])
        assert result.exit_code == 0

        li.upload_image.assert_not_called()
        bs_kwargs = bs.create_post.call_args.kwargs
        assert bs_kwargs.get("image_path") is None
        md_kwargs = md.create_post.call_args.kwargs
        assert md_kwargs.get("image_path") is None

    @patch("linkedin_sync.sync._make_clients")
    def test_image_in_thread_placed_at_correct_chunk_bluesky(
        self, mock_mc, runner, tmp_path
    ):
        """Image after the split point should go on the second chunk."""
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake-png-data")

        li = MagicMock()
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_thread.return_value = "https://bsky.app/post/thread"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        # Build a 400-char message with image near the end
        prefix = "word " * 60  # 300 chars
        msg = f"{prefix}and here is {img} the end"
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        # Bluesky should thread with image on a later chunk (not 0)
        bs_kwargs = bs.create_thread.call_args.kwargs
        assert bs_kwargs["image_path"] == str(img)
        assert bs_kwargs["image_chunk_index"] > 0

    @patch("linkedin_sync.sync._make_clients")
    def test_image_in_thread_placed_at_correct_chunk_mastodon(
        self, mock_mc, runner, tmp_path
    ):
        """Image after split goes on later chunk for Mastodon."""
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake-png-data")

        li = MagicMock()
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_thread.return_value = "https://bsky.app/post/thread"
        md = MagicMock()
        md.create_thread.return_value = "https://mastodon.social/@u/thread"
        mock_mc.return_value = (li, bs, md)

        # Build a 600-char message with image near the end
        prefix = "word " * 100  # 500 chars
        msg = f"{prefix}here is the image {img} done"
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        md_kwargs = md.create_thread.call_args.kwargs
        assert md_kwargs["image_path"] == str(img)
        assert md_kwargs["image_chunk_index"] > 0

    @patch("linkedin_sync.sync._make_clients")
    def test_dry_run_shows_image_info(self, mock_mc, runner, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake-png-data")
        mock_mc.return_value = (MagicMock(), MagicMock(), MagicMock())

        result = runner.invoke(
            cli, ["--dry-run", "single", f"Test {img}"]
        )
        assert result.exit_code == 0

        li, _bs, _md = mock_mc.return_value
        li.create_post.assert_not_called()

    @patch("linkedin_sync.sync._make_clients")
    def test_image_with_url_both_work(self, mock_mc, runner, tmp_path):
        """An image path and a URL can coexist."""
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake-png-data")

        li = MagicMock()
        li.upload_image.return_value = "urn:li:image:123"
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli,
            ["single", f"See {img} and https://example.com"],
        )
        assert result.exit_code == 0

        # LinkedIn gets image (image takes precedence over article)
        li.upload_image.assert_called_once()
        li_kwargs = li.create_post.call_args.kwargs
        assert li_kwargs["image_urn"] == "urn:li:image:123"

    @patch("linkedin_sync.sync._make_clients")
    def test_alt_text_passed_to_all_platforms(
        self, mock_mc, runner, tmp_path
    ):
        img = tmp_path / "bear.jpeg"
        img.write_bytes(b"fake-jpeg-data")

        li = MagicMock()
        li.upload_image.return_value = "urn:li:image:123"
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        msg = f"A post. {img} [An image of a bear]"
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        # Alt text passed to LinkedIn
        li_kwargs = li.create_post.call_args.kwargs
        assert li_kwargs["image_alt_text"] == "An image of a bear"
        # Alt text in posted text
        assert "[An image of a bear]" not in li_kwargs["text"]
        assert str(img) not in li_kwargs["text"]

        # Alt text passed to Bluesky
        bs_kwargs = bs.create_post.call_args.kwargs
        assert bs_kwargs["image_alt"] == "An image of a bear"

        # Alt text passed to Mastodon
        md_kwargs = md.create_post.call_args.kwargs
        assert md_kwargs["image_alt"] == "An image of a bear"

    @patch("linkedin_sync.sync._make_clients")
    def test_no_alt_text_not_passed(
        self, mock_mc, runner, tmp_path
    ):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake-png-data")

        li = MagicMock()
        li.upload_image.return_value = "urn:li:image:123"
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli, ["single", f"No alt {img}"]
        )
        assert result.exit_code == 0

        li_kwargs = li.create_post.call_args.kwargs
        assert li_kwargs.get("image_alt_text") is None
        bs_kwargs = bs.create_post.call_args.kwargs
        assert bs_kwargs.get("image_alt") is None
        md_kwargs = md.create_post.call_args.kwargs
        assert md_kwargs.get("image_alt") is None

    @patch("linkedin_sync.sync._make_clients")
    def test_alt_text_in_thread(
        self, mock_mc, runner, tmp_path
    ):
        """Alt text should be passed through to threaded posts."""
        img = tmp_path / "bear.jpeg"
        img.write_bytes(b"fake")

        li = MagicMock()
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_thread.return_value = "https://bsky.app/post/t"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        prefix = "word " * 80  # 400 chars, threads on Bluesky
        msg = f"{prefix}{img} [A bear photo]"
        result = runner.invoke(cli, ["single", msg])
        assert result.exit_code == 0

        bs_kwargs = bs.create_thread.call_args.kwargs
        assert bs_kwargs["image_alt"] == "A bear photo"

    @patch("linkedin_sync.sync._make_clients")
    def test_linkedin_upload_failure_still_posts(
        self, mock_mc, runner, tmp_path
    ):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake-png-data")

        li = MagicMock()
        li.upload_image.side_effect = RuntimeError("Upload failed")
        li.create_post.return_value = "urn:li:share:456"
        bs = MagicMock()
        bs.create_post.return_value = "https://bsky.app/post/1"
        md = MagicMock()
        md.create_post.return_value = "https://mastodon.social/@u/1"
        mock_mc.return_value = (li, bs, md)

        result = runner.invoke(
            cli, ["single", f"Test {img}"]
        )
        assert result.exit_code == 0
        # Should still attempt to post (without image)
        li.create_post.assert_called_once()


class TestBlueskyImageUpload:
    """Tests for Bluesky image upload and embed in posts."""

    @staticmethod
    def _make_blob_ref():
        from atproto_client.models.blob_ref import BlobRef

        link = (
            "bafkreibme22gw2h7y2h7tg2fhqotaq"
            "jucnbc24deqo72b6mkl2egezxhvy"
        )
        return BlobRef(
            mime_type="image/png",
            size=100,
            ref={"$link": link},
        )

    @patch("linkedin_sync.bluesky_client.Client")
    def test_create_post_with_image(
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

        img = tmp_path / "test.png"
        img.write_bytes(b"fake-png-bytes")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        url = client.create_post(text="With image", image_path=str(img))

        assert "bsky.app" in url
        mock_client.upload_blob.assert_called_once_with(b"fake-png-bytes")
        call_kwargs = mock_client.send_post.call_args[1]
        embed = call_kwargs["embed"]
        assert embed is not None

    @patch("linkedin_sync.bluesky_client.Client")
    def test_thread_with_image_on_specific_chunk(
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

        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake-jpg")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_thread(
            ["Part 1 🧵1/2", "Part 2 🧵2/2"],
            image_path=str(img),
            image_chunk_index=1,  # Image on second chunk
        )

        # First post should NOT have image embed
        first_call = mock_client.send_post.call_args_list[0]
        assert first_call[1].get("embed") is None

        # Second post should have image embed
        second_call = mock_client.send_post.call_args_list[1]
        assert second_call[1]["embed"] is not None

    @patch("linkedin_sync.bluesky_client.Client")
    def test_thread_image_on_first_chunk(
        self, mock_client_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/r1", cid="cid1"
        )
        blob_ref = self._make_blob_ref()
        mock_client.upload_blob.return_value = MagicMock(blob=blob_ref)
        mock_client_cls.return_value = mock_client

        img = tmp_path / "test.png"
        img.write_bytes(b"fake")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_thread(
            ["Part 1 🧵1/2", "Part 2 🧵2/2"],
            image_path=str(img),
            image_chunk_index=0,
        )

        first_call = mock_client.send_post.call_args_list[0]
        assert first_call[1]["embed"] is not None

    @patch("linkedin_sync.bluesky_client.Client")
    def test_alt_text_set_on_image(
        self, mock_client_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/xyz"
        )
        blob_ref = self._make_blob_ref()
        mock_client.upload_blob.return_value = MagicMock(
            blob=blob_ref
        )
        mock_client_cls.return_value = mock_client

        img = tmp_path / "test.png"
        img.write_bytes(b"fake")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_post(
            text="With image",
            image_path=str(img),
            image_alt="A nice photo",
        )

        call_kwargs = mock_client.send_post.call_args[1]
        embed = call_kwargs["embed"]
        assert embed.images[0].alt == "A nice photo"

    @patch("linkedin_sync.bluesky_client.Client")
    def test_no_alt_text_uses_empty_string(
        self, mock_client_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        mock_client.send_post.return_value = MagicMock(
            uri="at://did:plc:abc/app.bsky.feed.post/xyz"
        )
        blob_ref = self._make_blob_ref()
        mock_client.upload_blob.return_value = MagicMock(
            blob=blob_ref
        )
        mock_client_cls.return_value = mock_client

        img = tmp_path / "test.png"
        img.write_bytes(b"fake")

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client.create_post(
            text="With image", image_path=str(img)
        )

        call_kwargs = mock_client.send_post.call_args[1]
        embed = call_kwargs["embed"]
        assert embed.images[0].alt == ""


class TestMastodonImageUpload:
    """Tests for Mastodon media upload in posts."""

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_create_post_with_image(
        self, mock_mastodon_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.media_post.return_value = {"id": "media-123"}
        mock_api.status_post.return_value = {
            "url": "https://mastodon.social/@test/123",
            "id": "123",
        }
        mock_mastodon_cls.return_value = mock_api

        img = tmp_path / "test.png"
        img.write_bytes(b"fake-png")

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        url = client.create_post(text="With image", image_path=str(img))

        assert url == "https://mastodon.social/@test/123"
        mock_api.media_post.assert_called_once_with(str(img))
        call_kwargs = mock_api.status_post.call_args
        assert call_kwargs[1]["media_ids"] == ["media-123"]

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_thread_with_image_on_specific_chunk(
        self, mock_mastodon_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.media_post.return_value = {"id": "media-456"}
        mock_api.status_post.side_effect = [
            {"url": "https://mastodon.social/@t/1", "id": "1"},
            {"url": "https://mastodon.social/@t/2", "id": "2"},
        ]
        mock_mastodon_cls.return_value = mock_api

        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake-jpg")

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        client.create_thread(
            ["Part 1 🧵1/2", "Part 2 🧵2/2"],
            image_path=str(img),
            image_chunk_index=1,
        )

        # Media should be uploaded once
        mock_api.media_post.assert_called_once()

        # First post should NOT have media_ids
        first_call = mock_api.status_post.call_args_list[0]
        assert first_call[1].get("media_ids") is None

        # Second post should have media_ids
        second_call = mock_api.status_post.call_args_list[1]
        assert second_call[1]["media_ids"] == ["media-456"]

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_alt_text_passed_to_media_post(
        self, mock_mastodon_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv(
            "MASTODON_INSTANCE_URL", "https://mastodon.social"
        )
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.media_post.return_value = {"id": "media-789"}
        mock_api.status_post.return_value = {
            "url": "https://mastodon.social/@test/123",
            "id": "123",
        }
        mock_mastodon_cls.return_value = mock_api

        img = tmp_path / "test.png"
        img.write_bytes(b"fake-png")

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        client.create_post(
            text="With image",
            image_path=str(img),
            image_alt="A bear",
        )

        mock_api.media_post.assert_called_once_with(
            str(img), description="A bear"
        )

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_no_alt_text_no_description(
        self, mock_mastodon_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv(
            "MASTODON_INSTANCE_URL", "https://mastodon.social"
        )
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test-token")

        mock_api = MagicMock()
        mock_api.media_post.return_value = {"id": "media-789"}
        mock_api.status_post.return_value = {
            "url": "https://mastodon.social/@test/123",
            "id": "123",
        }
        mock_mastodon_cls.return_value = mock_api

        img = tmp_path / "test.png"
        img.write_bytes(b"fake-png")

        from linkedin_sync.mastodon_client import MastodonClient

        client = MastodonClient()
        client.create_post(
            text="With image", image_path=str(img)
        )

        mock_api.media_post.assert_called_once_with(str(img))

    @patch("linkedin_sync.mastodon_client.Mastodon")
    def test_no_image_no_media_upload(
        self, mock_mastodon_cls, monkeypatch
    ):
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
        client.create_post(text="No image")

        mock_api.media_post.assert_not_called()
        call_kwargs = mock_api.status_post.call_args
        assert call_kwargs[1].get("media_ids") is None
