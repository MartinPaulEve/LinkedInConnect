## v0.7.0 (2026-03-22)

### Feat

- **single**: add video upload support with ffmpeg transcoding
- **single**: add alt text support for image uploads
- **single**: support local image uploads in ad-hoc posts
- add automatic threading for long messages on BlueSky and Mastodon

## v0.6.0 (2026-03-22)

### Feat

- add single command for ad-hoc social media posts
- generalize tool for any Atom feed or markdown blog

## v0.5.4 (2026-03-21)

### Fix

- suppress raw httpx/httpcore log lines in favour of structlog
- resolve sync_state.json path from cwd instead of module directory

## v0.5.3 (2026-03-21)

### Refactor

- move source files into src/linkedin_sync package

## v0.5.2 (2026-03-21)

### Fix

- **ci**: skip GitHub release creation if tag already exists
- **linkedin**: auto-resolve person URN from /v2/userinfo and use REST API
- **linkedin**: use urn:li:member format for v2 ugcPosts API
- **linkedin**: switch from REST API to v2 API for Share on LinkedIn product

## v0.5.1 (2026-03-21)

### Fix

- **linkedin**: revert to 202602 API version and add diagnostic hints
- **linkedin**: change default API version to 202501 and add verify command

## v0.5.0 (2026-03-21)

### Feat

- add --only flag, fix Bluesky links, image paths, and tone

## v0.4.0 (2026-03-21)

### Feat

- **parser**: infer URL from Jekyll filename and handle nested image dicts

## v0.3.0 (2026-03-21)

### Feat

- **post**: accept local markdown file paths as well as URLs

## v0.2.0 (2026-03-21)

### Feat

- add image-check command for resizing blog post images
- add thumbnail support for Bluesky link card embeds
- add Bluesky and Mastodon cross-posting support
- add LLM-powered summary mode for LinkedIn posts
- add local markdown file sync support

### Fix

- **tests**: use BlobRef spec for Bluesky thumbnail mock
- **image-check**: resolve root-relative image paths against site root
- **image-check**: handle dict-valued front matter image fields
