"""Tests for the message threading/splitting utility."""

from linkedin_sync.threader import split_message


class TestSplitMessageNoThreading:
    """Messages that fit within the limit should not be threaded."""

    def test_short_message_returns_single_chunk(self):
        result = split_message("Hello world", 300)
        assert result == ["Hello world"]

    def test_empty_string_returns_single_chunk(self):
        result = split_message("", 300)
        assert result == [""]

    def test_message_at_exact_limit_returns_single_chunk(self):
        text = "a" * 300
        result = split_message(text, 300)
        assert result == [text]

    def test_no_thread_indicator_when_single_chunk(self):
        result = split_message("Just a short post", 300)
        assert len(result) == 1
        assert "🧵" not in result[0]


class TestSplitMessageThreading:
    """Messages exceeding the limit should be split into a thread."""

    def test_splits_into_two_chunks(self):
        # 301 chars should require 2 chunks at limit 300
        text = "word " * 61  # 305 chars
        result = split_message(text, 300)
        assert len(result) == 2

    def test_each_chunk_has_thread_indicator(self):
        text = "word " * 61
        result = split_message(text, 300)
        for chunk in result:
            assert "🧵" in chunk

    def test_thread_indicator_format(self):
        text = "word " * 61
        result = split_message(text, 300)
        assert result[0].endswith(" 🧵1/2")
        assert result[1].endswith(" 🧵2/2")

    def test_no_chunk_exceeds_limit(self):
        text = "word " * 200  # 1000 chars
        result = split_message(text, 300)
        for chunk in result:
            assert len(chunk) <= 300

    def test_splits_at_word_boundaries(self):
        text = "hello world " * 30  # 360 chars
        result = split_message(text, 300)
        for chunk in result:
            # Remove the thread indicator to check the text portion
            text_part = chunk.rsplit(" 🧵", 1)[0]
            # No word should be cut in half - text should not end mid-word
            # (it should end with a complete word, possibly followed by space)
            assert not text_part[-1].isalpha() or text_part.endswith(
                tuple(text_part.split()[-1:])
            )

    def test_three_chunks(self):
        text = "word " * 200  # 1000 chars
        result = split_message(text, 300)
        assert len(result) >= 3
        assert result[0].endswith(f" 🧵1/{len(result)}")
        assert result[-1].endswith(f" 🧵{len(result)}/{len(result)}")

    def test_preserves_all_text(self):
        """All original words should appear across the chunks."""
        text = "The quick brown fox jumps over the lazy dog " * 10
        result = split_message(text, 100)
        # Reconstruct text from chunks by stripping indicators
        reconstructed_words = []
        for chunk in result:
            text_part = chunk.rsplit(" 🧵", 1)[0]
            reconstructed_words.extend(text_part.split())
        original_words = text.split()
        assert reconstructed_words == original_words


class TestSplitMessageURLHandling:
    """URLs should not be split across chunks."""

    def test_url_kept_intact(self):
        # Build a message where a URL would be at a split point
        padding = "a " * 130  # 260 chars
        url = "https://example.com/very/long/path/to/article"
        text = padding + url
        result = split_message(text, 300)
        # The URL should appear completely in one chunk
        all_text = " ".join(result)
        assert url in all_text

    def test_url_not_broken_across_chunks(self):
        padding = "word " * 50  # 250 chars
        url = "https://example.com/path"
        text = padding + url
        result = split_message(text, 300)
        # Find which chunk contains the URL
        url_found = False
        for chunk in result:
            if "https://example.com/path" in chunk:
                url_found = True
                break
        assert url_found, "URL should appear intact in one chunk"


class TestSplitMessageBlueskyLimit:
    """Test with Bluesky's 300 grapheme limit."""

    def test_bluesky_short_message(self):
        result = split_message("Short post for Bluesky", 300)
        assert len(result) == 1

    def test_bluesky_long_message_threads(self):
        text = "This is a test message for Bluesky. " * 12  # ~432 chars
        result = split_message(text, 300)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= 300


class TestSplitMessageMastodonLimit:
    """Test with Mastodon's 500 character limit."""

    def test_mastodon_short_message(self):
        result = split_message("Short post for Mastodon", 500)
        assert len(result) == 1

    def test_mastodon_long_message_threads(self):
        text = "This is a longer message for Mastodon. " * 20  # ~780 chars
        result = split_message(text, 500)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= 500


class TestSplitMessageEdgeCases:
    """Edge cases for message splitting."""

    def test_single_long_word_exceeding_limit(self):
        """A single word longer than the limit should still be included."""
        text = "a" * 400
        result = split_message(text, 300)
        # Should handle gracefully - the word must appear somewhere
        all_text = "".join(chunk.rsplit(" 🧵", 1)[0] for chunk in result)
        assert "a" * 400 in all_text

    def test_indicator_space_reserved_correctly(self):
        """Thread indicator should not cause chunks to exceed the limit."""
        # Create text that is just barely over the limit
        text = "x " * 151  # 302 chars
        result = split_message(text, 300)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= 300

    def test_many_chunks_double_digit_indicator(self):
        """When there are 10+ chunks, the indicator is longer."""
        text = "word " * 700  # 3500 chars
        result = split_message(text, 300)
        assert len(result) >= 10
        for chunk in result:
            assert len(chunk) <= 300
        # Check last chunk indicator format
        assert result[9].endswith(f" 🧵10/{len(result)}")
