"""Mastodon client for posting statuses."""

import os

from mastodon import Mastodon

from logging_config import get_logger

log = get_logger(__name__)

# Default Mastodon character limit (varies by instance)
DEFAULT_MAX_LENGTH = 500


class MastodonClient:
    """Client for posting to Mastodon."""

    def __init__(
        self,
        instance_url: str | None = None,
        access_token: str | None = None,
    ):
        self.instance_url = (
            instance_url or os.environ.get("MASTODON_INSTANCE_URL", "")
        ).rstrip("/")
        self.access_token = access_token or os.environ.get(
            "MASTODON_ACCESS_TOKEN"
        )

        if not self.instance_url:
            raise ValueError(
                "Mastodon instance URL is required. "
                "Set MASTODON_INSTANCE_URL environment variable "
                "(e.g. https://mastodon.social)."
            )
        if not self.access_token:
            raise ValueError(
                "Mastodon access token is required. "
                "Set MASTODON_ACCESS_TOKEN environment variable. "
                "Create one at: Preferences > Development > "
                "New Application on your Mastodon instance."
            )

        self._client = Mastodon(
            access_token=self.access_token,
            api_base_url=self.instance_url,
        )
        log.info(
            "mastodon_client_initialized",
            instance=self.instance_url,
        )

    def create_post(
        self,
        text: str,
        visibility: str = "public",
        language: str = "en",
    ) -> str:
        """Create a Mastodon post. Returns the post URL.

        Links in the text are auto-embedded by Mastodon as preview
        cards, so no explicit link attachment is needed.
        """
        log.info(
            "creating_mastodon_post",
            text_length=len(text),
            visibility=visibility,
        )

        status = self._client.status_post(
            text,
            visibility=visibility,
            language=language,
        )

        post_url = status["url"]
        log.info("mastodon_post_created", post_url=post_url)
        return post_url
