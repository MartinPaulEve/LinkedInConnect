"""Track which blog posts have been synced to LinkedIn."""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from linkedin_sync.logging_config import get_logger

log = get_logger(__name__)

DEFAULT_STATE_FILE = os.path.join(os.getcwd(), "sync_state.json")


@dataclass
class SyncRecord:
    """Record of a single synced post."""

    post_url: str
    post_title: str
    linkedin_post_urn: str
    synced_at: str  # ISO format
    post_published: str  # ISO format
    bluesky_post_url: str = ""
    mastodon_post_url: str = ""


class SyncTracker:
    """Tracks which posts have been synced to LinkedIn using a JSON file."""

    def __init__(self, state_file: str | None = None):
        self.state_file = state_file or os.environ.get(
            "SYNC_STATE_FILE", DEFAULT_STATE_FILE
        )
        self._state = self._load()
        log.info(
            "sync_tracker_initialized",
            state_file=self.state_file,
            synced_count=len(self.get_synced_posts()),
        )

    def _load(self) -> dict:
        """Load state from the JSON file."""
        if Path(self.state_file).exists():
            with open(self.state_file) as f:
                data = json.load(f)
            log.debug("state_loaded", path=self.state_file)
            return data
        log.debug("state_file_not_found_using_empty", path=self.state_file)
        return {"synced_posts": {}}

    def _save(self):
        """Save state to the JSON file."""
        Path(self.state_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self._state, f, indent=2)
        log.debug("state_saved", path=self.state_file)

    def is_synced(self, post_url: str) -> bool:
        """Check if a post has already been synced."""
        synced = post_url in self._state.get("synced_posts", {})
        log.debug("is_synced_check", post_url=post_url, synced=synced)
        return synced

    def mark_synced(
        self,
        post_url: str,
        post_title: str,
        linkedin_post_urn: str,
        post_published: datetime,
        bluesky_post_url: str = "",
        mastodon_post_url: str = "",
    ):
        """Mark a post as synced."""
        record = SyncRecord(
            post_url=post_url,
            post_title=post_title,
            linkedin_post_urn=linkedin_post_urn,
            synced_at=datetime.now(timezone.utc).isoformat(),
            post_published=post_published.isoformat(),
            bluesky_post_url=bluesky_post_url,
            mastodon_post_url=mastodon_post_url,
        )
        self._state.setdefault("synced_posts", {})[post_url] = asdict(record)
        self._save()
        log.info(
            "post_marked_synced",
            post_url=post_url,
            linkedin_urn=linkedin_post_urn,
            bluesky_url=bluesky_post_url,
            mastodon_url=mastodon_post_url,
        )

    def get_synced_posts(self) -> dict:
        """Return all synced post records."""
        return self._state.get("synced_posts", {})

    def get_record(self, post_url: str) -> dict | None:
        """Get the sync record for a specific post."""
        return self._state.get("synced_posts", {}).get(post_url)

    def remove_record(self, post_url: str) -> bool:
        """Remove a sync record (useful for re-syncing)."""
        if post_url in self._state.get("synced_posts", {}):
            del self._state["synced_posts"][post_url]
            self._save()
            log.info("sync_record_removed", post_url=post_url)
            return True
        log.warning("sync_record_not_found", post_url=post_url)
        return False
