"""Tests for the LLM summarizer module."""

from unittest.mock import MagicMock, patch

import pytest

from linkedin_sync.summarizer import (
    _html_to_plain_text,
    summarize_post,
    summarize_post_short,
)


class TestHtmlToPlainText:
    def test_basic_html(self):
        html = "<p>Hello <strong>world</strong></p>"
        assert "Hello" in _html_to_plain_text(html)
        assert "world" in _html_to_plain_text(html)

    def test_strips_script_tags(self):
        html = "<p>Content</p><script>alert('x')</script>"
        result = _html_to_plain_text(html)
        assert "alert" not in result
        assert "Content" in result

    def test_empty_html(self):
        assert _html_to_plain_text("") == ""


class TestSummarizePost:
    @patch("linkedin_sync.summarizer._call_llm")
    def test_anthropic_provider(self, mock_call, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        mock_call.return_value = "A great summary of this post."

        result = summarize_post(
            title="Test Post",
            content_html="<p>Some content here.</p>",
            post_url="https://eve.gd/test/",
        )

        mock_call.assert_called_once()
        assert "A great summary of this post." in result
        assert "https://eve.gd/test/" in result

    @patch("linkedin_sync.summarizer._call_llm")
    def test_includes_doi(self, mock_call, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        mock_call.return_value = "Summary."

        result = summarize_post(
            title="Test",
            content_html="<p>X</p>",
            post_url="https://eve.gd/t/",
            doi="10.1234/test",
        )

        assert "DOI: https://doi.org/10.1234/test" in result

    @patch("linkedin_sync.summarizer._call_llm")
    def test_includes_hashtags(self, mock_call, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        mock_call.return_value = "Summary."

        result = summarize_post(
            title="Test",
            content_html="<p>X</p>",
            post_url="https://eve.gd/t/",
            tags=["python", "openaccess"],
        )

        assert "#python" in result
        assert "#openaccess" in result

    @patch("linkedin_sync.summarizer._call_llm")
    def test_truncates_long_content(self, mock_call, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        mock_call.return_value = "Summary."

        long_html = "<p>" + "x" * 10000 + "</p>"
        summarize_post(
            title="Test",
            content_html=long_html,
            post_url="https://eve.gd/t/",
        )

        call_args = mock_call.call_args[0]
        assert "[truncated]" in call_args[1]


class TestSummarizePostShort:
    @patch("linkedin_sync.summarizer._call_llm")
    def test_includes_url(self, mock_call):
        mock_call.return_value = "Short summary."

        result = summarize_post_short(
            title="Test",
            content_html="<p>Content</p>",
            post_url="https://eve.gd/t/",
            max_chars=300,
        )

        assert "https://eve.gd/t/" in result
        assert "Short summary." in result

    @patch("linkedin_sync.summarizer._call_llm")
    def test_respects_max_chars(self, mock_call):
        mock_call.return_value = "Short."

        result = summarize_post_short(
            title="Test",
            content_html="<p>Content</p>",
            post_url="https://eve.gd/t/",
            max_chars=300,
        )

        assert len(result) <= 300

    @patch("linkedin_sync.summarizer._call_llm")
    def test_hard_truncates_if_llm_exceeds_budget(self, mock_call):
        # Return something way too long
        mock_call.return_value = "x" * 500

        result = summarize_post_short(
            title="Test",
            content_html="<p>Content</p>",
            post_url="https://eve.gd/t/",
            max_chars=300,
        )

        assert len(result) <= 300
        assert result.endswith("https://eve.gd/t/")


class TestCallLlm:
    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")

        from linkedin_sync.summarizer import _call_llm

        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            _call_llm("system", "user")


class TestCallAnthropic:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        from linkedin_sync.summarizer import _call_anthropic

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            _call_anthropic("system", "test prompt")

    def test_calls_api(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5-20251001")

        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Generated summary.")]
        mock_client.messages.create.return_value = mock_message

        mock_anthropic_mod = MagicMock()
        mock_anthropic_mod.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic_mod}):
            from linkedin_sync.summarizer import _call_anthropic

            result = _call_anthropic("system prompt", "test prompt")

        assert result == "Generated summary."
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


class TestCallOpenai:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        from linkedin_sync.summarizer import _call_openai

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            _call_openai("system", "test prompt")

    def test_calls_api(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")

        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "OpenAI summary."
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        mock_openai_mod = MagicMock()
        mock_openai_mod.OpenAI.return_value = mock_client

        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            from linkedin_sync.summarizer import _call_openai

            result = _call_openai("system prompt", "test prompt")

        assert result == "OpenAI summary."
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"


class TestSyncPostSummaryMode:
    """Test that sync_post correctly uses summary mode."""

    @patch("linkedin_sync.sync.summarize_post_short")
    @patch("linkedin_sync.sync.summarize_post")
    @patch("linkedin_sync.sync.format_for_linkedin")
    def test_summary_true_calls_summarize(
        self, mock_format, mock_summarize, mock_short, monkeypatch
    ):
        mock_summarize.return_value = "LLM summary text"
        mock_short.return_value = "Short summary https://eve.gd/test/"

        from datetime import datetime, timezone
        from unittest.mock import MagicMock

        from linkedin_sync.feed_parser import BlogPost
        from linkedin_sync.sync import sync_post

        post = BlogPost(
            id="https://eve.gd/test/",
            title="Test",
            url="https://eve.gd/test/",
            published=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated=None,
            content_html="<p>Content</p>",
            summary="Content",
            featured_image_url=None,
            doi=None,
            tags=[],
        )

        tracker = MagicMock()
        sync_post(post, tracker, dry_run=True, summary=True)

        mock_summarize.assert_called_once()
        mock_format.assert_not_called()

    @patch("linkedin_sync.sync.summarize_post_short")
    @patch("linkedin_sync.sync.summarize_post")
    @patch("linkedin_sync.sync.format_for_linkedin")
    def test_summary_false_calls_format(
        self, mock_format, mock_summarize, mock_short
    ):
        mock_format.return_value = "Formatted full text"

        from datetime import datetime, timezone
        from unittest.mock import MagicMock

        from linkedin_sync.feed_parser import BlogPost
        from linkedin_sync.sync import sync_post

        post = BlogPost(
            id="https://eve.gd/test/",
            title="Test",
            url="https://eve.gd/test/",
            published=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated=None,
            content_html="<p>Content</p>",
            summary="Content",
            featured_image_url=None,
            doi=None,
            tags=[],
        )

        tracker = MagicMock()
        sync_post(post, tracker, dry_run=True, summary=False)

        mock_format.assert_called_once()
        mock_summarize.assert_not_called()
        mock_short.assert_not_called()
