"""Mastodon client for posting statuses."""

import os

from mastodon import Mastodon

from linkedin_sync.logging_config import get_logger

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
        image_path: str | None = None,
        image_alt: str | None = None,
        video_path: str | None = None,
        video_alt: str | None = None,
    ) -> str:
        """Create a Mastodon post. Returns the post URL.

        Links in the text are auto-embedded by Mastodon as preview
        cards, so no explicit link attachment is needed. If video_path
        or image_path is provided, the media is uploaded and attached.
        Video takes precedence over image.
        """
        log.info(
            "creating_mastodon_post",
            text_length=len(text),
            visibility=visibility,
            has_image=bool(image_path),
            has_video=bool(video_path),
        )

        kwargs: dict = {
            "visibility": visibility,
            "language": language,
        }

        if video_path:
            media_id = self._upload_media(
                video_path, description=video_alt
            )
            if media_id:
                kwargs["media_ids"] = [media_id]
        elif image_path:
            media_id = self._upload_media(
                image_path, description=image_alt
            )
            if media_id:
                kwargs["media_ids"] = [media_id]

        status = self._client.status_post(text, **kwargs)

        post_url = status["url"]
        log.info("mastodon_post_created", post_url=post_url)
        return post_url

    def create_thread(
        self,
        chunks: list[str],
        visibility: str = "public",
        language: str = "en",
        image_path: str | None = None,
        image_chunk_index: int = 0,
        image_alt: str | None = None,
        video_path: str | None = None,
        video_chunk_index: int = 0,
        video_alt: str | None = None,
    ) -> str:
        """Post a thread of statuses. Returns the URL of the first post.

        Each subsequent status is posted as a reply to the previous one.
        Media (video or image) is attached to the chunk at the
        specified index. Video takes precedence over image.
        """
        log.info(
            "creating_mastodon_thread",
            chunk_count=len(chunks),
            visibility=visibility,
            has_image=bool(image_path),
            has_video=bool(video_path),
        )

        # Upload media once if provided (video takes priority)
        media_id = None
        media_chunk_idx = 0
        if video_path:
            media_id = self._upload_media(
                video_path, description=video_alt
            )
            media_chunk_idx = video_chunk_index
        elif image_path:
            media_id = self._upload_media(
                image_path, description=image_alt
            )
            media_chunk_idx = image_chunk_index

        first_status = None
        parent_id = None

        for i, chunk in enumerate(chunks):
            kwargs: dict = {
                "visibility": visibility,
                "language": language,
            }
            if parent_id is not None:
                kwargs["in_reply_to_id"] = parent_id
            if i == media_chunk_idx and media_id:
                kwargs["media_ids"] = [media_id]

            status = self._client.status_post(chunk, **kwargs)

            if first_status is None:
                first_status = status
            parent_id = status["id"]

        post_url = first_status["url"]
        log.info(
            "mastodon_thread_created",
            post_url=post_url,
            chunk_count=len(chunks),
        )
        return post_url

    def _upload_media(
        self, image_path: str, description: str | None = None
    ) -> str | None:
        """Upload a local image file and return the media ID.

        If description is provided it is set as the alt text for
        the media attachment. Returns the media ID string, or None
        on failure.
        """
        try:
            kwargs: dict = {}
            if description:
                kwargs["description"] = description
            media = self._client.media_post(image_path, **kwargs)
            media_id = media["id"]
            log.info(
                "mastodon_media_uploaded",
                image_path=image_path,
                media_id=media_id,
            )
            return media_id
        except Exception as e:
            log.warning(
                "mastodon_media_upload_failed",
                image_path=image_path,
                error=str(e),
            )
            return None
