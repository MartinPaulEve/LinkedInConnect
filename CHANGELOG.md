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
