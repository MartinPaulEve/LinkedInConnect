#!/usr/bin/env python3
"""Sync blog posts to LinkedIn, Bluesky, and Mastodon."""

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import click
from dotenv import load_dotenv

from linkedin_sync.feed_parser import (
    get_feed_url,
    get_post_by_url,
    get_todays_posts,
    parse_markdown_file,
)
from linkedin_sync.formatter import format_for_linkedin
from linkedin_sync.logging_config import configure_logging, get_logger
from linkedin_sync.summarizer import summarize_post, summarize_post_short
from linkedin_sync.sync_tracker import SyncTracker
from linkedin_sync.threader import split_message

log = get_logger(__name__)

# Regex to find URLs in text (used by the single command)
_URL_RE = re.compile(r"https?://[^\s)<>]+")

# Regex to find local image file paths in text
# Matches absolute paths, ~/paths, and ./paths ending with image extensions
_IMAGE_PATH_RE = re.compile(
    r"(?:~|\.\.?)?/[^\s]+\.(?:png|jpg|jpeg|gif|webp)", re.IGNORECASE
)


def _extract_local_image(message: str) -> tuple[str, str | None]:
    """Extract a local image path from the message text.

    Returns (clean_message, resolved_image_path) or (message, None) if
    no valid local image was found. The image path is removed from the
    message text and extra whitespace is collapsed.
    """
    match = _IMAGE_PATH_RE.search(message)
    if not match:
        return message, None

    path_str = match.group(0)

    # Skip URLs (http/https) - they shouldn't match but be safe
    before = message[: match.start()]
    if before.rstrip().endswith(("http:", "https:")):
        return message, None

    resolved = Path(path_str).expanduser().resolve()
    if not resolved.exists():
        return message, None

    # Remove the path from the message and clean up whitespace
    clean = message[: match.start()] + message[match.end() :]
    clean = re.sub(r"  +", " ", clean).strip()

    return clean, str(resolved)


def _image_chunk_index(
    char_position: int, message_length: int, num_chunks: int
) -> int:
    """Determine which thread chunk an image should be attached to.

    Uses the character position of the image in the original message
    to map it proportionally to the correct chunk.
    """
    if num_chunks <= 1:
        return 0
    if message_length <= 0:
        return 0
    fraction = char_position / message_length
    return min(int(fraction * num_chunks), num_chunks - 1)


@dataclass
class SyncResult:
    """Result of syncing a post across all platforms."""

    linkedin_urn: str = ""
    linkedin_error: str = ""
    bluesky_url: str = ""
    bluesky_error: str = ""
    mastodon_url: str = ""
    mastodon_error: str = ""

    @property
    def any_success(self) -> bool:
        return bool(self.linkedin_urn or self.bluesky_url or self.mastodon_url)


def sync_post(
    post,
    tracker: SyncTracker,
    dry_run: bool = False,
    summary: bool = True,
    linkedin_client=None,
    bluesky_client=None,
    mastodon_client=None,
) -> SyncResult:
    """Sync a single blog post to all configured platforms."""
    log.info(
        "sync_post_start",
        title=post.title,
        url=post.url,
        published=post.published.isoformat(),
        has_image=bool(post.featured_image_url),
        has_doi=bool(post.doi),
        summary_mode=summary,
    )

    # Generate content for each platform
    if summary:
        linkedin_text = summarize_post(
            title=post.title,
            content_html=post.content_html,
            post_url=post.url,
            doi=post.doi,
            tags=post.tags,
        )
        bluesky_text = summarize_post_short(
            title=post.title,
            content_html=post.content_html,
            post_url=post.url,
            max_chars=300,
        )
        mastodon_text = summarize_post_short(
            title=post.title,
            content_html=post.content_html,
            post_url=post.url,
            max_chars=500,
        )
    else:
        linkedin_text = format_for_linkedin(
            title=post.title,
            content_html=post.content_html,
            post_url=post.url,
            doi=post.doi,
            tags=post.tags,
        )
        # For non-summary mode, use the LinkedIn text truncated
        bluesky_text = None
        mastodon_text = None

    if dry_run:
        log.info(
            "dry_run_preview",
            title=post.title,
            linkedin_chars=len(linkedin_text),
            linkedin_text=linkedin_text,
        )
        if bluesky_text:
            log.info(
                "dry_run_bluesky",
                chars=len(bluesky_text),
                text=bluesky_text,
            )
        if mastodon_text:
            log.info(
                "dry_run_mastodon",
                chars=len(mastodon_text),
                text=mastodon_text,
            )
        return SyncResult()

    result = SyncResult()

    # --- LinkedIn ---
    if linkedin_client:
        result.linkedin_urn = _post_to_linkedin(
            linkedin_client, post, linkedin_text, summary, result
        )

    # --- Bluesky ---
    if bluesky_client and bluesky_text:
        result.bluesky_url = _post_to_bluesky(
            bluesky_client, post, bluesky_text, result
        )

    # --- Mastodon ---
    if mastodon_client and mastodon_text:
        result.mastodon_url = _post_to_mastodon(
            mastodon_client, mastodon_text, result
        )

    # Log the report
    _log_report(post.title, result)

    # Record the sync if anything succeeded
    if result.any_success:
        tracker.mark_synced(
            post_url=post.url,
            post_title=post.title,
            linkedin_post_urn=result.linkedin_urn,
            post_published=post.published,
            bluesky_post_url=result.bluesky_url,
            mastodon_post_url=result.mastodon_url,
        )

    return result


def _post_to_linkedin(client, post, linkedin_text, summary, result):
    """Post to LinkedIn. Returns the post URN or empty string."""
    # Upload featured image if available
    image_urn = None
    if post.featured_image_url:
        try:
            image_urn = client.upload_image(image_url=post.featured_image_url)
        except Exception as e:
            log.warning(
                "linkedin_image_upload_failed",
                url=post.featured_image_url,
                error=str(e),
            )

    try:
        if summary and not image_urn:
            # In summary mode without an uploaded image, use article
            # embed so LinkedIn shows a link preview card
            post_urn = client.create_post(
                text=linkedin_text,
                article_url=post.url,
                article_title=post.title,
                article_description=post.summary,
            )
        else:
            post_urn = client.create_post(
                text=linkedin_text,
                image_urn=image_urn,
                image_alt_text=f"Featured image for: {post.title}",
            )
        log.info("linkedin_posted", post_urn=post_urn)
        return post_urn
    except Exception as e:
        log.error("linkedin_post_failed", error=str(e))
        result.linkedin_error = str(e)
        return ""


def _post_to_bluesky(client, post, bluesky_text, result):
    """Post to Bluesky. Returns the post URL or empty string."""
    try:
        post_url = client.create_post(
            text=bluesky_text,
            link_url=post.url,
            link_title=post.title,
            link_description=post.summary,
            thumbnail_url=post.featured_image_url,
        )
        log.info("bluesky_posted", post_url=post_url)
        return post_url
    except Exception as e:
        log.error("bluesky_post_failed", error=str(e))
        result.bluesky_error = str(e)
        return ""


def _post_to_mastodon(client, mastodon_text, result):
    """Post to Mastodon. Returns the post URL or empty string."""
    try:
        post_url = client.create_post(text=mastodon_text)
        log.info("mastodon_posted", post_url=post_url)
        return post_url
    except Exception as e:
        log.error("mastodon_post_failed", error=str(e))
        result.mastodon_error = str(e)
        return ""


def _log_report(title, result):
    """Log a summary report of the sync results."""
    log.info(
        "sync_report",
        title=title,
        linkedin="ok"
        if result.linkedin_urn
        else "skipped"
        if not result.linkedin_error
        else f"FAILED: {result.linkedin_error}",
        bluesky="ok"
        if result.bluesky_url
        else "skipped"
        if not result.bluesky_error
        else f"FAILED: {result.bluesky_error}",
        mastodon="ok"
        if result.mastodon_url
        else "skipped"
        if not result.mastodon_error
        else f"FAILED: {result.mastodon_error}",
    )
    if result.linkedin_urn:
        log.info("linkedin_link", urn=result.linkedin_urn)
    if result.bluesky_url:
        log.info("bluesky_link", url=result.bluesky_url)
    if result.mastodon_url:
        log.info("mastodon_link", url=result.mastodon_url)


def _make_linkedin_client(dry_run: bool):
    """Create a LinkedIn client, or None if not configured."""
    if dry_run and not os.environ.get("LINKEDIN_ACCESS_TOKEN"):
        return None
    try:
        from linkedin_sync.linkedin_client import LinkedInClient

        return LinkedInClient()
    except ValueError as e:
        log.warning("linkedin_client_skipped", error=str(e))
        return None


def _make_bluesky_client(dry_run: bool):
    """Create a Bluesky client, or None if not configured."""
    if dry_run and not os.environ.get("BLUESKY_HANDLE"):
        return None
    try:
        from linkedin_sync.bluesky_client import BlueskyClient

        return BlueskyClient()
    except ValueError as e:
        log.warning("bluesky_client_skipped", error=str(e))
        return None


def _make_mastodon_client(dry_run: bool):
    """Create a Mastodon client, or None if not configured."""
    if dry_run and not os.environ.get("MASTODON_ACCESS_TOKEN"):
        return None
    try:
        from linkedin_sync.mastodon_client import MastodonClient

        return MastodonClient()
    except ValueError as e:
        log.warning("mastodon_client_skipped", error=str(e))
        return None


def _make_clients(dry_run: bool, only: set[str] | None = None) -> tuple:
    """Create platform clients. Returns (linkedin, bluesky, mastodon).

    When *only* is provided, only the named platforms are initialised.
    """
    li = (
        _make_linkedin_client(dry_run)
        if only is None or "linkedin" in only
        else None
    )
    bs = (
        _make_bluesky_client(dry_run)
        if only is None or "bluesky" in only
        else None
    )
    md = (
        _make_mastodon_client(dry_run)
        if only is None or "mastodon" in only
        else None
    )
    return (li, bs, md)


@click.group(invoke_without_command=True)
@click.option(
    "--feed-url",
    default=None,
    help="Atom feed URL (default: $BLOG_FEED_URL or eve.gd feed).",
)
@click.option(
    "--state-file",
    default=None,
    help="Path to sync state JSON file.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview without actually posting.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force re-sync even if already synced.",
)
@click.option(
    "--json-logs",
    is_flag=True,
    help="Output structured JSON logs.",
)
@click.option(
    "--summary/--no-summary",
    default=True,
    show_default=True,
    help="Use LLM to generate a summary (default) or post full content.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable debug-level logging.",
)
@click.option(
    "--only",
    default=None,
    help=(
        "Comma-separated list of platforms to post to "
        "(e.g. --only linkedin, --only bluesky,mastodon)."
    ),
)
@click.pass_context
def cli(
    ctx,
    feed_url,
    state_file,
    dry_run,
    force,
    json_logs,
    summary,
    verbose,
    only,
):
    """Sync blog posts to LinkedIn, Bluesky, and Mastodon.

    With no subcommand, syncs all of today's unsynced posts.
    """
    configure_logging(
        json_logs=json_logs,
        verbosity=logging.DEBUG if verbose else logging.INFO,
    )
    load_dotenv()

    # Resolve feed URL after dotenv so BLOG_FEED_URL from .env is available
    if feed_url is None:
        feed_url = get_feed_url()

    # Parse --only into a set of platform names
    only_platforms = None
    if only:
        only_platforms = {p.strip().lower() for p in only.split(",")}
        valid = {"linkedin", "bluesky", "mastodon"}
        invalid = only_platforms - valid
        if invalid:
            raise click.BadParameter(
                f"Unknown platform(s): {', '.join(sorted(invalid))}. "
                f"Valid: {', '.join(sorted(valid))}",
                param_hint="'--only'",
            )

    ctx.ensure_object(dict)
    ctx.obj["feed_url"] = feed_url
    ctx.obj["dry_run"] = dry_run
    ctx.obj["force"] = force
    ctx.obj["summary"] = summary
    ctx.obj["only"] = only_platforms
    ctx.obj["tracker"] = SyncTracker(state_file=state_file)

    # If no subcommand, run the default "today" sync
    if ctx.invoked_subcommand is None:
        ctx.invoke(today)


@cli.command()
@click.pass_context
def today(ctx):
    """Sync all posts published today that haven't been synced yet."""
    feed_url = ctx.obj["feed_url"]
    dry_run = ctx.obj["dry_run"]
    force = ctx.obj["force"]
    summary = ctx.obj["summary"]
    tracker = ctx.obj["tracker"]
    only = ctx.obj.get("only")
    li_client, bs_client, md_client = _make_clients(dry_run, only)

    posts = get_todays_posts(feed_url)

    if not posts:
        log.info("no_posts_today")
        return

    log.info("found_todays_posts", count=len(posts))

    synced_count = 0
    skipped_count = 0

    for post in posts:
        if tracker.is_synced(post.url) and not force:
            log.info("skipping_already_synced", title=post.title, url=post.url)
            skipped_count += 1
            continue
        result = sync_post(
            post,
            tracker,
            dry_run=dry_run,
            summary=summary,
            linkedin_client=li_client,
            bluesky_client=bs_client,
            mastodon_client=md_client,
        )
        if result.any_success or dry_run:
            synced_count += 1

    log.info("sync_complete", synced=synced_count, skipped=skipped_count)


@cli.command()
@click.argument("url_or_path")
@click.pass_context
def post(ctx, url_or_path):
    """Sync a specific post by its URL or local markdown file path."""
    dry_run = ctx.obj["dry_run"]
    force = ctx.obj["force"]
    tracker = ctx.obj["tracker"]

    # Detect whether argument is a local file or a URL
    if Path(url_or_path).is_file():
        try:
            found_post = parse_markdown_file(url_or_path)
        except (FileNotFoundError, ValueError) as e:
            log.error("markdown_parse_failed", error=str(e))
            raise SystemExit(1) from e
    else:
        feed_url = ctx.obj["feed_url"]
        found_post = get_post_by_url(url_or_path, feed_url)
        if not found_post:
            log.error("post_not_found_in_feed", url=url_or_path)
            raise SystemExit(1)

    if tracker.is_synced(found_post.url) and not force:
        log.info("post_already_synced", url=found_post.url)
        return

    if force and tracker.is_synced(found_post.url):
        log.info("force_resync", url=found_post.url)
        tracker.remove_record(found_post.url)

    summary = ctx.obj["summary"]
    only = ctx.obj.get("only")
    li_client, bs_client, md_client = _make_clients(dry_run, only)
    sync_post(
        found_post,
        tracker,
        dry_run=dry_run,
        summary=summary,
        linkedin_client=li_client,
        bluesky_client=bs_client,
        mastodon_client=md_client,
    )


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def file(ctx, path):
    """Sync a post from a local markdown file."""
    dry_run = ctx.obj["dry_run"]
    force = ctx.obj["force"]
    tracker = ctx.obj["tracker"]

    try:
        found_post = parse_markdown_file(path)
    except (FileNotFoundError, ValueError) as e:
        log.error("markdown_parse_failed", error=str(e))
        raise SystemExit(1) from e

    if tracker.is_synced(found_post.url) and not force:
        log.info("post_already_synced", url=found_post.url)
        return

    if force and tracker.is_synced(found_post.url):
        log.info("force_resync", url=found_post.url)
        tracker.remove_record(found_post.url)

    summary = ctx.obj["summary"]
    only = ctx.obj.get("only")
    li_client, bs_client, md_client = _make_clients(dry_run, only)
    sync_post(
        found_post,
        tracker,
        dry_run=dry_run,
        summary=summary,
        linkedin_client=li_client,
        bluesky_client=bs_client,
        mastodon_client=md_client,
    )


@cli.command("list")
@click.pass_context
def list_synced(ctx):
    """List all previously synced posts."""
    tracker = ctx.obj["tracker"]
    synced = tracker.get_synced_posts()

    if not synced:
        log.info("no_synced_posts")
        return

    log.info("listing_synced_posts", count=len(synced))
    for url, record in synced.items():
        log.info(
            "synced_post",
            title=record["post_title"],
            url=url,
            linkedin_urn=record["linkedin_post_urn"],
            bluesky_url=record.get("bluesky_post_url", ""),
            mastodon_url=record.get("mastodon_post_url", ""),
            synced_at=record["synced_at"],
        )


@cli.command()
@click.pass_context
def verify(ctx):
    """Verify API credentials for all configured platforms."""
    from linkedin_sync.linkedin_client import LinkedInClient

    results = {}

    # LinkedIn — uses /v2/userinfo
    try:
        li = LinkedInClient()
        profile = li.get_profile()
        name = profile.get("name", "unknown")
        results["linkedin"] = f"OK ({name})"
    except Exception as e:
        results["linkedin"] = f"FAILED: {e}"

    # Bluesky
    try:
        from linkedin_sync.bluesky_client import BlueskyClient

        bs = BlueskyClient()
        results["bluesky"] = f"OK ({bs.handle})"
    except Exception as e:
        results["bluesky"] = f"FAILED: {e}"

    # Mastodon
    try:
        from linkedin_sync.mastodon_client import MastodonClient

        MastodonClient()
        results["mastodon"] = "OK"
    except Exception as e:
        results["mastodon"] = f"FAILED: {e}"

    for platform, status in results.items():
        log.info("verify_result", platform=platform, status=status)


@cli.command("image-check")
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def image_check(ctx, path):
    """Check and resize images referenced in a local markdown file.

    Finds all locally-referenced images, checks their dimensions,
    and resizes any that exceed 1200x630 (preserving aspect ratio).
    """
    from linkedin_sync.image_checker import extract_image_paths, resize_image

    dry_run = ctx.obj["dry_run"]

    try:
        image_paths = extract_image_paths(path)
    except FileNotFoundError as e:
        log.error("markdown_parse_failed", error=str(e))
        raise SystemExit(1) from e

    if not image_paths:
        log.info("no_images_found", file=path)
        return

    log.info("images_found", file=path, count=len(image_paths))

    for img_path in image_paths:
        if not img_path.is_file():
            log.warning("image_not_found", path=str(img_path))
            continue

        if dry_run:
            from PIL import Image

            img = Image.open(img_path)
            w, h = img.size
            log.info(
                "would_check_image",
                path=str(img_path),
                size=f"{w}x{h}",
                file_size_kb=f"{img_path.stat().st_size / 1024:.0f}",
            )
            continue

        resize_image(img_path)


@cli.command()
@click.argument("message")
@click.pass_context
def single(ctx, message):
    """Post an ad-hoc message to all social networks.

    The message is posted as-is. If it contains a URL, a link card
    embed is created on platforms that support them (LinkedIn and
    Bluesky). Mastodon generates its own link previews automatically.

    Example:

        linkedin-sync single "Had a great day https://example.com"
    """
    dry_run = ctx.obj["dry_run"]
    only = ctx.obj.get("only")
    li_client, bs_client, md_client = _make_clients(dry_run, only)

    # Extract local image path (if any) and clean it from the message
    # Record the character position before cleaning for chunk mapping
    image_match = _IMAGE_PATH_RE.search(message)
    image_char_pos = image_match.start() if image_match else 0
    original_len = len(message)
    clean_message, image_path = _extract_local_image(message)

    if image_path:
        log.info("local_image_detected", image_path=image_path)

    # Use the cleaned message (without image path) for posting
    message = clean_message

    # Extract URLs from the message for link card embeds
    url_matches = _URL_RE.findall(message)
    link_url = url_matches[-1] if url_matches else None

    # Split message into chunks for platforms with lower limits
    from linkedin_sync.bluesky_client import MAX_POST_LENGTH as BS_MAX
    from linkedin_sync.mastodon_client import DEFAULT_MAX_LENGTH as MD_MAX

    bs_chunks = split_message(message, BS_MAX)
    md_chunks = split_message(message, MD_MAX)

    # Determine which chunk the image belongs to for each platform
    bs_image_idx = _image_chunk_index(
        image_char_pos, original_len, len(bs_chunks)
    )
    md_image_idx = _image_chunk_index(
        image_char_pos, original_len, len(md_chunks)
    )

    if dry_run:
        log.info(
            "dry_run_single",
            message=message,
            link_url=link_url,
            image_path=image_path,
            platforms=_platform_names(li_client, bs_client, md_client),
        )
        # LinkedIn: always a single post
        log.info(
            "dry_run_linkedin",
            length=len(message),
            posts=1,
            text=message,
            has_image=bool(image_path),
        )
        # Bluesky threading breakdown
        log.info(
            "dry_run_bluesky_threading",
            total_posts=len(bs_chunks),
            threaded=len(bs_chunks) > 1,
            image_chunk=bs_image_idx if image_path else None,
        )
        for i, chunk in enumerate(bs_chunks):
            log.info(
                "dry_run_bluesky_chunk",
                part=i + 1,
                total=len(bs_chunks),
                length=len(chunk),
                text=chunk,
            )
        # Mastodon threading breakdown
        log.info(
            "dry_run_mastodon_threading",
            total_posts=len(md_chunks),
            threaded=len(md_chunks) > 1,
            image_chunk=md_image_idx if image_path else None,
        )
        for i, chunk in enumerate(md_chunks):
            log.info(
                "dry_run_mastodon_chunk",
                part=i + 1,
                total=len(md_chunks),
                length=len(chunk),
                text=chunk,
            )
        return

    # --- LinkedIn ---
    if li_client:
        try:
            li_kwargs: dict = {"text": message}
            image_urn = None
            if image_path:
                try:
                    image_urn = li_client.upload_image(
                        image_path=image_path
                    )
                    li_kwargs["image_urn"] = image_urn
                except Exception as e:
                    log.warning(
                        "linkedin_image_upload_failed", error=str(e)
                    )
            if not image_urn and link_url:
                li_kwargs["article_url"] = link_url
            li_client.create_post(**li_kwargs)
            log.info("linkedin_single_posted")
        except Exception as e:
            log.error("linkedin_single_failed", error=str(e))

    # --- Bluesky ---
    if bs_client:
        try:
            if len(bs_chunks) > 1:
                bs_kwargs: dict = {}
                if link_url:
                    bs_kwargs["link_url"] = link_url
                if image_path:
                    bs_kwargs["image_path"] = image_path
                    bs_kwargs["image_chunk_index"] = bs_image_idx
                bs_client.create_thread(bs_chunks, **bs_kwargs)
                log.info(
                    "bluesky_thread_posted",
                    chunk_count=len(bs_chunks),
                )
            else:
                bs_kwargs = {"text": message}
                if link_url:
                    bs_kwargs["link_url"] = link_url
                if image_path:
                    bs_kwargs["image_path"] = image_path
                bs_client.create_post(**bs_kwargs)
                log.info("bluesky_single_posted")
        except Exception as e:
            log.error("bluesky_single_failed", error=str(e))

    # --- Mastodon ---
    if md_client:
        try:
            if len(md_chunks) > 1:
                md_kwargs: dict = {}
                if image_path:
                    md_kwargs["image_path"] = image_path
                    md_kwargs["image_chunk_index"] = md_image_idx
                md_client.create_thread(md_chunks, **md_kwargs)
                log.info(
                    "mastodon_thread_posted",
                    chunk_count=len(md_chunks),
                )
            else:
                md_kwargs = {"text": message}
                if image_path:
                    md_kwargs["image_path"] = image_path
                md_client.create_post(**md_kwargs)
                log.info("mastodon_single_posted")
        except Exception as e:
            log.error("mastodon_single_failed", error=str(e))


def _platform_names(li, bs, md) -> list[str]:
    """Return a list of active platform names for logging."""
    names = []
    if li:
        names.append("linkedin")
    if bs:
        names.append("bluesky")
    if md:
        names.append("mastodon")
    return names


if __name__ == "__main__":
    cli()
