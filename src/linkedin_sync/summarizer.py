"""Generate human-sounding social media summaries using an LLM."""

import os
import re

from bs4 import BeautifulSoup

from linkedin_sync.logging_config import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT_LINKEDIN = """\
You are ghostwriting a LinkedIn post for the author of a blog. Your job is \
to write a short summary of a blog post that will appear on their LinkedIn \
feed.

Rules:
- Write in first person as the author. Use a casual, understated tone, as \
though you're mentioning something to a colleague in passing. Think "here's \
a post about how I set up X" or "my thoughts on Y" rather than anything \
that sounds like an announcement or promotion.
- Just say what the post is about and what the main point is. No hype, no \
grandiosity, no selling. If it's a technical walkthrough, say so plainly. \
If it's an opinion piece, state the opinion directly.
- Keep it to 2-3 short paragraphs. Aim for 100-200 words. Shorter is better.
- Do NOT use emojis anywhere in the text.
- Do NOT use em-dashes (use commas or full stops instead).
- Do NOT structure the post as a list. Avoid bullet points or numbered \
lists entirely.
- Do NOT use phrases like "In this post", "I wrote about", "I'm excited \
to share", "Delighted to announce", or "Here's why this matters".
- Do NOT end with a question to the audience or a call to action like \
"What do you think?" or "Let me know in the comments".
- Do NOT use hashtags. They will be added separately.
- Do NOT include the link to the blog post. It will be added separately.
- Avoid corporate, marketing, or motivational language. No "game-changer", \
"deep dive", "crucial", "essential", "powerful", "fascinating", or similar \
inflated words. Write plainly.
- The voice should sound like a person, not a brand.\
"""

_SYSTEM_PROMPT_SHORT = """\
You are ghostwriting a short social media post for the author of a blog. \
Your job is to write a very brief summary of a blog post, suitable for \
Bluesky or Mastodon.

Rules:
- Write in first person as the author. Casual, understated tone, like \
mentioning something to a friend. Think "wrote up how to do X" or \
"some thoughts on Y".
- You MUST keep the entire output under {max_chars} characters. This is a \
hard limit. Count carefully.
- Get straight to the point. One or two sentences.
- Do NOT use emojis.
- Do NOT use em-dashes (use commas or full stops instead).
- Do NOT use hashtags, bullet points, or numbered lists.
- Do NOT include any URLs or links. The link will be added separately.
- Do NOT use "In this post" or "I wrote about". Just state the point.
- Do NOT end with a question or call to action.
- No hype or inflated language. Write plainly.\
"""


def _build_system_prompt(base_prompt: str, **kwargs) -> str:
    """Build a system prompt, appending author context if configured."""
    prompt = base_prompt.format(**kwargs) if kwargs else base_prompt
    author_context = os.environ.get("BLOG_AUTHOR_CONTEXT", "").strip()
    if author_context:
        prompt += f"\n\nAdditional context about the author: {author_context}"
    return prompt


USER_PROMPT_TEMPLATE = """\
Blog post title: {title}

Blog post content:
{content_text}\
"""


def summarize_post(
    title: str,
    content_html: str,
    post_url: str,
    doi: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Generate a LinkedIn summary of a blog post using an LLM."""
    content_text = _html_to_plain_text(content_html)

    if len(content_text) > 8000:
        content_text = content_text[:8000] + "\n\n[truncated]"

    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=title, content_text=content_text
    )

    system_prompt = _build_system_prompt(_SYSTEM_PROMPT_LINKEDIN)
    summary = _call_llm(system_prompt, user_prompt)

    # Build the final post with footer
    parts = [summary.strip()]
    parts.append("")

    if doi:
        parts.append(f"DOI: https://doi.org/{doi}")

    parts.append(f"Read the full post: {post_url}")

    if tags:
        hashtags = " ".join(f"#{_sanitize_hashtag(t)}" for t in tags[:5])
        parts.append("")
        parts.append(hashtags)

    result = "\n".join(parts)
    log.info("summary_generated", total_length=len(result))
    return result


def summarize_post_short(
    title: str,
    content_html: str,
    post_url: str,
    max_chars: int = 280,
) -> str:
    """Generate a short summary for Bluesky/Mastodon.

    The returned text includes the post URL appended at the end.
    max_chars is the platform limit; the summary text is sized to
    leave room for the URL.
    """
    content_text = _html_to_plain_text(content_html)

    if len(content_text) > 8000:
        content_text = content_text[:8000] + "\n\n[truncated]"

    # Reserve space for "\n\n" + URL
    url_overhead = len(post_url) + 2
    summary_budget = max_chars - url_overhead

    system_prompt = _build_system_prompt(
        _SYSTEM_PROMPT_SHORT, max_chars=summary_budget
    )
    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=title, content_text=content_text
    )

    summary = _call_llm(system_prompt, user_prompt)
    summary = summary.strip()

    # Hard-truncate if the LLM exceeded the budget
    if len(summary) > summary_budget:
        summary = summary[: summary_budget - 3].rsplit(" ", 1)[0] + "..."

    result = f"{summary}\n\n{post_url}"
    log.info(
        "short_summary_generated",
        total_length=len(result),
        max_chars=max_chars,
    )
    return result


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call the configured LLM provider."""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    log.info("calling_llm", provider=provider)

    if provider == "openai":
        return _call_openai(system_prompt, user_prompt)
    elif provider == "anthropic":
        return _call_anthropic(system_prompt, user_prompt)
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: {provider}. Use 'anthropic' or 'openai'."
        )


def _call_anthropic(system_prompt: str, user_prompt: str) -> str:
    """Call the Anthropic API to generate a summary."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is required "
            "when LLM_PROVIDER=anthropic"
        )

    model = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
    client = anthropic.Anthropic(api_key=api_key)
    log.debug("calling_anthropic", model=model)

    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return message.content[0].text


def _call_openai(system_prompt: str, user_prompt: str) -> str:
    """Call the OpenAI API to generate a summary."""
    import openai

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable is required "
            "when LLM_PROVIDER=openai"
        )

    model = os.environ.get("LLM_MODEL", "gpt-4o")
    client = openai.OpenAI(api_key=api_key)
    log.debug("calling_openai", model=model)

    response = client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.choices[0].message.content


def _html_to_plain_text(html: str) -> str:
    """Convert HTML to plain text for the LLM prompt."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _sanitize_hashtag(tag: str) -> str:
    """Clean a tag string for use as a LinkedIn hashtag."""
    return re.sub(r"[^a-zA-Z0-9]", "", tag)
