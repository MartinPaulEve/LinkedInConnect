"""Tests for Bluesky image auto-resize on upload."""

import io
import os
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from linkedin_sync.bluesky_client import (
    BLUESKY_MAX_IMAGE_SIZE,
    _resize_image_data,
)


def _make_large_png(width: int, height: int, mode: str = "RGB") -> bytes:
    """Create a large PNG with random noise that won't compress small."""
    channels = 4 if mode == "RGBA" else 3
    noise = os.urandom(width * height * channels)
    img = Image.frombytes(mode, (width, height), noise)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestResizeImageData:
    """Unit tests for in-memory image resizing."""

    def test_small_image_unchanged(self):
        """An image under the size limit should be returned as-is."""
        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        assert len(data) < BLUESKY_MAX_IMAGE_SIZE
        result = _resize_image_data(data)
        assert result == data

    def test_large_image_is_resized(self):
        """An image over the size limit should be downsized."""
        large_data = _make_large_png(4000, 3000)
        if len(large_data) <= BLUESKY_MAX_IMAGE_SIZE:
            pytest.skip("Test image not large enough to trigger resize")

        result = _resize_image_data(large_data)
        assert len(result) <= BLUESKY_MAX_IMAGE_SIZE

    def test_aspect_ratio_preserved(self):
        """Resized image should maintain the original aspect ratio."""
        large_data = _make_large_png(4000, 2000)
        if len(large_data) <= BLUESKY_MAX_IMAGE_SIZE:
            pytest.skip("Test image not large enough to trigger resize")

        result = _resize_image_data(large_data)
        resized_img = Image.open(io.BytesIO(result))
        w, h = resized_img.size
        ratio = w / h
        assert abs(ratio - 2.0) < 0.05

    def test_jpeg_output_format(self):
        """Large images should be output as JPEG for better compression."""
        large_data = _make_large_png(4000, 3000)
        if len(large_data) <= BLUESKY_MAX_IMAGE_SIZE:
            pytest.skip("Test image not large enough to trigger resize")

        result = _resize_image_data(large_data)
        assert len(result) <= BLUESKY_MAX_IMAGE_SIZE
        resized_img = Image.open(io.BytesIO(result))
        assert resized_img.size[0] > 0

    def test_rgba_converted_for_jpeg(self):
        """RGBA images should be converted to RGB for JPEG output."""
        large_data = _make_large_png(4000, 3000, mode="RGBA")
        if len(large_data) <= BLUESKY_MAX_IMAGE_SIZE:
            pytest.skip("Test image not large enough to trigger resize")

        result = _resize_image_data(large_data)
        assert len(result) <= BLUESKY_MAX_IMAGE_SIZE
        resized_img = Image.open(io.BytesIO(result))
        assert resized_img.mode in ("RGB", "L")


class TestBlueskyUploadAutoResize:
    """Integration test: _upload_image_file auto-resizes large images."""

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
    def test_large_image_resized_before_upload(
        self, mock_client_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        blob_ref = self._make_blob_ref()
        mock_client.upload_blob.return_value = MagicMock(blob=blob_ref)
        mock_client_cls.return_value = mock_client

        # Write a large noise image to disk
        large_data = _make_large_png(4000, 3000)
        if len(large_data) <= BLUESKY_MAX_IMAGE_SIZE:
            pytest.skip("Test image not large enough")

        img_path = tmp_path / "large.png"
        img_path.write_bytes(large_data)

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        result = client._upload_image_file(str(img_path))

        assert result is not None
        # The data passed to upload_blob should be under the limit
        uploaded_data = mock_client.upload_blob.call_args[0][0]
        assert len(uploaded_data) <= BLUESKY_MAX_IMAGE_SIZE

    @patch("linkedin_sync.bluesky_client.Client")
    def test_small_image_not_resized(
        self, mock_client_cls, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("BLUESKY_HANDLE", "test.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "test-pass")

        mock_client = MagicMock()
        blob_ref = self._make_blob_ref()
        mock_client.upload_blob.return_value = MagicMock(blob=blob_ref)
        mock_client_cls.return_value = mock_client

        # Create a small image
        img = Image.new("RGB", (100, 100), color="blue")
        img_path = tmp_path / "small.png"
        img.save(str(img_path), format="PNG")

        original_data = img_path.read_bytes()

        from linkedin_sync.bluesky_client import BlueskyClient

        client = BlueskyClient()
        client._upload_image_file(str(img_path))

        # The data should be the original bytes unchanged
        uploaded_data = mock_client.upload_blob.call_args[0][0]
        assert uploaded_data == original_data
