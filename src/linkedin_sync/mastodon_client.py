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

    def _upload_multiple_media(
        self,
        paths: list[str],
        alts: list[str] | None = None,
    ) -> list[str]:
        """Upload multiple media files. Returns list of media IDs.

        Mastodon allows up to 4 media attachments per post.
        """
        media_ids = []
        for i, path in enumerate(paths[:4]):  # Mastodon max 4
            desc = alts[i] if alts and i < len(alts) else None
            mid = self._upload_media(path, description=desc)
            if mid:
                media_ids.append(mid)
        return media_ids

    def create_post(
        self,
        text: str,
        visibility: str = "public",
        language: str = "en",
        image_path: str | None = None,
        image_alt: str | None = None,
        image_paths: list[str] | None = None,
        image_alts: list[str] | None = None,
        video_path: str | None = None,
        video_alt: str | None = None,
    ) -> str:
        """Create a Mastodon post. Returns the post URL.

        Links in the text are auto-embedded by Mastodon as preview
        cards, so no explicit link attachment is needed. If video_path
        or image_paths/image_path is provided, media is uploaded and
        attached. Video takes precedence over images.
        """
        # Normalise single image param into list form
        all_paths = image_paths or ([image_path] if image_path else [])
        all_alts = image_alts or ([image_alt] if image_alt else None)

        log.info(
            "creating_mastodon_post",
            text_length=len(text),
            visibility=visibility,
            has_image=bool(all_paths),
            image_count=len(all_paths),
            has_video=bool(video_path),
        )

        kwargs: dict = {
            "visibility": visibility,
            "language": language,
        }

        if video_path:
            media_id = self._upload_media(video_path, description=video_alt)
            if media_id:
                kwargs["media_ids"] = [media_id]
        elif all_paths:
            media_ids = self._upload_multiple_media(all_paths, all_alts)
            if media_ids:
                kwargs["media_ids"] = media_ids

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
        images_by_chunk: (
            dict[int, list[tuple[str, str | None]]] | None
        ) = None,
    ) -> str:
        """Post a thread of statuses. Returns the URL of the first post.

        Each subsequent status is posted as a reply to the previous one.
        Media (video or image) is attached to the chunk at the
        specified index. Video takes precedence over images. When
        *images_by_chunk* is provided it takes precedence over the
        single image_path/image_alt params and maps chunk indices
        to lists of (path, alt) pairs.
        """
        log.info(
            "creating_mastodon_thread",
            chunk_count=len(chunks),
            visibility=visibility,
            has_image=bool(image_path or images_by_chunk),
            has_video=bool(video_path),
        )

        # Build per-chunk media IDs -----------------------------------
        # video_media: single media_id for the video (one chunk only)
        video_media_id = None
        video_chunk_idx = 0
        # chunk_media_ids: mapping from chunk index to list of media_ids
        chunk_media_ids: dict[int, list[str]] = {}

        if video_path:
            video_media_id = self._upload_media(
                video_path, description=video_alt
            )
            video_chunk_idx = video_chunk_index
        elif images_by_chunk:
            for idx, img_list in images_by_chunk.items():
                paths = [p for p, _a in img_list]
                alts = [a for _p, a in img_list]
                media_ids = self._upload_multiple_media(paths, alts)
                if media_ids:
                    chunk_media_ids[idx] = media_ids
        elif image_path:
            media_id = self._upload_media(image_path, description=image_alt)
            if media_id:
                chunk_media_ids[image_chunk_index] = [media_id]

        first_status = None
        parent_id = None

        for i, chunk in enumerate(chunks):
            kwargs: dict = {
                "visibility": visibility,
                "language": language,
            }
            if parent_id is not None:
                kwargs["in_reply_to_id"] = parent_id
            if i == video_chunk_idx and video_media_id:
                kwargs["media_ids"] = [video_media_id]
            elif i in chunk_media_ids:
                kwargs["media_ids"] = chunk_media_ids[i]

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
