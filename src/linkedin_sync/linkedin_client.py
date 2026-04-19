"""LinkedIn API client for posting content and uploading images.

Uses the REST API (/rest/posts, /rest/images) with the person URN
auto-resolved from /v2/userinfo. The person URN from userinfo uses
the OIDC 'sub' claim, which differs from the legacy numeric ID.
"""

import os
import tempfile
import urllib.parse
from pathlib import Path

import requests

from linkedin_sync.logging_config import get_logger

log = get_logger(__name__)

LINKEDIN_REST_BASE = "https://api.linkedin.com/rest"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
DEFAULT_LINKEDIN_VERSION = "202604"


class LinkedInClient:
    """Client for LinkedIn REST API (Share on LinkedIn product)."""

    def __init__(
        self,
        access_token: str | None = None,
        person_urn: str | None = None,
        api_version: str | None = None,
    ):
        self.access_token = access_token or os.environ.get(
            "LINKEDIN_ACCESS_TOKEN"
        )
        if not self.access_token:
            raise ValueError(
                "LinkedIn access token is required. "
                "Set LINKEDIN_ACCESS_TOKEN environment variable."
            )
        self.api_version = (
            api_version
            or os.environ.get("LINKEDIN_API_VERSION")
            or DEFAULT_LINKEDIN_VERSION
        )
        self._session = requests.Session()
        self._session.headers.update(self._default_headers())

        # Resolve person URN: prefer auto-detection from /v2/userinfo,
        # fall back to explicit value or env var
        explicit_urn = person_urn or os.environ.get("LINKEDIN_PERSON_URN")
        self.person_urn = self._resolve_person_urn(explicit_urn)

        log.info(
            "linkedin_client_initialized",
            person_urn=self.person_urn,
            api_version=self.api_version,
        )

    def _resolve_person_urn(self, explicit_urn: str | None) -> str:
        """Resolve the person URN from /v2/userinfo sub claim.

        The OIDC 'sub' field is the correct identifier for the
        REST API person URN. Falls back to explicit URN if
        userinfo lookup fails.
        """
        try:
            resp = self._session.get(LINKEDIN_USERINFO_URL)
            if resp.ok:
                sub = resp.json().get("sub")
                if sub:
                    resolved = f"urn:li:person:{sub}"
                    log.info(
                        "person_urn_resolved",
                        source="userinfo",
                        person_urn=resolved,
                    )
                    return resolved
        except Exception as e:
            log.debug("person_urn_resolve_failed", error=str(e))

        if explicit_urn:
            log.info(
                "person_urn_resolved",
                source="explicit",
                person_urn=explicit_urn,
            )
            return explicit_urn

        raise ValueError(
            "Could not resolve LinkedIn person URN. "
            "Set LINKEDIN_PERSON_URN environment variable or "
            "ensure your access token has the 'openid' scope."
        )

    def _default_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": self.api_version,
        }

    def _raise_with_diagnostics(self, resp: requests.Response) -> None:
        """Raise an HTTPError with added diagnostic hints."""
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}

        status = resp.status_code
        code = body.get("code", "")
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
        elif status == 426 and code == "NONEXISTENT_VERSION":
            hints.append(
                f"API version {self.api_version} is not active. "
                "Set LINKEDIN_API_VERSION env var to a supported version."
            )
        elif status == 401:
            hints.append("Access token is invalid or expired.")

        log.error(
            "linkedin_api_error",
            status_code=status,
            response_body=resp.text,
            url=resp.url,
            api_version=self.api_version,
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

        # Step 1: Initialize upload via REST API
        init_resp = self._session.post(
            f"{LINKEDIN_REST_BASE}/images?action=initializeUpload",
            headers={"Content-Type": "application/json"},
            json={
                "initializeUploadRequest": {
                    "owner": self.person_urn,
                }
            },
        )
        if not init_resp.ok:
            self._raise_with_diagnostics(init_resp)
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

    def upload_video(self, video_path: str) -> str:
        """Upload a video to LinkedIn and return the video URN.

        Uses the Videos REST API with a multi-step flow:
        1. Initialize upload (declares file size, gets upload URLs)
        2. Upload binary chunks to the provided URLs
        3. Finalize the upload

        Returns the video URN (e.g. ``urn:li:video:C5F...``).
        """
        if not Path(video_path).exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        file_size = Path(video_path).stat().st_size
        log.info(
            "uploading_video",
            path=video_path,
            size_bytes=file_size,
        )

        # Step 1: Initialize upload
        init_resp = self._session.post(
            f"{LINKEDIN_REST_BASE}/videos?action=initializeUpload",
            headers={"Content-Type": "application/json"},
            json={
                "initializeUploadRequest": {
                    "owner": self.person_urn,
                    "fileSizeBytes": file_size,
                    "uploadCaptions": False,
                    "uploadThumbnail": False,
                }
            },
        )
        if not init_resp.ok:
            self._raise_with_diagnostics(init_resp)

        init_data = init_resp.json()
        video_urn = init_data["value"]["video"]
        upload_instructions = init_data["value"]["uploadInstructions"]
        log.debug(
            "video_upload_initialized",
            video_urn=video_urn,
            num_parts=len(upload_instructions),
        )

        # Step 2: Upload binary chunks
        with open(video_path, "rb") as f:
            video_data = f.read()

        etags: list[dict] = []
        for part in upload_instructions:
            upload_url = part["uploadUrl"]
            # Each instruction may specify byte range; for small
            # files there is typically one part covering the whole
            # file.
            resp = requests.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/octet-stream",
                },
                data=video_data,
            )
            resp.raise_for_status()
            etag = resp.headers.get("ETag")
            if etag:
                etags.append({"etag": etag})

        # Step 3: Finalize upload
        finalize_resp = self._session.post(
            f"{LINKEDIN_REST_BASE}/videos?action=finalizeUpload",
            headers={"Content-Type": "application/json"},
            json={
                "finalizeUploadRequest": {
                    "video": video_urn,
                    "uploadToken": "",
                    "uploadedPartIds": etags or [],
                }
            },
        )
        if not finalize_resp.ok:
            self._raise_with_diagnostics(finalize_resp)

        log.info(
            "video_uploaded",
            video_urn=video_urn,
            size_bytes=file_size,
        )
        return video_urn

    def create_post(
        self,
        text: str,
        image_urn: str | None = None,
        image_alt_text: str | None = None,
        image_urns: list[str] | None = None,
        image_alt_texts: list[str] | None = None,
        video_urn: str | None = None,
        article_url: str | None = None,
        article_title: str | None = None,
        article_description: str | None = None,
    ) -> str:
        """Create a LinkedIn post via REST API. Returns the post URN.

        Args:
            text: The post commentary text.
            image_urn: Optional single image URN from upload_image().
            image_alt_text: Alt text for the single image.
            image_urns: Optional list of image URNs for multi-image.
            image_alt_texts: Alt texts matching image_urns.
            video_urn: Optional video URN from upload_video().
            article_url: Optional URL to share as an article link.
            article_title: Title for the article link.
            article_description: Description for the article link.
        """
        # Normalise: merge single image param into list form
        all_urns = image_urns or ([image_urn] if image_urn else [])
        all_alts = image_alt_texts or (
            [image_alt_text] if image_alt_text else []
        )

        log.info(
            "creating_post",
            text_length=len(text),
            has_image=bool(all_urns),
            image_count=len(all_urns),
            has_video=bool(video_urn),
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

        if video_urn:
            body["content"] = {
                "media": {
                    "id": video_urn,
                }
            }
        elif len(all_urns) > 1:
            # Multi-image post
            images = []
            for i, urn in enumerate(all_urns):
                alt = all_alts[i] if i < len(all_alts) else "Blog post image"
                images.append({"id": urn, "altText": alt})
            body["content"] = {"multiImage": {"images": images}}
        elif len(all_urns) == 1:
            alt = all_alts[0] if all_alts else "Blog post image"
            body["content"] = {
                "media": {
                    "id": all_urns[0],
                    "altText": alt,
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
            f"{LINKEDIN_REST_BASE}/posts",
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
