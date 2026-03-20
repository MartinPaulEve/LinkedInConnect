#!/usr/bin/env python3
"""Sync blog posts from eve.gd to LinkedIn.

Usage:
    # Sync all posts published today that haven't been synced yet
    python sync.py

    # Sync a specific post by URL
    python sync.py --url https://eve.gd/2025/03/17/institutional-stupidity/

    # Force re-sync a post (even if already synced)
    python sync.py --url https://eve.gd/2025/03/17/institutional-stupidity/ --force

    # Dry run (show what would be posted without actually posting)
    python sync.py --dry-run

    # List all synced posts
    python sync.py --list

    # Use a custom feed URL
    python sync.py --feed-url https://eve.gd/feed/feed.atom

Environment variables (or .env file):
    LINKEDIN_ACCESS_TOKEN  - OAuth2 access token
    LINKEDIN_PERSON_URN    - Your LinkedIn person URN (urn:li:person:XXXXX)
    SYNC_STATE_FILE        - Path to sync state JSON (optional)
"""

import argparse
import sys
import os

from dotenv import load_dotenv

from feed_parser import parse_feed, get_todays_posts, get_post_by_url, FEED_URL
from formatter import format_for_linkedin
from linkedin_client import LinkedInClient
from sync_tracker import SyncTracker


def sync_post(post, client: LinkedInClient, tracker: SyncTracker, dry_run: bool = False) -> bool:
    """Sync a single blog post to LinkedIn. Returns True on success."""
    print(f"\n--- Syncing: {post.title}")
    print(f"    URL: {post.url}")
    print(f"    Published: {post.published.strftime('%Y-%m-%d %H:%M')}")

    if post.featured_image_url:
        print(f"    Featured image: {post.featured_image_url}")
    if post.doi:
        print(f"    DOI: {post.doi}")

    # Format the post content for LinkedIn
    linkedin_text = format_for_linkedin(
        title=post.title,
        content_html=post.content_html,
        post_url=post.url,
        doi=post.doi,
        tags=post.tags,
    )

    if dry_run:
        print(f"\n    [DRY RUN] Would post to LinkedIn:")
        print(f"    {'='*60}")
        for line in linkedin_text.split("\n"):
            print(f"    {line}")
        print(f"    {'='*60}")
        print(f"    Character count: {len(linkedin_text)}")
        return True

    # Upload featured image if available
    image_urn = None
    if post.featured_image_url:
        try:
            print(f"    Uploading featured image...")
            image_urn = client.upload_image(image_url=post.featured_image_url)
            print(f"    Image uploaded: {image_urn}")
        except Exception as e:
            print(f"    WARNING: Failed to upload image: {e}")
            print(f"    Continuing without image...")

    # Create the LinkedIn post
    try:
        print(f"    Creating LinkedIn post...")
        post_urn = client.create_post(
            text=linkedin_text,
            image_urn=image_urn,
            image_alt_text=f"Featured image for: {post.title}",
        )
        print(f"    Posted successfully! URN: {post_urn}")
    except Exception as e:
        print(f"    ERROR: Failed to create LinkedIn post: {e}")
        return False

    # Record the sync
    tracker.mark_synced(
        post_url=post.url,
        post_title=post.title,
        linkedin_post_urn=post_urn,
        post_published=post.published,
    )
    print(f"    Sync recorded.")
    return True


def cmd_sync_today(args, client: LinkedInClient, tracker: SyncTracker):
    """Sync all of today's unsynced posts."""
    print(f"Fetching feed: {args.feed_url}")
    posts = get_todays_posts(args.feed_url)

    if not posts:
        print("No posts published today found in the feed.")
        return

    print(f"Found {len(posts)} post(s) published today.")

    synced_count = 0
    skipped_count = 0

    for post in posts:
        if tracker.is_synced(post.url) and not args.force:
            print(f"  Skipping (already synced): {post.title}")
            skipped_count += 1
            continue
        if sync_post(post, client, tracker, dry_run=args.dry_run):
            synced_count += 1

    print(f"\nDone. Synced: {synced_count}, Skipped: {skipped_count}")


def cmd_sync_url(args, client: LinkedInClient, tracker: SyncTracker):
    """Sync a specific post by URL."""
    url = args.url

    if tracker.is_synced(url) and not args.force:
        print(f"Post already synced: {url}")
        print("Use --force to re-sync.")
        return

    if args.force and tracker.is_synced(url):
        print(f"Force re-sync: removing existing sync record for {url}")
        tracker.remove_record(url)

    print(f"Fetching feed: {args.feed_url}")
    post = get_post_by_url(url, args.feed_url)

    if not post:
        print(f"Post not found in feed: {url}")
        print("Make sure the URL matches exactly as it appears in the Atom feed.")
        return

    sync_post(post, client, tracker, dry_run=args.dry_run)


def cmd_list(args, tracker: SyncTracker):
    """List all synced posts."""
    synced = tracker.get_synced_posts()
    if not synced:
        print("No posts have been synced yet.")
        return

    print(f"Synced posts ({len(synced)}):\n")
    for url, record in synced.items():
        print(f"  {record['post_title']}")
        print(f"    URL: {url}")
        print(f"    LinkedIn: {record['linkedin_post_urn']}")
        print(f"    Synced at: {record['synced_at']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Sync blog posts from eve.gd to LinkedIn",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--url",
        help="Sync a specific post by its URL",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-sync even if already synced",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be posted without actually posting",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_synced",
        help="List all synced posts",
    )
    parser.add_argument(
        "--feed-url",
        default=FEED_URL,
        help=f"Atom feed URL (default: {FEED_URL})",
    )
    parser.add_argument(
        "--state-file",
        help="Path to sync state JSON file",
    )

    args = parser.parse_args()

    # Load .env file
    load_dotenv()

    # Initialize tracker
    tracker = SyncTracker(state_file=args.state_file)

    # List command doesn't need LinkedIn client
    if args.list_synced:
        cmd_list(args, tracker)
        return

    # For dry-run, create a dummy client if credentials aren't set
    if args.dry_run and not os.environ.get("LINKEDIN_ACCESS_TOKEN"):
        client = None
    else:
        try:
            client = LinkedInClient()
        except ValueError as e:
            print(f"ERROR: {e}")
            print("\nRun 'python oauth_helper.py' to set up authentication.")
            print("See SETUP.md for detailed instructions.")
            sys.exit(1)

    if args.url:
        cmd_sync_url(args, client, tracker)
    else:
        cmd_sync_today(args, client, tracker)


if __name__ == "__main__":
    main()
