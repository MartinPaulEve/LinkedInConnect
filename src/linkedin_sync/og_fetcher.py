"""Fetch OpenGraph metadata from a URL."""

from __future__ import annotations

import re

import requests
import structlog
from bs4 import BeautifulSoup

log = structlog.get_logger(__name__)

_DOI_URL_RE = re.compile(r"^https?://(?:dx\.)?doi\.org/(10\.\d{4,}/\S+)$")


def fetch_og_metadata(url: str | None) -> dict:
    """Fetch OpenGraph metadata from a URL.

    Returns a dict with keys: title, description, image.
    On any failure, returns empty/None values gracefully.
    For DOI URLs, falls back to DOI content negotiation when
    the target site blocks the request.
    """
    empty = {"title": "", "description": "", "image": None}
    if not url:
        return empty

    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": ("linkedin-sync/1.0 (OpenGraph fetcher)"),
            },
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("og_fetch_failed", url=url, error=str(exc))
        # Fall back to DOI content negotiation for DOI URLs
        doi_match = _DOI_URL_RE.match(url)
        if doi_match:
            log.info("doi_fallback", doi=doi_match.group(1))
            return _fetch_doi_metadata(doi_match.group(1))
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


def _fetch_doi_metadata(doi: str) -> dict:
    """Fetch metadata via DOI content negotiation.

    Uses the Citeproc JSON format from doi.org, which provides
    title and abstract without needing to visit the target site.
    """
    empty = {"title": "", "description": "", "image": None}

    try:
        resp = requests.get(
            f"https://doi.org/{doi}",
            timeout=15,
            headers={"Accept": "application/citeproc+json"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("doi_metadata_failed", doi=doi, error=str(exc))
        return empty

    # Title may be a list (CrossRef) or a string (DataCite)
    raw_title = data.get("title", "")
    if isinstance(raw_title, list):
        title = raw_title[0] if raw_title else ""
    else:
        title = raw_title

    # Abstract may contain HTML/JATS markup
    raw_abstract = data.get("abstract", "")
    description = _strip_html(raw_abstract)

    return {
        "title": title or "",
        "description": description or "",
        "image": None,
    }


def _strip_html(text: str) -> str:
    """Remove HTML/JATS tags from a string."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    # Use get_text() and normalise whitespace (separator=" " can
    # introduce spaces before punctuation at tag boundaries).
    raw = soup.get_text()
    return " ".join(raw.split())


def _og_content(soup: BeautifulSoup, prop: str) -> str | None:
    """Extract the content attribute from an OG meta tag."""
    tag = soup.find("meta", property=prop)
    if tag:
        return tag.get("content")
    return None
