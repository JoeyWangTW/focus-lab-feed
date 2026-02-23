# Focus Lab Feed Collector

## Vision

Automated agent that scrolls social media feeds FOR the user, collecting all content (posts, images, videos) via browser automation. The user never touches the toxic infinite scroll. This data feeds into Focus Lab's AI curation layer, which filters, reorders, and mixes content aligned with the user's life goals — replacing mindless social media consumption with intentional, goal-aligned content.

## Technical Approach

- **Playwright** for browser automation (headed mode, not headless)
- **API interception** via `page.on("response")` to capture Twitter's GraphQL responses — clean structured JSON, no DOM parsing needed
- **DOM scraping** via `data-testid` selectors as fallback only
- **gallery-dl + yt-dlp** for media download (images first, video later)
- Start with **Twitter/X only**, replicate to other platforms later

## Work Documentation

### Status Updates
- Read `docs/status.md` at the start of every session to understand current project state
- Update `docs/status.md` after completing work with what was done and what's next

### Work Logging
- Append entries to `docs/worklog.md` for every work session
- Format: `## YYYY-MM-DD - Brief description` followed by bullet points of changes

### Inbox
- Check `docs/inbox.md` at the start of every session for action items from co-founder discussions or standups
- Mark items as `[SEEN]` after reading them
- Address action items in your current work session

## Project Conventions

- Python 3.11+ with async/await (Playwright is async)
- Use `playwright.async_api` for all browser automation
- Store collected data as structured JSON in `feed_data/YYYY-MM-DD/`
- Media files stored alongside JSON: `feed_data/YYYY-MM-DD/media/`
- Session state (cookies) stored in `session/twitter_state.json` — NEVER commit this file
- Reference projects: fa0311/twitter-openapi, proxidize/x-scraper, MIT Gobo
- All source code lives in `src/` directory
- Config in `config.json` at project root (scroll depth, delays, output paths)

## File Structure

```
focus-lab-feed-collector/
  src/
    collector.py          # Main entry point — orchestrates collection run
    auth.py               # Session management — login, save/load cookies
    interceptor.py        # GraphQL response interception and parsing
    scroller.py           # Scroll automation — timing, depth, stop conditions
    media_downloader.py   # Image/video download from media URLs
    storage.py            # Data persistence — JSON output, deduplication
    models.py             # Data classes for Tweet, Author, Media, etc.
  config.json             # Runtime configuration
  session/                # Browser session state (gitignored)
  feed_data/              # Collected data output (gitignored)
  tests/                  # Test files
  docs/                   # Project documentation
```

## Key Technical Notes

- Twitter GraphQL endpoints to intercept: `HomeTimeline`, `HomeLatestTimeline`
- Match responses by URL pattern: `*/i/api/graphql/*/Home*`
- Tweet data lives deep in response JSON: `data.home.home_timeline_urt.instructions[].entries[].content.itemContent.tweet_results.result`
- Media URLs use `media_url_https` field with size suffix (e.g., `?format=jpg&name=large`)
- Use random delays between scrolls (2-5s) to mimic human behavior
- Save browser state via `context.storage_state(path=...)` for session persistence

## Allowed Commands

- `pip install playwright`
- `playwright install chromium`
- `python *.py`
- `python src/*.py`
- `pip install gallery-dl yt-dlp`
- `pip install -r requirements.txt`
- `python -m pytest`
