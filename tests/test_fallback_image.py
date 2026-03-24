"""Tests for the prepare_fallback_image function."""

from pathlib import Path

from PIL import Image

from linkedin_sync.image_checker import prepare_fallback_image


class TestPrepareFallbackImage:
    """Test OG fallback image preparation."""

    def _make_image(self, tmp_path, w, h, fmt="JPEG"):
        img = Image.new("RGB", (w, h), color="red")
        ext = ".jpg" if fmt == "JPEG" else ".png"
        path = tmp_path / f"test{ext}"
        img.save(str(path), format=fmt)
        return path

    def test_large_image_is_resized(self, tmp_path):
        src = self._make_image(tmp_path, 3000, 2000)
        result = prepare_fallback_image(str(src))
        assert result is not None
        img = Image.open(result)
        w, h = img.size
        assert w <= 1200
        assert h <= 630

    def test_small_image_kept_as_is(self, tmp_path):
        src = self._make_image(tmp_path, 800, 400)
        result = prepare_fallback_image(str(src))
        assert result is not None
        img = Image.open(result)
        assert img.size == (800, 400)

    def test_returns_temp_file_not_original(self, tmp_path):
        src = self._make_image(tmp_path, 1200, 630)
        result = prepare_fallback_image(str(src))
        assert result != str(src)
        assert Path(result).exists()

    def test_nonexistent_file_returns_none(self):
        result = prepare_fallback_image("/nonexistent/img.jpg")
        assert result is None

    def test_none_input_returns_none(self):
        result = prepare_fallback_image(None)
        assert result is None

    def test_png_image_works(self, tmp_path):
        src = self._make_image(tmp_path, 2000, 1500, fmt="PNG")
        result = prepare_fallback_image(str(src))
        assert result is not None
        img = Image.open(result)
        w, h = img.size
        assert w <= 1200
        assert h <= 630
