"""Format blog post content for LinkedIn posts.

LinkedIn supports a limited subset of formatting in post text:
- Bold (using Unicode bold characters is unreliable; we use **text** which
  LinkedIn renders as bold in the composer but not via API)
- No markdown rendering in API posts - text is plain with some Unicode tricks
- Links are auto-detected from URLs
- Hashtags work with # prefix
- Mentions work with @ prefix
- Maximum post length is ~3000 characters for regular posts

Strategy: Convert HTML content to clean, readable plain text suitable for
LinkedIn, preserving structure with line breaks and bullet points.
"""

import re
from bs4 import BeautifulSoup, NavigableString, Tag

from logging_config import get_logger

log = get_logger(__name__)

# LinkedIn has a ~3000 character limit for post commentary
MAX_LINKEDIN_POST_LENGTH = 3000

# Reserve space for the footer (link, DOI, hashtags)
FOOTER_RESERVE = 500


def format_for_linkedin(
    title: str,
    content_html: str,
    post_url: str,
    doi: str = None,
    tags: list[str] = None,
    max_length: int = MAX_LINKEDIN_POST_LENGTH,
) -> str:
    """Format a blog post for LinkedIn.

    Converts HTML content to LinkedIn-friendly plain text with:
    - A bold-style title header
    - Clean paragraph structure
    - Bullet points preserved
    - Block quotes indicated
    - A footer with the original post link and DOI
    - Relevant hashtags
    """
    log.debug("formatting_post", title=title, html_length=len(content_html))

    # Convert HTML to structured text
    body_text = _html_to_linkedin_text(content_html)

    # Build the post
    parts = []

    # Title
    parts.append(title)
    parts.append("")  # blank line

    # Body (will be truncated if needed)
    parts.append(body_text)

    # Footer
    footer_parts = []
    footer_parts.append("")  # blank line separator

    if doi:
        footer_parts.append(f"DOI: https://doi.org/{doi}")

    footer_parts.append(f"Read the full post: {post_url}")

    if tags:
        hashtags = " ".join(f"#{_sanitize_hashtag(t)}" for t in tags[:5])
        footer_parts.append("")
        footer_parts.append(hashtags)

    footer = "\n".join(footer_parts)

    # Combine and truncate
    full_text = "\n".join(parts)

    available_length = max_length - len(footer) - 10  # 10 chars buffer
    if len(full_text) > available_length:
        log.info(
            "truncating_post",
            original_length=len(full_text),
            max_length=available_length,
        )
        full_text = _truncate_text(full_text, available_length)

    result = full_text + "\n" + footer
    log.info("post_formatted", total_length=len(result), truncated=len(full_text) < len("\n".join(parts)))
    return result


def _html_to_linkedin_text(html: str) -> str:
    """Convert HTML to LinkedIn-friendly plain text."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, and nav elements
    for tag in soup.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()

    lines = []
    _process_element(soup, lines)

    text = "\n".join(lines)

    # Clean up excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    return text


def _process_element(element, lines: list, depth: int = 0):
    """Recursively process HTML elements into plain text lines."""
    if isinstance(element, NavigableString):
        text = str(element).strip()
        if text:
            if lines and not lines[-1].endswith("\n"):
                lines.append(text)
            else:
                lines.append(text)
        return

    if not isinstance(element, Tag):
        return

    tag_name = element.name.lower() if element.name else ""

    # Block-level elements that need line breaks
    block_tags = {
        "p", "div", "section", "article", "main", "aside",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "br", "hr",
    }

    # Headings
    if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        lines.append("")
        text = element.get_text(strip=True)
        if text:
            lines.append(text.upper() if tag_name in ("h1", "h2") else text)
        lines.append("")
        return

    # Paragraphs
    if tag_name == "p":
        lines.append("")
        for child in element.children:
            _process_element(child, lines, depth)
        lines.append("")
        return

    # Line breaks
    if tag_name == "br":
        lines.append("")
        return

    # Horizontal rules
    if tag_name == "hr":
        lines.append("")
        lines.append("---")
        lines.append("")
        return

    # Lists
    if tag_name in ("ul", "ol"):
        lines.append("")
        counter = 0
        for child in element.children:
            if isinstance(child, Tag) and child.name == "li":
                counter += 1
                prefix = f"{counter}. " if tag_name == "ol" else "- "
                text = child.get_text(strip=True)
                if text:
                    lines.append(f"{prefix}{text}")
        lines.append("")
        return

    # Blockquotes
    if tag_name == "blockquote":
        lines.append("")
        text = element.get_text(strip=True)
        if text:
            for line in text.split("\n"):
                line = line.strip()
                if line:
                    lines.append(f'"{line}"')
        lines.append("")
        return

    # Pre/code blocks
    if tag_name in ("pre", "code"):
        if tag_name == "pre":
            lines.append("")
            text = element.get_text()
            for line in text.split("\n"):
                lines.append(f"  {line}")
            lines.append("")
            return

    # Links - include the URL inline
    if tag_name == "a":
        href = element.get("href", "")
        text = element.get_text(strip=True)
        if text and href and not href.startswith("#"):
            lines.append(f"{text} ({href})")
        elif text:
            lines.append(text)
        return

    # Images - skip (handled separately as featured image)
    if tag_name == "img":
        alt = element.get("alt", "")
        if alt:
            lines.append(f"[{alt}]")
        return

    # Figure/figcaption
    if tag_name == "figure":
        for child in element.children:
            if isinstance(child, Tag) and child.name == "figcaption":
                text = child.get_text(strip=True)
                if text:
                    lines.append(f"[{text}]")
        return

    # Bold/italic - just use the text
    if tag_name in ("strong", "b", "em", "i", "mark"):
        text = element.get_text(strip=True)
        if text:
            lines.append(text)
        return

    # Generic block elements
    if tag_name in block_tags:
        lines.append("")
        for child in element.children:
            _process_element(child, lines, depth)
        lines.append("")
        return

    # Default: recurse into children
    for child in element.children:
        _process_element(child, lines, depth)


def _truncate_text(text: str, max_length: int) -> str:
    """Truncate text to max_length, breaking at paragraph or sentence boundary."""
    if len(text) <= max_length:
        return text

    # Try to break at a paragraph boundary
    truncated = text[:max_length]
    last_para = truncated.rfind("\n\n")
    if last_para > max_length * 0.5:
        return truncated[:last_para] + "\n\n..."

    # Try to break at a sentence boundary
    last_sentence = max(
        truncated.rfind(". "),
        truncated.rfind("! "),
        truncated.rfind("? "),
    )
    if last_sentence > max_length * 0.5:
        return truncated[: last_sentence + 1] + "\n\n..."

    # Fall back to word boundary
    last_space = truncated.rfind(" ")
    if last_space > max_length * 0.5:
        return truncated[:last_space] + "..."

    return truncated + "..."


def _sanitize_hashtag(tag: str) -> str:
    """Clean a tag string for use as a LinkedIn hashtag."""
    # Remove special characters, keep alphanumeric
    clean = re.sub(r"[^a-zA-Z0-9]", "", tag)
    return clean
