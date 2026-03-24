"""Tests for ellipsis support in threaded messages."""

from linkedin_sync.sync import _resolve_ellipsis_flag
from linkedin_sync.threader import split_message


class TestEllipsisDefault:
    """By default, ellipses should appear on continued posts."""

    def test_end_ellipsis_on_non_final_chunks(self):
        text = "word " * 61  # 305 chars, needs 2 chunks at 300
        result = split_message(text, 300)
        assert len(result) == 2
        # First chunk (not the last) should have "..." before indicator
        text_part = result[0].rsplit(" 🧵", 1)[0]
        assert text_part.endswith("...")

    def test_start_ellipsis_on_non_first_chunks(self):
        text = "word " * 61
        result = split_message(text, 300)
        assert len(result) == 2
        # Second chunk should start with "..."
        assert result[1].startswith("...")

    def test_no_ellipsis_on_single_chunk(self):
        result = split_message("Short post", 300)
        assert len(result) == 1
        assert "..." not in result[0]

    def test_first_chunk_no_start_ellipsis(self):
        text = "word " * 61
        result = split_message(text, 300)
        assert not result[0].startswith("...")

    def test_last_chunk_no_end_ellipsis(self):
        text = "word " * 61
        result = split_message(text, 300)
        text_part = result[-1].rsplit(" 🧵", 1)[0]
        assert not text_part.endswith("...")

    def test_three_chunks_middle_has_both(self):
        text = "word " * 200  # 1000 chars
        result = split_message(text, 300)
        assert len(result) >= 3
        # Middle chunk should start with ... and end with ...
        mid = result[1]
        assert mid.startswith("...")
        text_part = mid.rsplit(" 🧵", 1)[0]
        assert text_part.endswith("...")

    def test_no_chunk_exceeds_limit_with_ellipses(self):
        text = "word " * 200
        result = split_message(text, 300)
        for chunk in result:
            assert len(chunk) <= 300

    def test_all_words_preserved_with_ellipses(self):
        text = "The quick brown fox jumps over the lazy dog " * 10
        result = split_message(text, 100)
        reconstructed_words = []
        for chunk in result:
            text_part = chunk.rsplit(" 🧵", 1)[0]
            # Strip ellipses
            text_part = text_part.strip(".")
            text_part = text_part.strip()
            reconstructed_words.extend(text_part.split())
        original_words = text.split()
        assert reconstructed_words == original_words


class TestEllipsisDisabled:
    """Ellipses can be disabled entirely."""

    def test_no_ellipsis_when_disabled(self):
        text = "word " * 61
        result = split_message(
            text, 300, start_ellipsis=False, end_ellipsis=False
        )
        assert len(result) == 2
        text_part = result[0].rsplit(" 🧵", 1)[0]
        assert not text_part.endswith("...")
        assert not result[1].startswith("...")


class TestEndEllipsisOnly:
    """Only end ellipses enabled."""

    def test_end_ellipsis_no_start(self):
        text = "word " * 61
        result = split_message(
            text, 300, start_ellipsis=False, end_ellipsis=True
        )
        assert len(result) == 2
        text_part = result[0].rsplit(" 🧵", 1)[0]
        assert text_part.endswith("...")
        assert not result[1].startswith("...")


class TestStartEllipsisOnly:
    """Only start ellipses enabled."""

    def test_start_ellipsis_no_end(self):
        text = "word " * 61
        result = split_message(
            text, 300, start_ellipsis=True, end_ellipsis=False
        )
        assert len(result) == 2
        text_part = result[0].rsplit(" 🧵", 1)[0]
        assert not text_part.endswith("...")
        assert result[1].startswith("...")


class TestResolveEllipsisFlag:
    """Test priority resolution: built-in < .env < CLI."""

    def test_default_is_true(self):
        assert _resolve_ellipsis_flag("THREAD_START_ELLIPSES", False, False)

    def test_cli_disable_overrides_all(self):
        assert not _resolve_ellipsis_flag("THREAD_START_ELLIPSES", True, False)

    def test_cli_disable_all_overrides(self):
        assert not _resolve_ellipsis_flag("THREAD_START_ELLIPSES", False, True)

    def test_env_specific_false(self, monkeypatch):
        monkeypatch.setenv("THREAD_START_ELLIPSES", "false")
        assert not _resolve_ellipsis_flag(
            "THREAD_START_ELLIPSES", False, False
        )

    def test_env_specific_true(self, monkeypatch):
        monkeypatch.setenv("THREAD_START_ELLIPSES", "true")
        assert _resolve_ellipsis_flag("THREAD_START_ELLIPSES", False, False)

    def test_env_blanket_false(self, monkeypatch):
        monkeypatch.setenv("THREAD_ELLIPSES", "false")
        assert not _resolve_ellipsis_flag(
            "THREAD_START_ELLIPSES", False, False
        )

    def test_env_specific_overrides_blanket(self, monkeypatch):
        monkeypatch.setenv("THREAD_ELLIPSES", "false")
        monkeypatch.setenv("THREAD_START_ELLIPSES", "true")
        assert _resolve_ellipsis_flag("THREAD_START_ELLIPSES", False, False)

    def test_cli_overrides_env_true(self, monkeypatch):
        monkeypatch.setenv("THREAD_START_ELLIPSES", "true")
        assert not _resolve_ellipsis_flag("THREAD_START_ELLIPSES", True, False)

    def test_env_values_0_no(self, monkeypatch):
        monkeypatch.setenv("THREAD_END_ELLIPSES", "0")
        assert not _resolve_ellipsis_flag("THREAD_END_ELLIPSES", False, False)
        monkeypatch.setenv("THREAD_END_ELLIPSES", "no")
        assert not _resolve_ellipsis_flag("THREAD_END_ELLIPSES", False, False)

    def test_env_values_1_yes(self, monkeypatch):
        monkeypatch.setenv("THREAD_END_ELLIPSES", "1")
        assert _resolve_ellipsis_flag("THREAD_END_ELLIPSES", False, False)
        monkeypatch.setenv("THREAD_END_ELLIPSES", "yes")
        assert _resolve_ellipsis_flag("THREAD_END_ELLIPSES", False, False)
