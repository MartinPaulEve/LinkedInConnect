"""Message splitting utility for threading long posts on social media."""

import re

# Regex to find URLs in text (same pattern used in bluesky_client and sync)
_URL_RE = re.compile(r"https?://[^\s)<>]+")

ELLIPSIS = "..."


def split_message(
    text: str,
    max_length: int,
    start_ellipsis: bool = True,
    end_ellipsis: bool = True,
) -> list[str]:
    """Split a message into chunks suitable for threading.

    If the text fits within *max_length*, it is returned as a single-element
    list with **no** thread indicator.  Otherwise the text is split at word
    boundaries and each chunk receives a thread indicator suffix like
    ``" 🧵1/4"``.

    When threading occurs, continuation markers are added:

    - *end_ellipsis*: ``...`` is appended to every chunk except the last,
      just before the thread indicator.
    - *start_ellipsis*: ``...`` is prepended to every chunk except the first.

    Both default to ``True``.  The ellipsis characters are factored into the
    character budget so that no chunk exceeds *max_length*.

    URLs are treated as unsplittable tokens so they are never broken across
    chunks.
    """
    if len(text) <= max_length:
        return [text]

    # Tokenise into words, keeping URLs as single tokens
    tokens = _tokenise(text)

    # We don't know the total number of chunks yet, so we do an iterative
    # approach: estimate, split, check, re-split if indicator length changed.
    estimate = _estimate_chunk_count(
        tokens, max_length, start_ellipsis, end_ellipsis
    )
    chunks = _split_tokens(
        tokens, max_length, estimate, start_ellipsis, end_ellipsis
    )

    # If actual count differs from estimate, the indicator length may have
    # changed (e.g. "1/9" vs "1/10").  Re-split with corrected estimate.
    if len(chunks) != estimate:
        chunks = _split_tokens(
            tokens,
            max_length,
            len(chunks),
            start_ellipsis,
            end_ellipsis,
        )

    total = len(chunks)
    result = []
    for i, chunk in enumerate(chunks):
        parts = []

        # Start ellipsis on non-first chunks
        if start_ellipsis and i > 0:
            parts.append(ELLIPSIS)

        parts.append(chunk)

        # End ellipsis on non-last chunks
        if end_ellipsis and i < total - 1:
            parts.append(ELLIPSIS)

        text_portion = " ".join(parts)
        result.append(f"{text_portion} 🧵{i + 1}/{total}")

    return result


def _tokenise(text: str) -> list[str]:
    """Split text into word tokens, preserving URLs as single tokens."""
    tokens: list[str] = []
    last_end = 0
    for match in _URL_RE.finditer(text):
        start, end = match.span()
        # Add words before this URL
        if start > last_end:
            tokens.extend(text[last_end:start].split())
        tokens.append(match.group(0))
        last_end = end
    # Add remaining words after the last URL
    if last_end < len(text):
        tokens.extend(text[last_end:].split())
    return tokens


def _indicator_len(part: int, total: int) -> int:
    """Return the length of a thread indicator like ' 🧵1/4'."""
    # " 🧵" is 3 chars (space + emoji + nothing) + digits
    return len(f" 🧵{part}/{total}")


def _max_indicator_len(total: int) -> int:
    """Return the maximum indicator length for a given total."""
    # The last indicator is the longest: " 🧵{total}/{total}"
    return _indicator_len(total, total)


def _ellipsis_overhead(
    chunk_index: int,
    total: int,
    start_ellipsis: bool,
    end_ellipsis: bool,
) -> int:
    """Extra characters needed for ellipsis markers on a given chunk.

    Start ellipsis adds "... " (4 chars) and end ellipsis adds " ..."
    (4 chars).
    """
    overhead = 0
    if start_ellipsis and chunk_index > 0:
        overhead += len(ELLIPSIS) + 1  # "... " (ellipsis + space)
    if end_ellipsis and chunk_index < total - 1:
        overhead += len(ELLIPSIS) + 1  # " ..." (space + ellipsis)
    return overhead


def _max_ellipsis_overhead(
    total: int,
    start_ellipsis: bool,
    end_ellipsis: bool,
) -> int:
    """Worst-case ellipsis overhead (a middle chunk with both markers)."""
    if total <= 1:
        return 0
    # Middle chunks have both start and end ellipsis
    overhead = 0
    if start_ellipsis:
        overhead += len(ELLIPSIS) + 1
    if end_ellipsis:
        overhead += len(ELLIPSIS) + 1
    return overhead


def _estimate_chunk_count(
    tokens: list[str],
    max_length: int,
    start_ellipsis: bool,
    end_ellipsis: bool,
) -> int:
    """Rough estimate of how many chunks we'll need."""
    total_len = sum(len(t) for t in tokens) + len(tokens) - 1  # spaces
    # Account for worst-case ellipsis + indicator overhead
    overhead = _max_ellipsis_overhead(2, start_ellipsis, end_ellipsis)
    est = max(2, total_len // (max_length - 10 - overhead) + 1)
    return est


def _split_tokens(
    tokens: list[str],
    max_length: int,
    estimated_total: int,
    start_ellipsis: bool,
    end_ellipsis: bool,
) -> list[str]:
    """Split tokens into chunks, reserving space for indicators + ellipses."""
    reserved_indicator = _max_indicator_len(estimated_total)
    reserved_ellipsis = _max_ellipsis_overhead(
        estimated_total, start_ellipsis, end_ellipsis
    )
    effective_limit = max_length - reserved_indicator - reserved_ellipsis

    chunks: list[str] = []
    current_words: list[str] = []
    current_len = 0

    for token in tokens:
        token_len = len(token)
        # Length if we add this token (with a space separator if not first)
        new_len = current_len + (1 if current_words else 0) + token_len

        if new_len <= effective_limit:
            current_words.append(token)
            current_len = new_len
        else:
            # Flush current chunk if it has content
            if current_words:
                chunks.append(" ".join(current_words))
                current_words = [token]
                current_len = token_len
            else:
                # Single token exceeds the limit - include it anyway
                chunks.append(token)
                current_words = []
                current_len = 0

    # Don't forget the last chunk
    if current_words:
        chunks.append(" ".join(current_words))

    return chunks
