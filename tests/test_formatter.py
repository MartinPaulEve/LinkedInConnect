"""Tests for formatter module."""

from linkedin_sync.formatter import (
    MAX_LINKEDIN_POST_LENGTH,
    _html_to_linkedin_text,
    _sanitize_hashtag,
    _truncate_text,
    format_for_linkedin,
)


class TestFormatForLinkedin:
    def test_basic_structure(self):
        result = format_for_linkedin(
            title="My Post",
            content_html="<p>Hello world</p>",
            post_url="https://eve.gd/2025/01/01/my-post/",
        )
        assert "My Post" in result
        assert "Hello world" in result
        assert (
            "Read the full post: https://eve.gd/2025/01/01/my-post/" in result
        )

    def test_includes_doi(self):
        result = format_for_linkedin(
            title="Paper Post",
            content_html="<p>Content</p>",
            post_url="https://eve.gd/post/",
            doi="10.1234/test",
        )
        assert "DOI: https://doi.org/10.1234/test" in result

    def test_no_doi_when_none(self):
        result = format_for_linkedin(
            title="Post",
            content_html="<p>Content</p>",
            post_url="https://eve.gd/post/",
            doi=None,
        )
        assert "DOI:" not in result

    def test_includes_hashtags(self):
        result = format_for_linkedin(
            title="Tagged Post",
            content_html="<p>Content</p>",
            post_url="https://eve.gd/post/",
            tags=["python", "open-access"],
        )
        assert "#python" in result
        assert "#openaccess" in result

    def test_limits_to_five_hashtags(self):
        tags = ["a", "b", "c", "d", "e", "f", "g"]
        result = format_for_linkedin(
            title="Post",
            content_html="<p>Content</p>",
            post_url="https://eve.gd/post/",
            tags=tags,
        )
        # Only 5 hashtags should appear
        assert result.count("#") == 5

    def test_respects_max_length(self):
        long_content = "<p>" + "This is a long sentence. " * 200 + "</p>"
        result = format_for_linkedin(
            title="Long Post",
            content_html=long_content,
            post_url="https://eve.gd/post/",
            max_length=500,
        )
        assert len(result) <= 500

    def test_truncation_includes_ellipsis(self):
        long_content = "<p>" + "word " * 1000 + "</p>"
        result = format_for_linkedin(
            title="Long Post",
            content_html=long_content,
            post_url="https://eve.gd/post/",
            max_length=300,
        )
        assert "..." in result

    def test_empty_content(self):
        result = format_for_linkedin(
            title="Empty Post",
            content_html="",
            post_url="https://eve.gd/post/",
        )
        assert "Empty Post" in result
        assert "Read the full post:" in result

    def test_full_blog_post(self, sample_blog_post):
        result = format_for_linkedin(
            title=sample_blog_post.title,
            content_html=sample_blog_post.content_html,
            post_url=sample_blog_post.url,
            doi=sample_blog_post.doi,
            tags=sample_blog_post.tags,
        )
        assert sample_blog_post.title in result
        assert "10.1234/test.5678" in result
        assert "#academia" in result
        assert len(result) <= MAX_LINKEDIN_POST_LENGTH


class TestHtmlToLinkedinText:
    def test_paragraph(self):
        result = _html_to_linkedin_text("<p>Hello world</p>")
        assert "Hello world" in result

    def test_headings_uppercased_h1_h2(self):
        result = _html_to_linkedin_text(
            "<h1>Big Title</h1><h3>Small Title</h3>"
        )
        assert "BIG TITLE" in result
        assert "Small Title" in result
        # h3 should NOT be uppercased
        assert "SMALL TITLE" not in result

    def test_unordered_list(self):
        result = _html_to_linkedin_text("<ul><li>One</li><li>Two</li></ul>")
        assert "- One" in result
        assert "- Two" in result

    def test_ordered_list(self):
        result = _html_to_linkedin_text(
            "<ol><li>First</li><li>Second</li></ol>"
        )
        assert "1. First" in result
        assert "2. Second" in result

    def test_blockquote(self):
        result = _html_to_linkedin_text(
            "<blockquote>Famous words</blockquote>"
        )
        assert '"Famous words"' in result

    def test_link_includes_url(self):
        result = _html_to_linkedin_text(
            '<a href="https://example.com">Click here</a>'
        )
        assert "Click here" in result
        assert "https://example.com" in result

    def test_anchor_link_no_url(self):
        result = _html_to_linkedin_text('<a href="#section">Jump</a>')
        assert "Jump" in result
        assert "#section" not in result

    def test_image_alt_text(self):
        result = _html_to_linkedin_text('<img src="x.jpg" alt="A photo" />')
        assert "[A photo]" in result

    def test_image_no_alt(self):
        result = _html_to_linkedin_text('<img src="x.jpg" />')
        assert "[" not in result

    def test_hr_becomes_dashes(self):
        result = _html_to_linkedin_text("<p>Above</p><hr/><p>Below</p>")
        assert "---" in result

    def test_pre_block(self):
        result = _html_to_linkedin_text("<pre>code line 1\ncode line 2</pre>")
        assert "code line 1" in result
        assert "code line 2" in result

    def test_strips_script_and_style(self):
        html = (
            "<p>Good</p><script>evil()</script>"
            "<style>.bad{}</style><p>Also good</p>"
        )
        result = _html_to_linkedin_text(html)
        assert "Good" in result
        assert "Also good" in result
        assert "evil" not in result
        assert ".bad" not in result

    def test_figure_with_figcaption(self):
        html = (
            '<figure><img src="x.jpg" />'
            "<figcaption>Photo credit: Me</figcaption>"
            "</figure>"
        )
        result = _html_to_linkedin_text(html)
        assert "[Photo credit: Me]" in result

    def test_bold_italic_text_preserved(self):
        html = "<p><strong>Bold</strong> and <em>italic</em></p>"
        result = _html_to_linkedin_text(html)
        assert "Bold" in result
        assert "italic" in result

    def test_excessive_whitespace_cleaned(self):
        html = "<p>One</p><p></p><p></p><p></p><p>Two</p>"
        result = _html_to_linkedin_text(html)
        assert "\n\n\n" not in result

    def test_empty_html(self):
        assert _html_to_linkedin_text("") == ""

    def test_br_tag(self):
        result = _html_to_linkedin_text("Line one<br/>Line two")
        assert "Line one" in result
        assert "Line two" in result


class TestTruncateText:
    def test_short_text_unchanged(self):
        assert _truncate_text("Hello", 100) == "Hello"

    def test_truncates_at_paragraph(self):
        text = "First paragraph.\n\nSecond paragraph that is quite long."
        result = _truncate_text(text, 30)
        assert result.endswith("...")
        assert "First paragraph" in result

    def test_truncates_at_sentence(self):
        text = "First sentence. Second sentence is longer and goes on."
        result = _truncate_text(text, 40)
        assert result.rstrip().endswith("...")

    def test_truncates_at_word(self):
        text = "word " * 50
        result = _truncate_text(text, 30)
        assert len(result) <= 34  # 30 + "..."
        assert result.endswith("...")

    def test_exact_length_no_truncation(self):
        text = "Exactly this."
        result = _truncate_text(text, len(text))
        assert result == text


class TestSanitizeHashtag:
    def test_alphanumeric_unchanged(self):
        assert _sanitize_hashtag("python3") == "python3"

    def test_removes_hyphens(self):
        assert _sanitize_hashtag("open-access") == "openaccess"

    def test_removes_spaces(self):
        assert _sanitize_hashtag("machine learning") == "machinelearning"

    def test_removes_special_chars(self):
        assert _sanitize_hashtag("C++/C#") == "CC"

    def test_empty_string(self):
        assert _sanitize_hashtag("") == ""
