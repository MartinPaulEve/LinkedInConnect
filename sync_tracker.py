"""Track which blog posts have been synced to LinkedIn."""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DEFAULT_STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sync_state.json"
)


@dataclass
class SyncRecord:
    """Record of a single synced post."""
    post_url: str
    post_title: str
    linkedin_post_urn: str
    synced_at: str  # ISO format
    post_published: str  # ISO format


class SyncTracker:
    """Tracks which posts have been synced to LinkedIn using a JSON file."""

    def __init__(self, state_file: str = None):
        self.state_file = state_file or os.environ.get(
            "SYNC_STATE_FILE", DEFAULT_STATE_FILE
        )
        self._state = self._load()

    def _load(self) -> dict:
        """Load state from the JSON file."""
        if Path(self.state_file).exists():
            with open(self.state_file, "r") as f:
                return json.load(f)
        return {"synced_posts": {}}

    def _save(self):
        """Save state to the JSON file."""
        Path(self.state_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self._state, f, indent=2)

    def is_synced(self, post_url: str) -> bool:
        """Check if a post has already been synced."""
        return post_url in self._state.get("synced_posts", {})

    def mark_synced(
        self,
        post_url: str,
        post_title: str,
        linkedin_post_urn: str,
        post_published: datetime,
    ):
        """Mark a post as synced."""
        record = SyncRecord(
            post_url=post_url,
            post_title=post_title,
            linkedin_post_urn=linkedin_post_urn,
            synced_at=datetime.now(timezone.utc).isoformat(),
            post_published=post_published.isoformat(),
        )
        self._state.setdefault("synced_posts", {})[post_url] = asdict(record)
        self._save()

    def get_synced_posts(self) -> dict:
        """Return all synced post records."""
        return self._state.get("synced_posts", {})

    def get_record(self, post_url: str) -> Optional[dict]:
        """Get the sync record for a specific post."""
        return self._state.get("synced_posts", {}).get(post_url)

    def remove_record(self, post_url: str) -> bool:
        """Remove a sync record (useful for re-syncing)."""
        if post_url in self._state.get("synced_posts", {}):
            del self._state["synced_posts"][post_url]
            self._save()
            return True
        return False
