"""Bluesky client for posting via the AT Protocol."""

import os
import re

import requests
from atproto import Client, client_utils, models

from linkedin_sync.logging_config import get_logger

log = get_logger(__name__)

# Bluesky post limit is 300 graphemes
MAX_POST_LENGTH = 300

# Regex to find URLs in text
_URL_RE = re.compile(r"https?://[^\s)<>]+")


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

    def create_post(
        self,
        text: str,
        link_url: str | None = None,
        link_title: str | None = None,
        link_description: str | None = None,
        thumbnail_url: str | None = None,
        image_path: str | None = None,
        image_alt: str | None = None,
    ) -> str:
        """Create a Bluesky post. Returns the post URL.

        If image_path is provided, the local image is uploaded and
        attached as an image embed. If link_url is provided (and no
        image_path), a link card embed is created. Image embeds take
        precedence over link card embeds. image_alt sets the alt
        text for the image.
        """
        log.info(
            "creating_bluesky_post",
            text_length=len(text),
            has_link=bool(link_url),
            has_thumbnail=bool(thumbnail_url),
            has_image=bool(image_path),
        )

        # Build facets so URLs in the text become clickable links
        text_builder = _build_text_with_links(text)

        embed = None
        if image_path:
            image_blob = self._upload_image_file(image_path)
            if image_blob:
                embed = models.AppBskyEmbedImages.Main(
                    images=[
                        models.AppBskyEmbedImages.Image(
                            alt=image_alt or "",
                            image=image_blob,
                        )
                    ]
                )
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
    ) -> str:
        """Post a thread of messages. Returns the URL of the first post.

        The link card embed is only attached to the first post.
        Each subsequent post is a reply to the previous one.
        If image_path is provided, the image is attached to the chunk
        at image_chunk_index. image_alt sets the alt text.
        """
        log.info(
            "creating_bluesky_thread",
            chunk_count=len(chunks),
            has_link=bool(link_url),
            has_image=bool(image_path),
            image_chunk_index=image_chunk_index if image_path else None,
        )

        # Upload image blob once if provided
        image_blob = None
        if image_path:
            image_blob = self._upload_image_file(image_path)

        root_response = None
        parent_response = None

        for i, chunk in enumerate(chunks):
            text_builder = _build_text_with_links(chunk)

            embed = None
            if i == image_chunk_index and image_blob:
                embed = models.AppBskyEmbedImages.Main(
                    images=[
                        models.AppBskyEmbedImages.Image(
                            alt=image_alt or "",
                            image=image_blob,
                        )
                    ]
                )
            elif i == 0 and link_url and not image_blob:
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

    def _upload_image_file(self, image_path: str):
        """Upload a local image file as a blob.

        Returns the blob reference for use in image embeds, or None
        on failure.
        """
        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
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
