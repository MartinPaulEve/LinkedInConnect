"""LinkedIn API client for posting content and uploading images.

Uses the v2 API (ugcPosts / assets) which works with the
'Share on LinkedIn' product. The versioned REST API (/rest/)
requires the 'Community Management' product.
"""

import os
import tempfile
import urllib.parse
from pathlib import Path

import requests

from logging_config import get_logger

log = get_logger(__name__)

LINKEDIN_V2_BASE = "https://api.linkedin.com/v2"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"


class LinkedInClient:
    """Client for LinkedIn v2 API (Share on LinkedIn product)."""

    def __init__(
        self,
        access_token: str | None = None,
        person_urn: str | None = None,
    ):
        self.access_token = access_token or os.environ.get(
            "LINKEDIN_ACCESS_TOKEN"
        )
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
        log.info(
            "linkedin_client_initialized",
            person_urn=self.person_urn,
        )

    def _default_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def _raise_with_diagnostics(self, resp: requests.Response) -> None:
        """Raise an HTTPError with added diagnostic hints."""
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}

        status = resp.status_code
        message = body.get("message", "")

        hints = []
        if status == 403 and not message:
            hints.append(
                "Empty 403 typically means the access token lacks the "
                "required scope (w_member_social). Regenerate your token "
                "at https://www.linkedin.com/developers/ with the "
                "'Share on LinkedIn' product enabled."
            )
            hints.append(
                "LinkedIn access tokens expire after 60 days. "
                "Check if yours needs refreshing."
            )
        elif status == 403:
            hints.append(
                "Access denied. Verify your app has the correct "
                "permissions and the token is not expired."
            )
        elif status == 401:
            hints.append("Access token is invalid or expired.")

        log.error(
            "linkedin_api_error",
            status_code=status,
            response_body=resp.text,
            url=resp.url,
            hints=hints,
        )
        resp.raise_for_status()

    def get_profile(self) -> dict:
        """Fetch the authenticated user's profile via /v2/userinfo."""
        log.debug("fetching_profile")
        resp = self._session.get(LINKEDIN_USERINFO_URL)
        if not resp.ok:
            self._raise_with_diagnostics(resp)
        profile = resp.json()
        log.info("profile_fetched", name=profile.get("name"))
        return profile

    def upload_image(
        self,
        image_path: str | None = None,
        image_url: str | None = None,
    ) -> str:
        """Upload an image to LinkedIn and return the asset URN.

        Uses the v2 assets API (registerUpload) which works with
        the 'Share on LinkedIn' product.
        """
        if image_url and not image_path:
            log.info("downloading_image", url=image_url)
            image_path = self._download_image(image_url)

        if not image_path or not Path(image_path).exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        file_size = Path(image_path).stat().st_size
        log.info("uploading_image", path=image_path, size_bytes=file_size)

        # Step 1: Register upload
        register_resp = self._session.post(
            f"{LINKEDIN_V2_BASE}/assets?action=registerUpload",
            headers={"Content-Type": "application/json"},
            json={
                "registerUploadRequest": {
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                    "owner": self.person_urn,
                    "serviceRelationships": [
                        {
                            "relationshipType": "OWNER",
                            "identifier": ("urn:li:userGeneratedContent"),
                        }
                    ],
                }
            },
        )
        if not register_resp.ok:
            self._raise_with_diagnostics(register_resp)

        register_data = register_resp.json()
        upload_info = register_data["value"]
        upload_url = upload_info["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading" ".MediaUploadHttpRequest"
        ]["uploadUrl"]
        asset_urn = upload_info["asset"]
        log.debug("image_upload_registered", asset_urn=asset_urn)

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
            asset_urn=asset_urn,
            size_bytes=len(image_data),
        )

        return asset_urn

    def create_post(
        self,
        text: str,
        image_urn: str | None = None,
        image_alt_text: str | None = None,
        article_url: str | None = None,
        article_title: str | None = None,
        article_description: str | None = None,
    ) -> str:
        """Create a LinkedIn post via ugcPosts. Returns the post URN.

        Args:
            text: The post commentary text.
            image_urn: Optional asset URN from upload_image().
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

        share_content: dict = {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "NONE",
        }

        if image_urn:
            share_content["shareMediaCategory"] = "IMAGE"
            share_content["media"] = [
                {
                    "status": "READY",
                    "media": image_urn,
                    "title": {"text": image_alt_text or "Blog post image"},
                }
            ]
        elif article_url:
            share_content["shareMediaCategory"] = "ARTICLE"
            share_content["media"] = [
                {
                    "status": "READY",
                    "originalUrl": article_url,
                    "title": {"text": article_title or ""},
                    "description": {"text": article_description or ""},
                }
            ]

        body = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": share_content
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }

        resp = self._session.post(
            f"{LINKEDIN_V2_BASE}/ugcPosts",
            headers={"Content-Type": "application/json"},
            json=body,
        )
        if not resp.ok:
            self._raise_with_diagnostics(resp)

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
