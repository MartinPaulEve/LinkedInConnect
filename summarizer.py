"""Generate human-sounding LinkedIn summaries using an LLM."""

import os
import re

from bs4 import BeautifulSoup

from logging_config import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = """\
You are ghostwriting a LinkedIn post for Martin Paul Eve, a professor and \
academic who blogs about higher education, open access, publishing, and \
technology. Your job is to write a short summary of a blog post that will \
appear on his LinkedIn feed.

Rules:
- Write in first person as Martin. Use a natural, conversational academic \
tone. You are not trying to sell anything.
- Summarise the key points of the post honestly. Do not use clickbait \
phrasing like "you won't believe" or "here's why this matters". Just state \
what the post is about and what the main argument or finding is.
- Keep it to 2-4 short paragraphs. Aim for 150-300 words.
- Do NOT use emojis anywhere in the text.
- Do NOT use em-dashes (use commas or full stops instead).
- Do NOT structure the post as a three-item list. Avoid bullet points or \
numbered lists entirely.
- Do NOT use the phrase "In this post" or "I wrote about". Just get into it.
- Do NOT end with a question to the audience or a call to action like \
"What do you think?" or "Let me know in the comments".
- Do NOT use hashtags. They will be added separately.
- Do NOT include the link to the blog post. It will be added separately.
- The summary should give the reader enough substance that they understand \
the argument, but leave them wanting to read the full piece for the detail.
- Avoid corporate or marketing language. Write the way a thoughtful academic \
would write on social media.\
"""

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
    """Generate a LinkedIn summary of a blog post using an LLM.

    The LLM provider is configured via LLM_PROVIDER env var
    ("anthropic" or "openai"). API keys are read from
    ANTHROPIC_API_KEY or OPENAI_API_KEY respectively.
    """
    content_text = _html_to_plain_text(content_html)

    # Truncate very long posts to avoid token limits
    if len(content_text) > 8000:
        content_text = content_text[:8000] + "\n\n[truncated]"

    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=title, content_text=content_text
    )

    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    log.info("generating_summary", provider=provider, title=title)

    if provider == "openai":
        summary = _call_openai(user_prompt)
    elif provider == "anthropic":
        summary = _call_anthropic(user_prompt)
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: {provider}. Use 'anthropic' or 'openai'."
        )

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


def _call_anthropic(user_prompt: str) -> str:
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
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return message.content[0].text


def _call_openai(user_prompt: str) -> str:
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
            {"role": "system", "content": SYSTEM_PROMPT},
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
