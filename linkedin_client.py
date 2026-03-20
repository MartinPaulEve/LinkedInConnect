"""LinkedIn API client for posting content and uploading images."""

import os
import requests
import tempfile
import urllib.parse
from pathlib import Path


LINKEDIN_API_BASE = "https://api.linkedin.com/rest"
LINKEDIN_VERSION = "202602"


class LinkedInClient:
    """Client for LinkedIn Community Management API (Posts + Images)."""

    def __init__(self, access_token: str = None, person_urn: str = None):
        self.access_token = access_token or os.environ.get("LINKEDIN_ACCESS_TOKEN")
        self.person_urn = person_urn or os.environ.get("LINKEDIN_PERSON_URN")
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

    def _default_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": LINKEDIN_VERSION,
        }

    def get_profile(self) -> dict:
        """Fetch the authenticated user's profile to verify credentials."""
        resp = self._session.get(
            f"{LINKEDIN_API_BASE}/me",
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    def upload_image(self, image_path: str = None, image_url: str = None) -> str:
        """Upload an image to LinkedIn and return the image URN.

        Provide either a local file path or a URL to download from.
        """
        if image_url and not image_path:
            image_path = self._download_image(image_url)

        if not image_path or not Path(image_path).exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

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
        init_resp.raise_for_status()
        init_data = init_resp.json()
        upload_url = init_data["value"]["uploadUrl"]
        image_urn = init_data["value"]["image"]

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

        return image_urn

    def create_post(
        self,
        text: str,
        image_urn: str = None,
        image_alt_text: str = None,
        article_url: str = None,
        article_title: str = None,
        article_description: str = None,
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
        resp.raise_for_status()

        post_urn = resp.headers.get("x-restli-id", "")
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

        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        for chunk in resp.iter_content(chunk_size=8192):
            tmp.write(chunk)
        tmp.close()
        return tmp.name
