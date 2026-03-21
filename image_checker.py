"""Check and resize images referenced in markdown blog posts."""

import re
from pathlib import Path

import yaml
from PIL import Image

from logging_config import get_logger

log = get_logger(__name__)

MAX_WIDTH = 1200
MAX_HEIGHT = 630
MAX_FILE_SIZE = 7 * 1024 * 1024  # 7 MB


def extract_image_paths(file_path: str) -> list[Path]:
    """Extract local image paths from a markdown file.

    Finds images in:
    - Markdown syntax: ![alt](path)
    - HTML img tags: <img src="path" />
    - Front matter: image or featured_image fields

    Remote URLs (http/https) are skipped.
    Paths are resolved relative to the markdown file's directory.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Markdown file not found: {file_path}")

    text = path.read_text(encoding="utf-8")
    base_dir = path.parent
    seen: set[Path] = set()
    result: list[Path] = []

    # Extract front matter image fields
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if fm_match:
        try:
            front_matter = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError:
            front_matter = {}
        for key in ("image", "featured_image"):
            val = front_matter.get(key)
            if val and not _is_remote(val):
                resolved = (base_dir / val).resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    result.append(resolved)

    # Markdown image syntax: ![alt](path) or ![alt](path "title")
    for match in re.finditer(r'!\[[^\]]*\]\(([^)"\s]+)', text):
        src = match.group(1)
        if not _is_remote(src):
            resolved = (base_dir / src).resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(resolved)

    # HTML <img src="..."> tags
    for match in re.finditer(r'<img\s[^>]*src=["\']([^"\']+)["\']', text):
        src = match.group(1)
        if not _is_remote(src):
            resolved = (base_dir / src).resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(resolved)

    log.info(
        "images_extracted",
        file=file_path,
        count=len(result),
    )
    return result


def _is_remote(src: str) -> bool:
    """Check if a URL is remote (http/https)."""
    return src.startswith(("http://", "https://", "//"))


def resize_image(image_path: Path) -> None:
    """Resize an image to fit within 1200x630 preserving aspect ratio.

    The image is scaled down so that it fits entirely within the
    1200x630 bounding box. If the image already fits, it is not
    modified. The file is overwritten in place.
    """
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    img = Image.open(image_path)
    original_format = img.format
    orig_w, orig_h = img.size

    # Calculate scale factor to fit within bounding box
    scale_w = MAX_WIDTH / orig_w
    scale_h = MAX_HEIGHT / orig_h
    scale = min(scale_w, scale_h)

    if scale >= 1.0:
        log.info(
            "image_already_fits",
            path=str(image_path),
            size=f"{orig_w}x{orig_h}",
        )
        return

    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)

    log.info(
        "resizing_image",
        path=str(image_path),
        original=f"{orig_w}x{orig_h}",
        new=f"{new_w}x{new_h}",
        scale=f"{scale:.4f}",
    )

    resized = img.resize((new_w, new_h), Image.LANCZOS)

    save_kwargs: dict = {}
    fmt = (original_format or "JPEG").upper()
    if fmt == "JPEG":
        save_kwargs["quality"] = 85
        save_kwargs["optimize"] = True
    elif fmt == "PNG":
        save_kwargs["optimize"] = True

    resized.save(str(image_path), format=fmt, **save_kwargs)

    file_size = image_path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        log.warning(
            "image_still_large",
            path=str(image_path),
            size_mb=f"{file_size / (1024 * 1024):.1f}",
        )

    log.info(
        "image_resized",
        path=str(image_path),
        new_size=f"{new_w}x{new_h}",
        file_size_kb=f"{file_size / 1024:.0f}",
    )
