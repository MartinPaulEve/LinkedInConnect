#!/usr/bin/env python3
"""Sync blog posts from eve.gd to LinkedIn."""

import logging
import os

import click
from dotenv import load_dotenv

from feed_parser import (
    FEED_URL,
    get_post_by_url,
    get_todays_posts,
    parse_markdown_file,
)
from formatter import format_for_linkedin
from linkedin_client import LinkedInClient
from logging_config import configure_logging, get_logger
from sync_tracker import SyncTracker

log = get_logger(__name__)


def sync_post(
    post, client: LinkedInClient, tracker: SyncTracker, dry_run: bool = False
) -> bool:
    """Sync a single blog post to LinkedIn. Returns True on success."""
    log.info(
        "sync_post_start",
        title=post.title,
        url=post.url,
        published=post.published.isoformat(),
        has_image=bool(post.featured_image_url),
        has_doi=bool(post.doi),
    )

    # Format the post content for LinkedIn
    linkedin_text = format_for_linkedin(
        title=post.title,
        content_html=post.content_html,
        post_url=post.url,
        doi=post.doi,
        tags=post.tags,
    )

    if dry_run:
        log.info(
            "dry_run_preview",
            title=post.title,
            char_count=len(linkedin_text),
            text=linkedin_text,
        )
        return True

    # Upload featured image if available
    image_urn = None
    if post.featured_image_url:
        try:
            image_urn = client.upload_image(image_url=post.featured_image_url)
        except Exception as e:
            log.warning(
                "image_upload_failed",
                url=post.featured_image_url,
                error=str(e),
            )

    # Create the LinkedIn post
    try:
        post_urn = client.create_post(
            text=linkedin_text,
            image_urn=image_urn,
            image_alt_text=f"Featured image for: {post.title}",
        )
        log.info(
            "post_synced_successfully", title=post.title, linkedin_urn=post_urn
        )
    except Exception as e:
        log.error("post_creation_failed", title=post.title, error=str(e))
        return False

    # Record the sync
    tracker.mark_synced(
        post_url=post.url,
        post_title=post.title,
        linkedin_post_urn=post_urn,
        post_published=post.published,
    )
    return True


def _make_client(dry_run: bool) -> LinkedInClient | None:
    """Create a LinkedIn client, or None for dry-run without credentials."""
    if dry_run and not os.environ.get("LINKEDIN_ACCESS_TOKEN"):
        log.debug("skipping_client_creation_dry_run")
        return None
    try:
        return LinkedInClient()
    except ValueError as e:
        log.error("client_creation_failed", error=str(e))
        raise SystemExit(1) from e


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
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable debug-level logging.",
)
@click.pass_context
def cli(ctx, feed_url, state_file, dry_run, force, json_logs, verbose):
    """Sync blog posts from eve.gd to LinkedIn.

    With no subcommand, syncs all of today's unsynced posts.
    """
    configure_logging(
        json_logs=json_logs,
        verbosity=logging.DEBUG if verbose else logging.INFO,
    )
    load_dotenv()
    ctx.ensure_object(dict)
    ctx.obj["feed_url"] = feed_url
    ctx.obj["dry_run"] = dry_run
    ctx.obj["force"] = force
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
    tracker = ctx.obj["tracker"]
    client = _make_client(dry_run)

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
        if sync_post(post, client, tracker, dry_run=dry_run):
            synced_count += 1

    log.info("sync_complete", synced=synced_count, skipped=skipped_count)


@cli.command()
@click.argument("url")
@click.pass_context
def post(ctx, url):
    """Sync a specific post by its URL."""
    feed_url = ctx.obj["feed_url"]
    dry_run = ctx.obj["dry_run"]
    force = ctx.obj["force"]
    tracker = ctx.obj["tracker"]

    if tracker.is_synced(url) and not force:
        log.info("post_already_synced", url=url)
        return

    if force and tracker.is_synced(url):
        log.info("force_resync", url=url)
        tracker.remove_record(url)

    client = _make_client(dry_run)

    found_post = get_post_by_url(url, feed_url)

    if not found_post:
        log.error("post_not_found_in_feed", url=url)
        raise SystemExit(1)

    sync_post(found_post, client, tracker, dry_run=dry_run)


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

    client = _make_client(dry_run)
    sync_post(found_post, client, tracker, dry_run=dry_run)


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
            synced_at=record["synced_at"],
        )


if __name__ == "__main__":
    cli()
