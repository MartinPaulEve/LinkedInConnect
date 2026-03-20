#!/usr/bin/env python3
"""Sync blog posts from eve.gd to LinkedIn."""

import os
import sys

import click
from dotenv import load_dotenv

from feed_parser import parse_feed, get_todays_posts, get_post_by_url, FEED_URL
from formatter import format_for_linkedin
from linkedin_client import LinkedInClient
from sync_tracker import SyncTracker


def sync_post(post, client: LinkedInClient, tracker: SyncTracker, dry_run: bool = False) -> bool:
    """Sync a single blog post to LinkedIn. Returns True on success."""
    click.echo(f"\n--- Syncing: {post.title}")
    click.echo(f"    URL: {post.url}")
    click.echo(f"    Published: {post.published.strftime('%Y-%m-%d %H:%M')}")

    if post.featured_image_url:
        click.echo(f"    Featured image: {post.featured_image_url}")
    if post.doi:
        click.echo(f"    DOI: {post.doi}")

    # Format the post content for LinkedIn
    linkedin_text = format_for_linkedin(
        title=post.title,
        content_html=post.content_html,
        post_url=post.url,
        doi=post.doi,
        tags=post.tags,
    )

    if dry_run:
        click.echo(f"\n    [DRY RUN] Would post to LinkedIn:")
        click.echo(f"    {'='*60}")
        for line in linkedin_text.split("\n"):
            click.echo(f"    {line}")
        click.echo(f"    {'='*60}")
        click.echo(f"    Character count: {len(linkedin_text)}")
        return True

    # Upload featured image if available
    image_urn = None
    if post.featured_image_url:
        try:
            click.echo("    Uploading featured image...")
            image_urn = client.upload_image(image_url=post.featured_image_url)
            click.echo(f"    Image uploaded: {image_urn}")
        except Exception as e:
            click.echo(f"    WARNING: Failed to upload image: {e}", err=True)
            click.echo("    Continuing without image...")

    # Create the LinkedIn post
    try:
        click.echo("    Creating LinkedIn post...")
        post_urn = client.create_post(
            text=linkedin_text,
            image_urn=image_urn,
            image_alt_text=f"Featured image for: {post.title}",
        )
        click.echo(f"    Posted successfully! URN: {post_urn}")
    except Exception as e:
        click.echo(f"    ERROR: Failed to create LinkedIn post: {e}", err=True)
        return False

    # Record the sync
    tracker.mark_synced(
        post_url=post.url,
        post_title=post.title,
        linkedin_post_urn=post_urn,
        post_published=post.published,
    )
    click.echo("    Sync recorded.")
    return True


def _make_client(dry_run: bool) -> LinkedInClient | None:
    """Create a LinkedIn client, or None for dry-run without credentials."""
    if dry_run and not os.environ.get("LINKEDIN_ACCESS_TOKEN"):
        return None
    try:
        return LinkedInClient()
    except ValueError as e:
        click.echo(f"ERROR: {e}", err=True)
        click.echo("\nRun 'linkedin-oauth' or 'python oauth_helper.py' to set up authentication.", err=True)
        click.echo("See SETUP.md for detailed instructions.", err=True)
        raise SystemExit(1)


@click.group(invoke_without_command=True)
@click.option("--feed-url", default=FEED_URL, show_default=True, help="Atom feed URL.")
@click.option("--state-file", default=None, help="Path to sync state JSON file.")
@click.option("--dry-run", is_flag=True, help="Show what would be posted without actually posting.")
@click.option("--force", is_flag=True, help="Force re-sync even if already synced.")
@click.pass_context
def cli(ctx, feed_url, state_file, dry_run, force):
    """Sync blog posts from eve.gd to LinkedIn.

    With no subcommand, syncs all posts published today that haven't been synced yet.
    """
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

    click.echo(f"Fetching feed: {feed_url}")
    posts = get_todays_posts(feed_url)

    if not posts:
        click.echo("No posts published today found in the feed.")
        return

    click.echo(f"Found {len(posts)} post(s) published today.")

    synced_count = 0
    skipped_count = 0

    for post in posts:
        if tracker.is_synced(post.url) and not force:
            click.echo(f"  Skipping (already synced): {post.title}")
            skipped_count += 1
            continue
        if sync_post(post, client, tracker, dry_run=dry_run):
            synced_count += 1

    click.echo(f"\nDone. Synced: {synced_count}, Skipped: {skipped_count}")


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
        click.echo(f"Post already synced: {url}")
        click.echo("Use --force to re-sync.")
        return

    if force and tracker.is_synced(url):
        click.echo(f"Force re-sync: removing existing sync record for {url}")
        tracker.remove_record(url)

    client = _make_client(dry_run)

    click.echo(f"Fetching feed: {feed_url}")
    found_post = get_post_by_url(url, feed_url)

    if not found_post:
        click.echo(f"Post not found in feed: {url}", err=True)
        click.echo("Make sure the URL matches exactly as it appears in the Atom feed.", err=True)
        raise SystemExit(1)

    sync_post(found_post, client, tracker, dry_run=dry_run)


@cli.command("list")
@click.pass_context
def list_synced(ctx):
    """List all previously synced posts."""
    tracker = ctx.obj["tracker"]
    synced = tracker.get_synced_posts()

    if not synced:
        click.echo("No posts have been synced yet.")
        return

    click.echo(f"Synced posts ({len(synced)}):\n")
    for url, record in synced.items():
        click.echo(f"  {record['post_title']}")
        click.echo(f"    URL: {url}")
        click.echo(f"    LinkedIn: {record['linkedin_post_urn']}")
        click.echo(f"    Synced at: {record['synced_at']}")
        click.echo()


if __name__ == "__main__":
    cli()
