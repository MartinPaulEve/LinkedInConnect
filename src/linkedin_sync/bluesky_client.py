"""Bluesky client for posting via the AT Protocol."""

import io
import os
import re

import requests
from atproto import Client, client_utils, models
from PIL import Image

from linkedin_sync.logging_config import get_logger

log = get_logger(__name__)

# Bluesky post limit is 300 graphemes
MAX_POST_LENGTH = 300

# Bluesky image blob size limit (976.56 KB ≈ 1,000,000 bytes)
BLUESKY_MAX_IMAGE_SIZE = 1_000_000

# Regex to find URLs in text
_URL_RE = re.compile(r"https?://[^\s)<>]+")


def _resize_image_data(
    data: bytes,
    max_size: int = BLUESKY_MAX_IMAGE_SIZE,
) -> bytes:
    """Resize image data in-memory so it fits under *max_size* bytes.

    If the image is already small enough it is returned unchanged.
    Otherwise the image is progressively scaled down and re-encoded
    as JPEG (for better compression) until it fits. The aspect ratio
    is always preserved.
    """
    if len(data) <= max_size:
        return data

    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    orig_w, orig_h = img.size
    log.info(
        "bluesky_image_resize_start",
        original_bytes=len(data),
        max_bytes=max_size,
        dimensions=f"{orig_w}x{orig_h}",
    )

    # Try progressively smaller scales
    for scale in (0.75, 0.5, 0.35, 0.25, 0.15, 0.1):
        new_w = max(1, int(orig_w * scale))
        new_h = max(1, int(orig_h * scale))
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=85, optimize=True)
        result = buf.getvalue()
        if len(result) <= max_size:
            log.info(
                "bluesky_image_resized",
                new_bytes=len(result),
                new_dimensions=f"{new_w}x{new_h}",
                scale=f"{scale:.2f}",
            )
            return result

    # Last resort: very aggressive quality reduction at smallest scale
    new_w = max(1, int(orig_w * 0.1))
    new_h = max(1, int(orig_h * 0.1))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=60, optimize=True)
    result = buf.getvalue()
    log.warning(
        "bluesky_image_resize_aggressive",
        final_bytes=len(result),
        new_dimensions=f"{new_w}x{new_h}",
    )
    return result


def _build_text_with_links(text: str) -> client_utils.TextBuilder:
    """Build a TextBuilder that turns URLs into clickable link facets."""
    builder = client_utils.TextBuilder()
    last_end = 0
    for match in _URL_RE.finditer(text):
        start, end = match.span()
        if start > last_end:
            builder.text(text[last_end:start])
        url = match.group(0)
        builder.link(url, url)
        last_end = end
    if last_end < len(text):
        builder.text(text[last_end:])
    return builder


class BlueskyClient:
    """Client for posting to Bluesky via the AT Protocol."""

    def __init__(
        self,
        handle: str | None = None,
        app_password: str | None = None,
    ):
        self.handle = handle or os.environ.get("BLUESKY_HANDLE")
        self.app_password = app_password or os.environ.get(
            "BLUESKY_APP_PASSWORD"
        )
        if not self.handle:
            raise ValueError(
                "Bluesky handle is required. "
                "Set BLUESKY_HANDLE environment variable "
                "(e.g. yourname.bsky.social)."
            )
        if not self.app_password:
            raise ValueError(
                "Bluesky app password is required. "
                "Set BLUESKY_APP_PASSWORD environment variable. "
                "Create one at: Settings > Privacy and Security "
                "> App Passwords on bsky.app"
            )

        self._client = Client()
        self._client.login(self.handle, self.app_password)
        log.info("bluesky_client_initialized", handle=self.handle)

    def _build_images_embed(
        self,
        paths: list[str],
        alts: list[str] | None = None,
    ):
        """Upload images and build an AppBskyEmbedImages.Main embed.

        Returns the embed, or None if no images uploaded successfully.
        Bluesky allows up to 4 images per post.
        """
        image_items = []
        for i, path in enumerate(paths[:4]):  # Bluesky max 4 images
            blob = self._upload_image_file(path)
            if blob:
                alt = alts[i] if alts and i < len(alts) else ""
                image_items.append(
                    models.AppBskyEmbedImages.Image(alt=alt, image=blob)
                )
        if not image_items:
            return None
        return models.AppBskyEmbedImages.Main(images=image_items)

    def create_post(
        self,
        text: str,
        link_url: str | None = None,
        link_title: str | None = None,
        link_description: str | None = None,
        thumbnail_url: str | None = None,
        image_path: str | None = None,
        image_alt: str | None = None,
        image_paths: list[str] | None = None,
        image_alts: list[str] | None = None,
        video_path: str | None = None,
        video_alt: str | None = None,
    ) -> str:
        """Create a Bluesky post. Returns the post URL.

        If video_path is provided, the video is uploaded and attached
        as a video embed. If image_paths (or image_path) is provided,
        images are uploaded as an image embed (up to 4). If link_url
        is provided (and no media), a link card embed is created.
        Video > images > link.
        """
        # Normalise single image param into list form
        all_paths = image_paths or ([image_path] if image_path else [])
        all_alts = image_alts or ([image_alt] if image_alt else None)

        log.info(
            "creating_bluesky_post",
            text_length=len(text),
            has_link=bool(link_url),
            has_thumbnail=bool(thumbnail_url),
            has_image=bool(all_paths),
            image_count=len(all_paths),
            has_video=bool(video_path),
        )

        # Build facets so URLs in the text become clickable links
        text_builder = _build_text_with_links(text)

        embed = None
        if video_path:
            video_blob = self._upload_video_file(video_path)
            if video_blob:
                embed = models.AppBskyEmbedVideo.Main(
                    video=video_blob,
                    alt=video_alt or None,
                )
        elif all_paths:
            embed = self._build_images_embed(all_paths, all_alts)
        if embed is None and link_url:
            thumb_blob = None
            if thumbnail_url:
                thumb_blob = self._upload_thumbnail(thumbnail_url)

            embed = models.AppBskyEmbedExternal.Main(
                external=models.AppBskyEmbedExternal.External(
                    uri=link_url,
                    title=link_title or "",
                    description=link_description or "",
                    thumb=thumb_blob,
                )
            )

        response = self._client.send_post(text_builder, embed=embed)

        # Build the post URL from the response
        # response.uri is like at://did:plc:xxx/app.bsky.feed.post/rkey
        post_url = self._uri_to_url(response.uri)
        log.info("bluesky_post_created", post_url=post_url)
        return post_url

    def create_thread(
        self,
        chunks: list[str],
        link_url: str | None = None,
        link_title: str | None = None,
        link_description: str | None = None,
        thumbnail_url: str | None = None,
        image_path: str | None = None,
        image_chunk_index: int = 0,
        image_alt: str | None = None,
        video_path: str | None = None,
        video_chunk_index: int = 0,
        video_alt: str | None = None,
        images_by_chunk: (
            dict[int, list[tuple[str, str | None]]] | None
        ) = None,
    ) -> str:
        """Post a thread of messages. Returns the URL of the first post.

        The link card embed is only attached to the first post.
        Each subsequent post is a reply to the previous one.
        Media (video or image) is attached to the chunk at the
        specified index. When *images_by_chunk* is provided it
        takes precedence over the single image_path/image_alt
        params and maps chunk indices to lists of (path, alt) pairs.
        """
        log.info(
            "creating_bluesky_thread",
            chunk_count=len(chunks),
            has_link=bool(link_url),
            has_image=bool(image_path or images_by_chunk),
            has_video=bool(video_path),
        )

        # Upload media blobs ------------------------------------------
        video_blob = None
        if video_path:
            video_blob = self._upload_video_file(video_path)

        # Build per-chunk image embeds when images_by_chunk is given
        chunk_embeds: dict[int, object] = {}
        has_media = bool(video_blob)

        if not video_blob and images_by_chunk:
            for idx, img_list in images_by_chunk.items():
                embed = self._build_images_embed(
                    [p for p, _a in img_list],
                    [a or "" for _p, a in img_list],
                )
                if embed:
                    chunk_embeds[idx] = embed
                    has_media = True
        elif not video_blob and image_path:
            image_blob = self._upload_image_file(image_path)
            if image_blob:
                has_media = True
                chunk_embeds[image_chunk_index] = (
                    models.AppBskyEmbedImages.Main(
                        images=[
                            models.AppBskyEmbedImages.Image(
                                alt=image_alt or "",
                                image=image_blob,
                            )
                        ]
                    )
                )

        root_response = None
        parent_response = None

        for i, chunk in enumerate(chunks):
            text_builder = _build_text_with_links(chunk)

            embed = None
            if i == video_chunk_index and video_blob:
                embed = models.AppBskyEmbedVideo.Main(
                    video=video_blob,
                    alt=video_alt or None,
                )
            elif i in chunk_embeds:
                embed = chunk_embeds[i]
            elif i == 0 and link_url and not has_media:
                thumb_blob = None
                if thumbnail_url:
                    thumb_blob = self._upload_thumbnail(thumbnail_url)
                embed = models.AppBskyEmbedExternal.Main(
                    external=models.AppBskyEmbedExternal.External(
                        uri=link_url,
                        title=link_title or "",
                        description=link_description or "",
                        thumb=thumb_blob,
                    )
                )

            reply_to = None
            if parent_response is not None:
                reply_to = models.AppBskyFeedPost.ReplyRef(
                    parent=models.create_strong_ref(parent_response),
                    root=models.create_strong_ref(root_response),
                )

            response = self._client.send_post(
                text_builder, embed=embed, reply_to=reply_to
            )

            if i == 0:
                root_response = response
            parent_response = response

        post_url = self._uri_to_url(root_response.uri)
        log.info(
            "bluesky_thread_created",
            post_url=post_url,
            chunk_count=len(chunks),
        )
        return post_url

    def _upload_video_file(self, video_path: str):
        """Upload a local video file as a blob.

        Returns the blob reference for use in video embeds, or None
        on failure.
        """
        try:
            with open(video_path, "rb") as f:
                video_data = f.read()
            upload = self._client.upload_blob(video_data)
            log.info(
                "bluesky_video_uploaded",
                video_path=video_path,
                size=len(video_data),
            )
            return upload.blob
        except Exception as e:
            log.warning(
                "bluesky_video_upload_failed",
                video_path=video_path,
                error=str(e),
            )
            return None

    def _upload_image_file(self, image_path: str):
        """Upload a local image file as a blob.

        If the file exceeds Bluesky's size limit it is automatically
        resized in-memory (preserving aspect ratio) before uploading.

        Returns the blob reference for use in image embeds, or None
        on failure.
        """
        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
            image_data = _resize_image_data(image_data)
            upload = self._client.upload_blob(image_data)
            log.info(
                "bluesky_image_uploaded",
                image_path=image_path,
                size=len(image_data),
            )
            return upload.blob
        except Exception as e:
            log.warning(
                "bluesky_image_upload_failed",
                image_path=image_path,
                error=str(e),
            )
            return None

    def _upload_thumbnail(self, image_url: str):
        """Fetch an image from a URL and upload it as a blob.

        Returns the blob reference for use in embeds, or None on failure.
        """
        try:
            resp = requests.get(image_url, timeout=15)
            resp.raise_for_status()
            upload = self._client.upload_blob(resp.content)
            log.info(
                "bluesky_thumbnail_uploaded",
                image_url=image_url,
                size=len(resp.content),
            )
            return upload.blob
        except Exception as e:
            log.warning(
                "bluesky_thumbnail_upload_failed",
                image_url=image_url,
                error=str(e),
            )
            return None

    def _uri_to_url(self, at_uri: str) -> str:
        """Convert an AT URI to a bsky.app URL."""
        # at://did:plc:xxx/app.bsky.feed.post/rkey
        match = re.match(
            r"at://(did:[^/]+)/app\.bsky\.feed\.post/(.+)", at_uri
        )
        if match:
            rkey = match.group(2)
            return f"https://bsky.app/profile/{self.handle}/post/{rkey}"
        return at_uri
