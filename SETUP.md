# LinkedIn Blog Post Sync - Setup Guide

This tool syncs blog posts from an Atom feed to LinkedIn, Bluesky, and Mastodon.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- A LinkedIn account
- A LinkedIn Developer Application (instructions below)

## Step 1: Install Dependencies

```bash
cd LinkedInConnect
uv sync
```

This reads `pyproject.toml` and installs all dependencies into a virtual environment managed by uv.

## Step 2: Create a LinkedIn Developer Application

1. Go to [LinkedIn Developer Portal](https://developer.linkedin.com/) and sign in with your LinkedIn account.

2. Click **Create App** and fill in:
   - **App name**: e.g., "Blog Post Sync"
   - **LinkedIn Page**: You need to associate it with a LinkedIn Company Page. If you don't have one, create a simple one first at [linkedin.com/company/setup/new](https://www.linkedin.com/company/setup/new/).
   - **Privacy policy URL**: Can be your blog URL
   - **App logo**: Any square image (required)

3. After creating the app, go to the **Products** tab.

4. Request access to these products:
   - **Share on LinkedIn** — this grants the `w_member_social` scope needed to create posts
   - **Sign In with LinkedIn using OpenID Connect** — this grants `openid` and `profile` scopes

   > **Note:** "Share on LinkedIn" may require review and approval by LinkedIn. This can take a few minutes to a few days. The `w_member_social` permission is essential for creating posts.

5. Go to the **Auth** tab:
   - Note your **Client ID** and **Client Secret**
   - Under **OAuth 2.0 settings**, add this redirect URL:
     ```
     http://localhost:8585/callback
     ```

## Step 3: Configure Environment Variables

Create a `.env` file in the project directory:

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```env
# LinkedIn OAuth2 credentials (from Developer Portal -> Auth tab)
LINKEDIN_CLIENT_ID="your_client_id_here"
LINKEDIN_CLIENT_SECRET="your_client_secret_here"

# These will be filled in after running oauth_helper.py
LINKEDIN_ACCESS_TOKEN=""
LINKEDIN_PERSON_URN=""

# Bluesky credentials
# Handle: your full Bluesky handle WITHOUT the leading @ symbol
# e.g. "yourname.bsky.social" — NOT "@yourname.bsky.social"
BLUESKY_HANDLE=""
BLUESKY_APP_PASSWORD=""

# Mastodon credentials
MASTODON_INSTANCE_URL=""
MASTODON_ACCESS_TOKEN=""
```

> **Bluesky note:** Your handle must not include the `@` symbol at the start. Use `yourname.bsky.social`, not `@yourname.bsky.social`. For the app password, generate one at bsky.app under Settings > Privacy and Security > App Passwords. You cannot use your account password.

> **Security:** The `.env` file is in `.gitignore` and should **never** be committed. Keep your credentials safe.

## Step 4: Obtain an Access Token

Run the OAuth helper script:

```bash
uv run linkedin-oauth
```

Or directly:

```bash
uv run python src/linkedin_sync/oauth_helper.py
```

This will:
1. Open your browser to LinkedIn's authorization page
2. Ask you to sign in and grant permissions
3. Capture the callback on `localhost:8585`
4. Exchange the authorization code for an access token
5. Fetch your LinkedIn Person URN
6. Print both values for you to save

Copy the `LINKEDIN_ACCESS_TOKEN` and `LINKEDIN_PERSON_URN` values into your `.env` file.

### Access Token Expiry

LinkedIn access tokens typically expire after **60 days**. When your token expires, run `uv run linkedin-oauth` again to get a new one.

## Step 5: Verify Setup

Test that everything works with a dry run:

```bash
uv run linkedin-sync --dry-run
```

This will fetch the feed, find today's posts, format them, and show what would be posted — without actually posting anything.

## Usage

All commands can be run with `uv run linkedin-sync` (the installed entry point) or `uv run python src/linkedin_sync/sync.py`.

### Sync today's posts

```bash
uv run linkedin-sync
```

This finds all posts published today in the Atom feed that haven't been synced yet, and posts them to LinkedIn.

### Sync a specific post

```bash
uv run linkedin-sync post "https://eve.gd/2025/03/17/institutional-stupidity/"
```

### Force re-sync a post

```bash
uv run linkedin-sync --force post "https://eve.gd/2025/03/17/some-post/"
```

### Dry run (preview without posting)

```bash
uv run linkedin-sync --dry-run
uv run linkedin-sync --dry-run post "https://eve.gd/2025/03/17/some-post/"
```

### List synced posts

```bash
uv run linkedin-sync list
```

### Use a custom feed URL

```bash
uv run linkedin-sync --feed-url "https://eve.gd/feed/feed.atom"
```

## Logging

The tool uses structured logging via **structlog** with **rich** for human-readable output by default.

### Human-readable logs (default)

```bash
uv run linkedin-sync --dry-run
```

Produces colourful, formatted console output.

### JSON structured logs

```bash
uv run linkedin-sync --json-logs --dry-run
```

Produces one JSON object per line on stderr — useful for piping to log aggregators (e.g., `jq`, Datadog, CloudWatch).

### Verbose / debug logging

```bash
uv run linkedin-sync -v --dry-run
```

Enables `DEBUG`-level output. Combine with `--json-logs` as needed.

## Docker

You can run the tool in a Docker container using Docker Compose. This avoids needing Python or uv installed on your host.

### Build the image

```bash
docker compose build
```

### Run commands

The container's entrypoint is `linkedin-sync`, so you pass subcommands and flags directly:

```bash
# Sync today's posts
docker compose run --rm linkedin-sync

# Dry run
docker compose run --rm linkedin-sync --dry-run

# Sync a specific post
docker compose run --rm linkedin-sync post "https://eve.gd/2025/03/17/some-post/"

# Force re-sync with JSON logs
docker compose run --rm linkedin-sync --json-logs --force post "https://eve.gd/2025/03/17/some-post/"

# List synced posts
docker compose run --rm linkedin-sync list

# Verbose output
docker compose run --rm linkedin-sync -v --dry-run
```

The `docker-compose.yml` mounts `sync_state.json` from the host so that sync state persists between container runs. It also reads your `.env` file for credentials.

### Cron with Docker

```cron
0 12 * * * cd /path/to/LinkedInConnect && docker compose run --rm linkedin-sync >> sync.log 2>&1
```

## Running After Publishing a Blog Post

You can run `linkedin-sync` manually after publishing a post, or set up a simple automation:

### Option A: Manual (run after publishing)

```bash
uv run linkedin-sync
```

### Option B: Cron job (check daily)

```cron
# Run daily at noon — only syncs today's posts
0 12 * * * cd /path/to/LinkedInConnect && uv run linkedin-sync >> sync.log 2>&1
```

### Option C: Post-publish hook

If your blog has a post-publish hook (e.g., Hugo, Jekyll, WordPress), call the sync script from there:

```bash
#!/bin/bash
# post-publish.sh
cd /path/to/LinkedInConnect
uv run linkedin-sync
```

## Running Tests

```bash
uv sync                   # install all deps including dev group
uv run pytest             # run the test suite
uv run pytest -v          # verbose output
uv run pytest --cov       # with coverage report
```

## How It Works

1. **Feed parsing**: Fetches and parses the Atom feed configured via `BLOG_FEED_URL`
2. **Content formatting**: Converts HTML blog content to LinkedIn-friendly plain text:
   - Preserves paragraph structure with line breaks
   - Converts lists to bullet/numbered format
   - Includes blockquotes
   - Adds the original post URL and DOI (if present)
   - Adds relevant hashtags from post tags
   - Truncates to LinkedIn's ~3000 character limit
3. **Image upload**: If the post has a featured image, it's downloaded and uploaded to LinkedIn via the Images API
4. **Post creation**: Creates a public LinkedIn post via the Posts API with the formatted text and optional image
5. **Sync tracking**: Records which posts have been synced in `sync_state.json` to avoid duplicates

## Important Notes

- **No backdating**: LinkedIn does not support setting a custom publish date. Posts will appear with the date they were actually posted to LinkedIn. The original publish date is mentioned in the post text via the link to the original blog post.
- **Character limit**: LinkedIn posts are limited to ~3000 characters. Long blog posts are intelligently truncated with a "Read the full post" link.
- **Rate limits**: LinkedIn API has rate limits. Avoid syncing many posts in rapid succession.
- **Token refresh**: Access tokens expire after ~60 days. Re-run `uv run linkedin-oauth` when needed.

## Troubleshooting

### "401 Unauthorized" errors
Your access token has expired. Run `uv run linkedin-oauth` to get a new one.

### "403 Forbidden" errors
Your app may not have the required permissions. Check that "Share on LinkedIn" is approved in your app's Products tab.

### "Post not found in feed"
The URL must match exactly as it appears in the Atom feed. Check with `--dry-run` to see available posts.

### Image upload failures
Some images may be too large or in unsupported formats. The tool will continue without the image and create a text-only post.
