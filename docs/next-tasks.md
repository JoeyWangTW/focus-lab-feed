# Prioritized Tasks

## Sprint 1: Session + Interception PoC (This Week)

### S1.1 - Project Scaffolding
**Priority:** Highest (do first)
**Effort:** Small
- Create `src/` directory with empty module files: `__init__.py`, `collector.py`, `auth.py`, `interceptor.py`, `scroller.py`, `media_downloader.py`, `storage.py`, `models.py`
- Create `requirements.txt` with: `playwright`
- Create `config.json` with defaults: scroll delays, output path, max tweets
- Create `.gitignore` with: `session/`, `feed_data/`, `__pycache__/`, `.venv/`, `*.pyc`
- Run `pip install playwright && playwright install chromium`
**Done:** Project runs `python src/collector.py` without errors (even if it does nothing yet)

### S1.2 - Session Management (auth.py)
**Priority:** Highest (do second)
**Effort:** Medium
- Implement `save_session()`: launch Chromium (headed), navigate to twitter.com, wait for user to log in manually, save `storage_state` to `session/twitter_state.json`
- Implement `load_session()`: launch Chromium with saved `storage_state`, verify login by checking for home feed
- Handle missing/expired session gracefully with clear error message
**Done:** Can run auth script, log in once, and subsequent runs load the session automatically

### S1.3 - GraphQL Interception (interceptor.py)
**Priority:** Highest (do third -- this is the core PoC)
**Effort:** Large
- Set up `page.on("response")` listener filtering for URL pattern `*/i/api/graphql/*/Home*`
- Capture raw JSON response bodies from `HomeTimeline` and `HomeLatestTimeline` endpoints
- Log each intercepted response (endpoint name, response size, number of entries)
- Save raw responses to `feed_data/YYYY-MM-DD/raw/` for debugging
**Done:** Navigate to home feed, see intercepted GraphQL responses logged with tweet counts

### S1.4 - Tweet Parsing (models.py + interceptor.py)
**Priority:** High
**Effort:** Medium
- Define `Tweet` dataclass: `id`, `text`, `author_handle`, `author_name`, `created_at`, `likes`, `retweets`, `replies`, `quotes`, `media_urls`, `is_retweet`, `original_author` (if retweet)
- Parse Twitter's nested JSON response structure to extract tweet data
- Handle edge cases: retweets, quote tweets, tweets with no text (media only), promoted tweets (skip or flag)
- Path into response: `data.home.home_timeline_urt.instructions[].entries[].content.itemContent.tweet_results.result`
**Done:** Intercepted JSON is parsed into a list of Tweet objects with all fields populated

### S1.5 - Data Output (storage.py)
**Priority:** High
**Effort:** Small
- Save list of parsed tweets as JSON to `feed_data/YYYY-MM-DD/tweets.json`
- Pretty-printed, one tweet per JSON object in an array
- Include collection metadata: timestamp, tweet count, session info
**Done:** After a collection run, `feed_data/YYYY-MM-DD/tweets.json` exists with readable tweet data

## Sprint 2: Scroll + Media Download (Next Week)

### S2.1 - Scroll Automation (scroller.py)
- Implement `scroll_feed()`: scroll down, wait random 2-5s, repeat
- Track scroll position and detect "end of new content" (no new tweets intercepted after N scrolls)

### S2.2 - Stop Conditions
- Config-driven: `max_tweets`, `max_minutes`, `oldest_tweet_date`
- Whichever threshold is hit first stops the collection

### S2.3 - Deduplication (storage.py)
- Load existing tweet IDs from previous runs
- Skip duplicates during parsing
- Report duplicates skipped in run summary

### S2.4 - Image Download (media_downloader.py)
- Download images from `media_url_https` URLs
- Save to `feed_data/YYYY-MM-DD/media/{tweet_id}_{index}.jpg`
- Update tweet JSON with local file paths

### S2.5 - Run Summary
- Print collection stats: tweets captured, images downloaded, time elapsed, duplicates skipped

## Backlog

- Study proxidize/x-scraper for checkpoint/resume patterns
- Study MIT Gobo for alternative feed reader UX patterns
- Run captured tweets through Claude for rage bait classification (first curation test)
- Video download via gallery-dl + yt-dlp
- Instagram support
- Configurable scroll depth profiles (quick scan vs deep collect)
- Error recovery: resume collection after crash
