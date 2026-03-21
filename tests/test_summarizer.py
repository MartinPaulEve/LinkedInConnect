"""Tests for the LLM summarizer module."""

from unittest.mock import MagicMock, patch

import pytest

from summarizer import (
    _html_to_plain_text,
    summarize_post,
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
    @patch("summarizer._call_anthropic")
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

    @patch("summarizer._call_openai")
    def test_openai_provider(self, mock_call, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        mock_call.return_value = "An OpenAI summary."

        result = summarize_post(
            title="Test Post",
            content_html="<p>Content.</p>",
            post_url="https://eve.gd/test/",
        )

        mock_call.assert_called_once()
        assert "An OpenAI summary." in result

    @patch("summarizer._call_anthropic")
    def test_default_provider_is_anthropic(self, mock_call, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        mock_call.return_value = "Summary text."

        summarize_post(
            title="Test",
            content_html="<p>X</p>",
            post_url="https://eve.gd/t/",
        )

        mock_call.assert_called_once()

    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")

        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            summarize_post(
                title="Test",
                content_html="<p>X</p>",
                post_url="https://eve.gd/t/",
            )

    @patch("summarizer._call_anthropic")
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

    @patch("summarizer._call_anthropic")
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

    @patch("summarizer._call_anthropic")
    def test_truncates_long_content(self, mock_call, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        mock_call.return_value = "Summary."

        long_html = "<p>" + "x" * 10000 + "</p>"
        summarize_post(
            title="Test",
            content_html=long_html,
            post_url="https://eve.gd/t/",
        )

        # Check that the prompt sent to the LLM was truncated
        call_args = mock_call.call_args[0][0]
        assert "[truncated]" in call_args


class TestCallAnthropic:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        from summarizer import _call_anthropic

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            _call_anthropic("test prompt")

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
            from summarizer import _call_anthropic

            result = _call_anthropic("test prompt")

        assert result == "Generated summary."
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


class TestCallOpenai:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        from summarizer import _call_openai

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            _call_openai("test prompt")

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
            from summarizer import _call_openai

            result = _call_openai("test prompt")

        assert result == "OpenAI summary."
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"


class TestSyncPostSummaryMode:
    """Test that sync_post correctly uses summary mode."""

    @patch("sync.summarize_post")
    @patch("sync.format_for_linkedin")
    def test_summary_true_calls_summarize(
        self, mock_format, mock_summarize, monkeypatch
    ):
        mock_summarize.return_value = "LLM summary text"

        from datetime import datetime, timezone

        from feed_parser import BlogPost

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

        from unittest.mock import MagicMock

        from sync import sync_post

        tracker = MagicMock()
        result = sync_post(post, None, tracker, dry_run=True, summary=True)

        assert result is True
        mock_summarize.assert_called_once()
        mock_format.assert_not_called()

    @patch("sync.summarize_post")
    @patch("sync.format_for_linkedin")
    def test_summary_false_calls_format(self, mock_format, mock_summarize):
        mock_format.return_value = "Formatted full text"

        from datetime import datetime, timezone

        from feed_parser import BlogPost

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

        from unittest.mock import MagicMock

        from sync import sync_post

        tracker = MagicMock()
        result = sync_post(post, None, tracker, dry_run=True, summary=False)

        assert result is True
        mock_format.assert_called_once()
        mock_summarize.assert_not_called()
