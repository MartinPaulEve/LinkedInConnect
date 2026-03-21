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
    ) -> str:
        """Create a Bluesky post. Returns the post URL.

        If link_url is provided, a link card embed is created.
        If thumbnail_url is also provided, the image is fetched and
        attached to the link card as a thumbnail preview.
        """
        log.info(
            "creating_bluesky_post",
            text_length=len(text),
            has_link=bool(link_url),
            has_thumbnail=bool(thumbnail_url),
        )

        # Build facets so URLs in the text become clickable links
        text_builder = _build_text_with_links(text)

        embed = None
        if link_url:
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
