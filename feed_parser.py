"""Parse the eve.gd Atom feed and extract blog post data."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import feedparser
import markdown
import yaml
from bs4 import BeautifulSoup

from logging_config import get_logger

log = get_logger(__name__)

FEED_URL = "https://eve.gd/feed/feed.atom"
DEFAULT_SITE_URL = "https://eve.gd"

# Jekyll filename pattern: YYYY-MM-DD-slug.ext
_JEKYLL_FILENAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+?)(?:\.\w+)+$")


@dataclass
class BlogPost:
    """A parsed blog post from the Atom feed."""

    id: str
    title: str
    url: str
    published: datetime
    updated: datetime | None
    content_html: str
    summary: str
    featured_image_url: str | None
    doi: str | None
    author: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def published_date(self) -> date:
        return self.published.date()


def parse_feed(feed_url: str = FEED_URL) -> list[BlogPost]:
    """Parse the Atom feed and return a list of BlogPost objects."""
    log.info("parsing_feed", feed_url=feed_url)
    feed = feedparser.parse(feed_url)
    posts = []

    if feed.bozo:
        log.warning("feed_parse_warning", error=str(feed.bozo_exception))

    for entry in feed.entries:
        post = _parse_entry(entry)
        if post:
            posts.append(post)

    log.info("feed_parsed", post_count=len(posts))
    return posts


def _parse_entry(entry) -> BlogPost | None:
    """Parse a single feed entry into a BlogPost."""
    entry_id = getattr(entry, "id", "") or getattr(entry, "link", "")
    title = getattr(entry, "title", "Untitled")
    url = getattr(entry, "link", "")

    # Parse dates
    published = _parse_date(entry, "published_parsed") or _parse_date(
        entry, "updated_parsed"
    )
    updated = _parse_date(entry, "updated_parsed")

    if not published:
        log.warning("skipping_entry_no_date", entry_id=entry_id, title=title)
        return None

    # Get content - prefer full content over summary
    content_html = ""
    if hasattr(entry, "content") and entry.content:
        content_html = entry.content[0].get("value", "")
    elif hasattr(entry, "summary"):
        content_html = entry.summary or ""

    # Extract featured image
    featured_image_url = _extract_featured_image(entry, content_html)

    # Extract DOI
    doi = _extract_doi(content_html, title)

    # Build a text summary
    summary = _html_to_text_summary(content_html, max_length=300)

    # Tags/categories
    tags = []
    if hasattr(entry, "tags"):
        tags = [t.get("term", "") for t in entry.tags if t.get("term")]

    author = ""
    if hasattr(entry, "author"):
        author = entry.author

    log.debug(
        "entry_parsed",
        title=title,
        url=url,
        has_image=bool(featured_image_url),
        has_doi=bool(doi),
        tag_count=len(tags),
    )

    return BlogPost(
        id=entry_id,
        title=title,
        url=url,
        published=published,
        updated=updated,
        content_html=content_html,
        summary=summary,
        featured_image_url=featured_image_url,
        doi=doi,
        author=author,
        tags=tags,
    )


def _parse_date(entry, attr: str) -> datetime | None:
    """Parse a date from a feed entry attribute."""
    parsed = getattr(entry, attr, None)
    if parsed:
        from time import mktime

        return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
    return None


def _extract_featured_image(entry, content_html: str) -> str | None:
    """Extract the featured image URL from entry metadata or content."""
    # Check for media:thumbnail or media:content
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")
    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            is_image = media.get("medium") == "image" or "image" in media.get(
                "type", ""
            )
            if is_image:
                return media.get("url")

    # Check for enclosures
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if "image" in enc.get("type", ""):
                return enc.get("href")

    # Check entry links for image type
    if hasattr(entry, "links"):
        for link in entry.links:
            is_img_enc = link.get(
                "rel"
            ) == "enclosure" and "image" in link.get("type", "")
            if is_img_enc:
                return link.get("href")

    # Fall back to first image in content
    if content_html:
        soup = BeautifulSoup(content_html, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]

    return None


def _extract_doi(content_html: str, title: str = "") -> str | None:
    """Extract a DOI from the content HTML."""
    # Common DOI patterns
    doi_patterns = [
        r'(?:doi\.org/|DOI:\s*|doi:\s*)(10\.\d{4,}/[^\s<>"]+)',
        r'(10\.\d{4,}/[^\s<>"]+)',
    ]

    text_to_search = content_html + " " + title
    for pattern in doi_patterns:
        match = re.search(pattern, text_to_search, re.IGNORECASE)
        if match:
            doi = match.group(1).rstrip(".,;)")
            return doi

    return None


def _html_to_text_summary(html: str, max_length: int = 300) -> str:
    """Convert HTML to plain text and truncate."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    if len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0] + "..."
    return text


def get_todays_posts(feed_url: str = FEED_URL) -> list[BlogPost]:
    """Get only posts published today."""
    today = date.today()
    posts = [p for p in parse_feed(feed_url) if p.published_date == today]
    log.info(
        "todays_posts_filtered",
        today=today.isoformat(),
        count=len(posts),
    )
    return posts


def get_post_by_url(url: str, feed_url: str = FEED_URL) -> BlogPost | None:
    """Find a specific post by its URL."""
    log.info("searching_post_by_url", target_url=url)
    for post in parse_feed(feed_url):
        if post.url == url or post.id == url:
            log.info("post_found", title=post.title)
            return post
    log.warning("post_not_found", target_url=url)
    return None


def _url_from_jekyll_filename(filename: str, site_url: str) -> str | None:
    """Derive a URL from a Jekyll-style filename (YYYY-MM-DD-slug.ext)."""
    m = _JEKYLL_FILENAME_RE.match(filename)
    if not m:
        return None
    year, month, day, slug = m.groups()
    return f"{site_url.rstrip('/')}/{year}/{month}/{day}/{slug}/"


def parse_markdown_file(
    file_path: str, site_url: str = DEFAULT_SITE_URL
) -> BlogPost:
    """Parse a local markdown file with YAML front matter into a BlogPost.

    Expected front matter fields:
        title (required), date, tags, image, doi, author

    If *url* / *permalink* is absent the URL is inferred from a Jekyll-style
    filename (``YYYY-MM-DD-slug.ext``) combined with *site_url*.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Markdown file not found: {file_path}")

    text = path.read_text(encoding="utf-8")
    front_matter, body = _split_front_matter(text)

    title = front_matter.get("title")
    url = (
        front_matter.get("url")
        or front_matter.get("permalink")
        or _url_from_jekyll_filename(path.name, site_url)
    )
    if not title or not url:
        raise ValueError(
            f"Markdown file must have 'title' and 'url' in front matter: "
            f"{file_path}"
        )

    # Parse date
    raw_date = front_matter.get("date")
    if isinstance(raw_date, datetime):
        published = raw_date.replace(tzinfo=timezone.utc)
    elif isinstance(raw_date, date):
        published = datetime(
            raw_date.year, raw_date.month, raw_date.day, tzinfo=timezone.utc
        )
    elif isinstance(raw_date, str):
        published = _parse_front_matter_date(raw_date)
    else:
        published = datetime.now(tz=timezone.utc)

    # Convert markdown body to HTML
    content_html = markdown.markdown(
        body, extensions=["extra", "codehilite", "toc"]
    )

    # Extract tags
    raw_tags = front_matter.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.split(",")]
    tags = [t for t in raw_tags if t]

    # Featured image — may be a string or a Jekyll-style dict with a
    # "feature" key (e.g.  image: {feature: photo.jpg, credit: ...})
    raw_image = front_matter.get("image") or front_matter.get("featured_image")
    if isinstance(raw_image, dict):
        featured_image_url = raw_image.get("feature") or raw_image.get("url")
    else:
        featured_image_url = raw_image

    # Resolve relative image filenames to full URLs under /images/
    if featured_image_url and not featured_image_url.startswith(
        ("http://", "https://", "/")
    ):
        featured_image_url = (
            f"{site_url.rstrip('/')}/images/{featured_image_url}"
        )

    # DOI - check front matter first, then content
    doi_value = front_matter.get("doi") or _extract_doi(content_html, title)

    summary = _html_to_text_summary(content_html, max_length=300)

    log.info(
        "markdown_file_parsed",
        file=file_path,
        title=title,
        url=url,
        has_image=bool(featured_image_url),
        has_doi=bool(doi_value),
        tag_count=len(tags),
    )

    return BlogPost(
        id=url,
        title=title,
        url=url,
        published=published,
        updated=None,
        content_html=content_html,
        summary=summary,
        featured_image_url=featured_image_url,
        doi=doi_value,
        author=front_matter.get("author", ""),
        tags=tags,
    )


def _split_front_matter(text: str) -> tuple[dict, str]:
    """Split YAML front matter from markdown body."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return {}, text

    try:
        front_matter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        log.warning("front_matter_parse_error", error=str(e))
        front_matter = {}

    return front_matter, match.group(2)


def _parse_front_matter_date(date_str: str) -> datetime:
    """Parse common date formats from front matter."""
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    log.warning("unparseable_date", date_str=date_str)
    return datetime.now(tz=timezone.utc)
