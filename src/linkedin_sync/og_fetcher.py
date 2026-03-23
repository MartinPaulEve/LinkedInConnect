"""Fetch OpenGraph metadata from a URL."""

from __future__ import annotations

import requests
import structlog
from bs4 import BeautifulSoup

log = structlog.get_logger(__name__)


def fetch_og_metadata(url: str | None) -> dict:
    """Fetch OpenGraph metadata from a URL.

    Returns a dict with keys: title, description, image.
    On any failure, returns empty/None values gracefully.
    """
    empty = {"title": "", "description": "", "image": None}
    if not url:
        return empty

    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "linkedin-sync/1.0 (OpenGraph fetcher)"},
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("og_fetch_failed", url=url, error=str(exc))
        return empty

    soup = BeautifulSoup(resp.text, "html.parser")

    # OpenGraph tags
    og_title = _og_content(soup, "og:title")
    og_desc = _og_content(soup, "og:description")
    og_image = _og_content(soup, "og:image")

    # Fallbacks
    if not og_title:
        title_tag = soup.find("title")
        og_title = title_tag.get_text(strip=True) if title_tag else ""

    if not og_desc:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        og_desc = meta_desc.get("content", "") if meta_desc else ""

    return {
        "title": og_title or "",
        "description": og_desc or "",
        "image": og_image or None,
    }


def _og_content(soup: BeautifulSoup, prop: str) -> str | None:
    """Extract the content attribute from an OG meta tag."""
    tag = soup.find("meta", property=prop)
    if tag:
        return tag.get("content")
    return None
