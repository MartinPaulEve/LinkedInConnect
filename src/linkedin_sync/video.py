"""Video transcoding and classification utilities.

Provides helpers to detect media type (image vs video), decide
whether transcoding is needed, and transcode to MP4/H.264 via
ffmpeg for maximum cross-platform compatibility.
"""

import enum
import subprocess
import tempfile
from pathlib import Path

from linkedin_sync.logging_config import get_logger

log = get_logger(__name__)

_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
_VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
)

# Formats that don't need transcoding (already MP4/H.264 compatible)
_MP4_COMPATIBLE = frozenset({".mp4", ".m4v"})


class MediaType(enum.Enum):
    IMAGE = "image"
    VIDEO = "video"


def classify_media(path: str) -> MediaType | None:
    """Classify a file path as image, video, or unknown."""
    ext = Path(path).suffix.lower()
    if ext in _IMAGE_EXTENSIONS:
        return MediaType.IMAGE
    if ext in _VIDEO_EXTENSIONS:
        return MediaType.VIDEO
    return None


def needs_transcode(path: str) -> bool:
    """Check if a video file needs transcoding to MP4/H.264."""
    ext = Path(path).suffix.lower()
    return ext not in _MP4_COMPATIBLE


def transcode_video(path: str) -> str:
    """Transcode a video to MP4/H.264 if needed.

    Returns the path to the transcoded file (or the original path
    if no transcoding was necessary). Raises RuntimeError on
    transcode failure.
    """
    if not needs_transcode(path):
        return path

    src = Path(path)
    out = Path(tempfile.mkdtemp()) / f"{src.stem}.mp4"

    log.info(
        "transcoding_video",
        source=str(src),
        destination=str(out),
    )

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(src),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                "-y",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(f"Failed to transcode {src} to MP4: {e}") from e

    out_size = out.stat().st_size if out.exists() else 0
    log.info(
        "video_transcoded",
        source=str(src),
        destination=str(out),
        size_bytes=out_size,
    )
    return str(out)
