"""Tests for sync_tracker module."""

import json
from datetime import datetime, timezone
from pathlib import Path

from sync_tracker import SyncTracker


class TestSyncTrackerInit:
    def test_creates_empty_state(self, tmp_state_file):
        tracker = SyncTracker(state_file=tmp_state_file)
        assert tracker.get_synced_posts() == {}

    def test_loads_existing_state(self, populated_state_file):
        tracker = SyncTracker(state_file=populated_state_file)
        posts = tracker.get_synced_posts()
        assert len(posts) == 1
        assert "https://eve.gd/2025/01/01/old-post/" in posts


class TestIsSynced:
    def test_unsynced_url(self, tmp_state_file):
        tracker = SyncTracker(state_file=tmp_state_file)
        assert tracker.is_synced("https://eve.gd/new/") is False

    def test_synced_url(self, populated_state_file):
        tracker = SyncTracker(state_file=populated_state_file)
        assert tracker.is_synced("https://eve.gd/2025/01/01/old-post/") is True

    def test_synced_url_not_present(self, populated_state_file):
        tracker = SyncTracker(state_file=populated_state_file)
        assert tracker.is_synced("https://eve.gd/other/") is False


class TestMarkSynced:
    def test_marks_and_persists(self, tmp_state_file):
        tracker = SyncTracker(state_file=tmp_state_file)
        published = datetime(2025, 3, 20, 10, 0, tzinfo=timezone.utc)
        tracker.mark_synced(
            post_url="https://eve.gd/new-post/",
            post_title="New Post",
            linkedin_post_urn="urn:li:share:9999",
            post_published=published,
        )
        assert tracker.is_synced("https://eve.gd/new-post/")

        # Reload from disk
        tracker2 = SyncTracker(state_file=tmp_state_file)
        assert tracker2.is_synced("https://eve.gd/new-post/")
        record = tracker2.get_record("https://eve.gd/new-post/")
        assert record["post_title"] == "New Post"
        assert record["linkedin_post_urn"] == "urn:li:share:9999"
        assert record["post_published"] == published.isoformat()

    def test_mark_multiple_posts(self, tmp_state_file):
        tracker = SyncTracker(state_file=tmp_state_file)
        dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        tracker.mark_synced("https://eve.gd/a/", "Post A", "urn:a", dt)
        tracker.mark_synced("https://eve.gd/b/", "Post B", "urn:b", dt)
        tracker.mark_synced("https://eve.gd/c/", "Post C", "urn:c", dt)
        assert len(tracker.get_synced_posts()) == 3

    def test_overwrite_existing(self, populated_state_file):
        tracker = SyncTracker(state_file=populated_state_file)
        dt = datetime(2025, 6, 1, tzinfo=timezone.utc)
        tracker.mark_synced(
            "https://eve.gd/2025/01/01/old-post/",
            "Old Post Updated",
            "urn:li:share:new",
            dt,
        )
        record = tracker.get_record("https://eve.gd/2025/01/01/old-post/")
        assert record["post_title"] == "Old Post Updated"
        assert record["linkedin_post_urn"] == "urn:li:share:new"


class TestGetRecord:
    def test_existing_record(self, populated_state_file):
        tracker = SyncTracker(state_file=populated_state_file)
        record = tracker.get_record("https://eve.gd/2025/01/01/old-post/")
        assert record is not None
        assert record["post_title"] == "Old Post"

    def test_missing_record(self, populated_state_file):
        tracker = SyncTracker(state_file=populated_state_file)
        assert tracker.get_record("https://eve.gd/nonexistent/") is None


class TestRemoveRecord:
    def test_remove_existing(self, populated_state_file):
        tracker = SyncTracker(state_file=populated_state_file)
        result = tracker.remove_record("https://eve.gd/2025/01/01/old-post/")
        assert result is True
        assert (
            tracker.is_synced("https://eve.gd/2025/01/01/old-post/") is False
        )

        # Verify persistence
        tracker2 = SyncTracker(state_file=populated_state_file)
        assert (
            tracker2.is_synced("https://eve.gd/2025/01/01/old-post/") is False
        )

    def test_remove_nonexistent(self, tmp_state_file):
        tracker = SyncTracker(state_file=tmp_state_file)
        result = tracker.remove_record("https://eve.gd/nope/")
        assert result is False


class TestStatePersistence:
    def test_state_file_is_valid_json(self, tmp_state_file):
        tracker = SyncTracker(state_file=tmp_state_file)
        dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        tracker.mark_synced("https://eve.gd/x/", "X", "urn:x", dt)

        with open(tmp_state_file) as f:
            data = json.load(f)
        assert "synced_posts" in data
        assert "https://eve.gd/x/" in data["synced_posts"]

    def test_creates_parent_directories(self, tmp_path):
        deep_path = str(tmp_path / "a" / "b" / "c" / "state.json")
        tracker = SyncTracker(state_file=deep_path)
        dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        tracker.mark_synced("https://eve.gd/x/", "X", "urn:x", dt)
        assert Path(deep_path).exists()
