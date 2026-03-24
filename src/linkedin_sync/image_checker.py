"""Check and resize images referenced in markdown blog posts."""

import os
import re
from pathlib import Path

import yaml
from PIL import Image

from linkedin_sync.logging_config import get_logger

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

    Root-relative paths (starting with /) are resolved against the
    detected site root (e.g. a Jekyll project). Other relative paths
    are resolved against the markdown file's parent directory.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Markdown file not found: {file_path}")

    text = path.read_text(encoding="utf-8")
    base_dir = path.parent
    site_root = _find_site_root(path)
    seen: set[Path] = set()
    result: list[Path] = []

    def _resolve(src: str) -> Path:
        """Resolve an image path against site root or file directory."""
        if src.startswith("/"):
            return (site_root / src.lstrip("/")).resolve()
        return (base_dir / src).resolve()

    def _collect(src: str) -> None:
        resolved = _resolve(src)
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)

    # Extract front matter image fields
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if fm_match:
        try:
            front_matter = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError:
            front_matter = {}
        for key in ("image", "featured_image"):
            val = front_matter.get(key)
            if isinstance(val, dict):
                val = val.get("src") or val.get("url") or val.get("path")
            if isinstance(val, str) and val and not _is_remote(val):
                _collect(val)

    # Markdown image syntax: ![alt](path) or ![alt](path "title")
    for match in re.finditer(r'!\[[^\]]*\]\(([^)"\s]+)', text):
        src = match.group(1)
        if not _is_remote(src):
            _collect(src)

    # HTML <img src="..."> tags
    for match in re.finditer(r'<img\s[^>]*src=["\']([^"\']+)["\']', text):
        src = match.group(1)
        if not _is_remote(src):
            _collect(src)

    log.info(
        "images_extracted",
        file=file_path,
        count=len(result),
        site_root=str(site_root),
    )
    return result


def _find_site_root(file_path: Path) -> Path:
    """Walk up from a file to find the static site root directory.

    Looks for Jekyll/Hugo markers: _config.yml, _config.toml,
    config.toml, hugo.toml, or a _posts directory at the same level.
    Falls back to the markdown file's parent directory.
    """
    markers = (
        "_config.yml",
        "_config.toml",
        "config.toml",
        "hugo.toml",
        "hugo.yaml",
    )
    current = file_path.parent
    for _ in range(20):  # safety limit
        for marker in markers:
            if (current / marker).exists():
                log.debug("site_root_found", root=str(current), marker=marker)
                return current
        if (current / "_posts").is_dir() and current != file_path.parent:
            log.debug("site_root_found", root=str(current), marker="_posts")
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    # If the file is inside a _posts directory, the root is one level up
    if file_path.parent.name == "_posts":
        return file_path.parent.parent
    return file_path.parent


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


def prepare_fallback_image(image_path: str | None) -> str | None:
    """Prepare a local image as an OG fallback thumbnail.

    Copies the image to a temporary file, resizes it to fit within
    1200x630 (standard OG dimensions), and compresses it.
    Returns the path to the prepared temp file, or None on failure.
    The caller is responsible for cleaning up the temp file.
    """
    if not image_path:
        return None

    src = Path(image_path)
    if not src.is_file():
        log.warning(
            "fallback_image_not_found",
            path=image_path,
        )
        return None

    try:
        img = Image.open(src)
        original_format = (img.format or "JPEG").upper()
        ext = ".jpg" if original_format == "JPEG" else ".png"

        import tempfile

        fd, tmp_name = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        tmp_path = Path(tmp_name)

        # Resize to fit OG bounding box
        orig_w, orig_h = img.size
        scale_w = MAX_WIDTH / orig_w
        scale_h = MAX_HEIGHT / orig_h
        scale = min(scale_w, scale_h, 1.0)

        if scale < 1.0:
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        save_kwargs: dict = {}
        if original_format == "JPEG":
            save_kwargs["quality"] = 85
            save_kwargs["optimize"] = True
        elif original_format == "PNG":
            save_kwargs["optimize"] = True

        img.save(str(tmp_path), format=original_format, **save_kwargs)

        log.info(
            "fallback_image_prepared",
            source=image_path,
            output=str(tmp_path),
            size=f"{img.size[0]}x{img.size[1]}",
            file_size_kb=f"{tmp_path.stat().st_size / 1024:.0f}",
        )
        return str(tmp_path)
    except Exception as exc:
        log.warning(
            "fallback_image_prepare_failed",
            path=image_path,
            error=str(exc),
        )
        return None
