#!/usr/bin/env python3
"""Sync blog posts from eve.gd to LinkedIn, Bluesky, and Mastodon."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import click
from dotenv import load_dotenv

from feed_parser import (
    FEED_URL,
    get_post_by_url,
    get_todays_posts,
    parse_markdown_file,
)
from formatter import format_for_linkedin
from logging_config import configure_logging, get_logger
from summarizer import summarize_post, summarize_post_short
from sync_tracker import SyncTracker

log = get_logger(__name__)


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
        from linkedin_client import LinkedInClient

        return LinkedInClient()
    except ValueError as e:
        log.warning("linkedin_client_skipped", error=str(e))
        return None


def _make_bluesky_client(dry_run: bool):
    """Create a Bluesky client, or None if not configured."""
    if dry_run and not os.environ.get("BLUESKY_HANDLE"):
        return None
    try:
        from bluesky_client import BlueskyClient

        return BlueskyClient()
    except ValueError as e:
        log.warning("bluesky_client_skipped", error=str(e))
        return None


def _make_mastodon_client(dry_run: bool):
    """Create a Mastodon client, or None if not configured."""
    if dry_run and not os.environ.get("MASTODON_ACCESS_TOKEN"):
        return None
    try:
        from mastodon_client import MastodonClient

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
    default=FEED_URL,
    show_default=True,
    help="Atom feed URL.",
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
    from linkedin_client import LinkedInClient

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
        from bluesky_client import BlueskyClient

        bs = BlueskyClient()
        results["bluesky"] = f"OK ({bs.handle})"
    except Exception as e:
        results["bluesky"] = f"FAILED: {e}"

    # Mastodon
    try:
        from mastodon_client import MastodonClient

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
    from image_checker import extract_image_paths, resize_image

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


if __name__ == "__main__":
    cli()
