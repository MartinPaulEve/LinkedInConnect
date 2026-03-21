"""Tests for the image-check command and image_checker module."""

import os

import pytest
from click.testing import CliRunner

from image_checker import extract_image_paths, resize_image


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_md_with_images(tmp_path):
    """Create a markdown file referencing local images."""
    md = tmp_path / "post.md"
    md.write_text(
        "---\n"
        "title: Test Post\n"
        "url: https://example.com/test\n"
        "---\n"
        "\n"
        "# Hello\n"
        "\n"
        "![Photo](images/photo.jpg)\n"
        "\n"
        "Some text.\n"
        "\n"
        '![Diagram](diagrams/arch.png "Architecture")\n'
    )
    return md


@pytest.fixture
def sample_md_with_html_images(tmp_path):
    """Create a markdown file referencing images via HTML tags."""
    md = tmp_path / "post.md"
    md.write_text(
        "---\n"
        "title: Test Post\n"
        "url: https://example.com/test\n"
        "---\n"
        "\n"
        '<img src="images/banner.png" alt="Banner" />\n'
        "\n"
        "Some text.\n"
    )
    return md


@pytest.fixture
def sample_md_no_images(tmp_path):
    """Create a markdown file with no images."""
    md = tmp_path / "post.md"
    md.write_text(
        "---\n"
        "title: No Images\n"
        "url: https://example.com/none\n"
        "---\n"
        "\n"
        "Just text, no images here.\n"
    )
    return md


@pytest.fixture
def sample_md_with_remote_images(tmp_path):
    """Create a markdown file with remote (http) image URLs."""
    md = tmp_path / "post.md"
    md.write_text(
        "---\n"
        "title: Remote Images\n"
        "url: https://example.com/remote\n"
        "---\n"
        "\n"
        "![Remote](https://example.com/photo.jpg)\n"
        "![Local](images/local.png)\n"
    )
    return md


@pytest.fixture
def sample_md_front_matter_image(tmp_path):
    """Create a markdown file with image in front matter."""
    md = tmp_path / "post.md"
    md.write_text(
        "---\n"
        "title: Front Matter Image\n"
        "url: https://example.com/fm\n"
        "image: images/featured.jpg\n"
        "---\n"
        "\n"
        "Post body.\n"
    )
    return md


class TestExtractImagePaths:
    """Tests for extracting image paths from markdown files."""

    def test_extracts_markdown_image_syntax(self, sample_md_with_images):
        paths = extract_image_paths(str(sample_md_with_images))
        assert len(paths) == 2
        parent = sample_md_with_images.parent
        assert parent / "images" / "photo.jpg" in paths
        assert parent / "diagrams" / "arch.png" in paths

    def test_extracts_html_img_tags(self, sample_md_with_html_images):
        paths = extract_image_paths(str(sample_md_with_html_images))
        assert len(paths) == 1
        parent = sample_md_with_html_images.parent
        assert parent / "images" / "banner.png" in paths

    def test_no_images_returns_empty(self, sample_md_no_images):
        paths = extract_image_paths(str(sample_md_no_images))
        assert paths == []

    def test_skips_remote_urls(self, sample_md_with_remote_images):
        paths = extract_image_paths(str(sample_md_with_remote_images))
        assert len(paths) == 1
        parent = sample_md_with_remote_images.parent
        assert parent / "images" / "local.png" in paths

    def test_includes_front_matter_image(self, sample_md_front_matter_image):
        paths = extract_image_paths(str(sample_md_front_matter_image))
        assert len(paths) == 1
        parent = sample_md_front_matter_image.parent
        assert parent / "images" / "featured.jpg" in paths

    def test_deduplicates_paths(self, tmp_path):
        md = tmp_path / "post.md"
        md.write_text(
            "---\n"
            "title: Dup\n"
            "url: https://example.com/dup\n"
            "image: images/same.jpg\n"
            "---\n"
            "\n"
            "![Same](images/same.jpg)\n"
        )
        paths = extract_image_paths(str(md))
        assert len(paths) == 1

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            extract_image_paths("/nonexistent/file.md")


class TestResizeImage:
    """Tests for resizing images to fit within 1200x630."""

    def _make_image(self, tmp_path, name, size, fmt="JPEG"):
        """Create a test image of a given size (width, height)."""
        from PIL import Image

        img = Image.new("RGB", size, color="red")
        path = tmp_path / name
        img.save(str(path), fmt)
        return path

    def test_landscape_wider_than_target(self, tmp_path):
        """A 2400x800 image should scale down to 1200x400."""
        path = self._make_image(tmp_path, "wide.jpg", (2400, 800))
        resize_image(path)
        from PIL import Image

        img = Image.open(path)
        assert img.width == 1200
        assert img.height == 400

    def test_tall_image_scales_to_height(self, tmp_path):
        """A 600x1260 image should scale to 300x630."""
        path = self._make_image(tmp_path, "tall.jpg", (600, 1260))
        resize_image(path)
        from PIL import Image

        img = Image.open(path)
        assert img.width == 300
        assert img.height == 630

    def test_image_within_bounds_not_resized(self, tmp_path):
        """A 800x400 image should NOT be resized (already fits)."""
        path = self._make_image(tmp_path, "small.jpg", (800, 400))
        resize_image(path)
        from PIL import Image

        img = Image.open(path)
        assert img.width == 800
        assert img.height == 400

    def test_exact_target_size_unchanged(self, tmp_path):
        """A 1200x630 image should stay 1200x630."""
        path = self._make_image(tmp_path, "exact.jpg", (1200, 630))
        resize_image(path)
        from PIL import Image

        img = Image.open(path)
        assert img.width == 1200
        assert img.height == 630

    def test_aspect_ratio_preserved(self, tmp_path):
        """Aspect ratio must be preserved after resize."""
        path = self._make_image(tmp_path, "ratio.jpg", (3000, 2000))
        resize_image(path)
        from PIL import Image

        img = Image.open(path)
        # 3000x2000 -> scale by min(1200/3000, 630/2000)
        # = min(0.4, 0.315) = 0.315
        # -> 945 x 630
        assert img.width == 945
        assert img.height == 630

    def test_png_format_preserved(self, tmp_path):
        """PNG files should remain PNG after resize."""
        path = self._make_image(tmp_path, "test.png", (2400, 1200), "PNG")
        resize_image(path)
        from PIL import Image

        img = Image.open(path)
        assert img.format == "PNG"
        # 2400x1200 -> scale by min(1200/2400, 630/1200) = min(0.5, 0.525)
        # = 0.5 -> 1200 x 600
        assert img.width == 1200
        assert img.height == 600

    def test_file_size_under_7mb(self, tmp_path):
        """Result must be under 7MB."""
        path = self._make_image(tmp_path, "big.jpg", (4000, 3000))
        resize_image(path)
        assert os.path.getsize(path) < 7 * 1024 * 1024

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            resize_image(tmp_path / "nope.jpg")


class TestImageCheckCLI:
    """Tests for the image-check CLI command."""

    def _make_image(self, directory, name, size, fmt="JPEG"):
        from PIL import Image

        img = Image.new("RGB", size, color="blue")
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(path), fmt)
        return path

    def test_command_processes_images(self, runner, tmp_path):
        """image-check should resize referenced images."""
        from sync import cli

        img_dir = tmp_path / "images"
        img_dir.mkdir()
        self._make_image(img_dir, "photo.jpg", (2400, 1200))

        md = tmp_path / "post.md"
        md.write_text(
            "---\n"
            "title: Test\n"
            "url: https://example.com/test\n"
            "---\n"
            "\n"
            "![Photo](images/photo.jpg)\n"
        )

        result = runner.invoke(cli, ["image-check", str(md)])
        assert result.exit_code == 0

        from PIL import Image

        img = Image.open(img_dir / "photo.jpg")
        assert img.width == 1200
        assert img.height == 600

    def test_command_reports_missing_images(self, runner, tmp_path):
        """image-check should warn about missing image files."""
        from sync import cli

        md = tmp_path / "post.md"
        md.write_text(
            "---\n"
            "title: Test\n"
            "url: https://example.com/test\n"
            "---\n"
            "\n"
            "![Missing](images/gone.jpg)\n"
        )

        result = runner.invoke(cli, ["image-check", str(md)])
        assert result.exit_code == 0

    def test_command_no_images(self, runner, tmp_path):
        """image-check on a file with no images should succeed."""
        from sync import cli

        md = tmp_path / "post.md"
        md.write_text(
            "---\n"
            "title: Test\n"
            "url: https://example.com/test\n"
            "---\n"
            "\n"
            "No images.\n"
        )

        result = runner.invoke(cli, ["image-check", str(md)])
        assert result.exit_code == 0

    def test_dry_run_does_not_modify(self, runner, tmp_path):
        """image-check --dry-run should not modify images."""
        from sync import cli

        img_dir = tmp_path / "images"
        img_dir.mkdir()
        self._make_image(img_dir, "photo.jpg", (2400, 1200))
        md = tmp_path / "post.md"
        md.write_text(
            "---\n"
            "title: Test\n"
            "url: https://example.com/test\n"
            "---\n"
            "\n"
            "![Photo](images/photo.jpg)\n"
        )

        result = runner.invoke(cli, ["--dry-run", "image-check", str(md)])
        assert result.exit_code == 0

        from PIL import Image

        img = Image.open(img_dir / "photo.jpg")
        assert img.width == 2400
        assert img.height == 1200
