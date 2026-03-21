"""LinkedIn API client for posting content and uploading images."""

import os
import tempfile
import urllib.parse
from pathlib import Path

import requests

from logging_config import get_logger

log = get_logger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/rest"
DEFAULT_LINKEDIN_VERSION = "202501"


class LinkedInClient:
    """Client for LinkedIn Community Management API (Posts + Images)."""

    def __init__(
        self,
        access_token: str | None = None,
        person_urn: str | None = None,
        api_version: str | None = None,
    ):
        self.access_token = access_token or os.environ.get(
            "LINKEDIN_ACCESS_TOKEN"
        )
        self.person_urn = person_urn or os.environ.get("LINKEDIN_PERSON_URN")
        self.api_version = (
            api_version
            or os.environ.get("LINKEDIN_API_VERSION")
            or DEFAULT_LINKEDIN_VERSION
        )
        if not self.access_token:
            raise ValueError(
                "LinkedIn access token is required. "
                "Set LINKEDIN_ACCESS_TOKEN environment variable."
            )
        if not self.person_urn:
            raise ValueError(
                "LinkedIn person URN is required. "
                "Set LINKEDIN_PERSON_URN environment variable. "
                "Format: urn:li:person:XXXXXX"
            )
        self._session = requests.Session()
        self._session.headers.update(self._default_headers())
        log.info(
            "linkedin_client_initialized",
            person_urn=self.person_urn,
            api_version=self.api_version,
        )

    def _default_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": self.api_version,
        }

    def get_profile(self) -> dict:
        """Fetch the authenticated user's profile to verify credentials."""
        log.debug("fetching_profile")
        resp = self._session.get(
            f"{LINKEDIN_API_BASE}/me",
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        profile = resp.json()
        log.info("profile_fetched", profile_id=profile.get("id"))
        return profile

    def upload_image(
        self,
        image_path: str | None = None,
        image_url: str | None = None,
    ) -> str:
        """Upload an image to LinkedIn and return the image URN.

        Provide either a local file path or a URL to download from.
        """
        if image_url and not image_path:
            log.info("downloading_image", url=image_url)
            image_path = self._download_image(image_url)

        if not image_path or not Path(image_path).exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        file_size = Path(image_path).stat().st_size
        log.info("uploading_image", path=image_path, size_bytes=file_size)

        # Step 1: Initialize upload
        init_resp = self._session.post(
            f"{LINKEDIN_API_BASE}/images?action=initializeUpload",
            headers={"Content-Type": "application/json"},
            json={
                "initializeUploadRequest": {
                    "owner": self.person_urn,
                }
            },
        )
        if not init_resp.ok:
            log.error(
                "linkedin_api_error",
                status_code=init_resp.status_code,
                response_body=init_resp.text,
            )
        init_resp.raise_for_status()
        init_data = init_resp.json()
        upload_url = init_data["value"]["uploadUrl"]
        image_urn = init_data["value"]["image"]
        log.debug("image_upload_initialized", image_urn=image_urn)

        # Step 2: Upload binary
        with open(image_path, "rb") as f:
            image_data = f.read()

        upload_resp = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream",
            },
            data=image_data,
        )
        upload_resp.raise_for_status()
        log.info(
            "image_uploaded",
            image_urn=image_urn,
            size_bytes=len(image_data),
        )

        return image_urn

    def create_post(
        self,
        text: str,
        image_urn: str | None = None,
        image_alt_text: str | None = None,
        article_url: str | None = None,
        article_title: str | None = None,
        article_description: str | None = None,
    ) -> str:
        """Create a LinkedIn post. Returns the post URN.

        Args:
            text: The post commentary text.
            image_urn: Optional image URN from upload_image().
            image_alt_text: Alt text for the image.
            article_url: Optional URL to share as an article link.
            article_title: Title for the article link.
            article_description: Description for the article link.
        """
        log.info(
            "creating_post",
            text_length=len(text),
            has_image=bool(image_urn),
            has_article=bool(article_url),
        )

        body = {
            "author": self.person_urn,
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        if image_urn:
            body["content"] = {
                "media": {
                    "id": image_urn,
                    "altText": image_alt_text or "Blog post image",
                }
            }
        elif article_url:
            body["content"] = {
                "article": {
                    "source": article_url,
                    "title": article_title or "",
                    "description": article_description or "",
                }
            }

        resp = self._session.post(
            f"{LINKEDIN_API_BASE}/posts",
            headers={"Content-Type": "application/json"},
            json=body,
        )
        if not resp.ok:
            log.error(
                "linkedin_api_error",
                status_code=resp.status_code,
                response_body=resp.text,
            )
        resp.raise_for_status()

        post_urn = resp.headers.get("x-restli-id", "")
        log.info("post_created", post_urn=post_urn)
        return post_urn

    def _download_image(self, url: str) -> str:
        """Download an image from a URL to a temp file and return the path."""
        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "png" in content_type:
            suffix = ".png"
        elif "gif" in content_type:
            suffix = ".gif"
        elif "webp" in content_type:
            suffix = ".webp"
        else:
            suffix = ".jpg"

        # Try to get extension from URL
        parsed = urllib.parse.urlparse(url)
        path_ext = Path(parsed.path).suffix.lower()
        if path_ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            suffix = path_ext

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
            tmp_name = tmp.name
        log.debug(
            "image_downloaded",
            path=tmp_name,
            content_type=content_type,
        )
        return tmp_name
