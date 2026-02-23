# Work Log

## 2026-02-22 - Project created

- Initial project setup with TST structure
- Co-founder discussion established technical approach:
  - Playwright + API interception as primary strategy
  - DOM scraping via data-testid as fallback
  - gallery-dl + yt-dlp for media download
  - Twitter/X first, other platforms later
- Key reference projects identified: fa0311/twitter-openapi, proxidize/x-scraper
- Discussion summary saved to HQ

## 2026-02-22 - VP Planning Session (Fiona Feed)

- Sharpened vision into one-liner: "An AI agent scrolls your social media so you never have to"
- Broke Milestone 1 into two concrete sprints (5 tasks each)
- Sprint 1: Scaffolding, session management, GraphQL interception, tweet parsing, data output
- Sprint 2: Scroll automation, stop conditions, deduplication, image download, run summary
- Populated prd.json with 10 user stories (S1.1-S1.5, S2.1-S2.5) with acceptance criteria
- Technical decisions locked: Python 3.11+, JSON files for storage, manual login with saved storage_state
- Updated CLAUDE.md with file structure, technical notes, and key patterns
- Updated roadmap.md with detailed sprint breakdown
- Updated next-tasks.md with concrete task definitions and done criteria
- Defined branch name for Ralph loop: `milestone-1-twitter-collection`
- Researched reference projects (proxidize/x-scraper uses same Playwright + cookie pattern, 2-5s scroll delays)

## 2026-02-22 - Ralph Loop launched

- Initiated autonomous work session via `/tst:project-work`
- Stories to complete: 10
- Starting with: Project Scaffolding (S1.1)

## 2026-02-22 - S1.1 Project Scaffolding complete

- Created all 8 source files in `src/` with initial implementations
- Created `requirements.txt` (playwright, aiohttp), `config.json`, `.gitignore`
- Verified `python3 src/collector.py` runs cleanly and models instantiate correctly
- Branch: `milestone-1-twitter-collection`

## 2026-02-22 - S1.3 GraphQL Response Interception complete

- Wired up `collector.py` with `auth.load_session()` and `interceptor.ResponseInterceptor`
- End-to-end flow: load session → attach page.on("response") → reload page → capture GraphQL responses → save raw JSON
- Interceptor pattern matches `*/i/api/graphql/*/Home*` (HomeTimeline, HomeLatestTimeline)
- Each response logged with: endpoint name, HTTP status, response size, entry count
- Raw responses saved to `feed_data/YYYY-MM-DD/raw/{endpoint}_{timestamp}.json`
- Added microsecond precision to raw filenames to prevent collisions
- Added `sys.path` fix in collector.py so `python3 src/collector.py` works with `from src.` imports
- Graceful error handling for missing/expired sessions
- Files changed: src/collector.py, src/interceptor.py

## 2026-02-22 - S1.4 Tweet Data Parsing complete

- Added `parse_all_tweets()`, `_parse_entry()`, `_parse_tweet_result()`, `_extract_author()`, `_extract_media_urls()` to `ResponseInterceptor`
- Parser navigates Twitter's nested JSON: data.home.home_timeline_urt.instructions[].entries[].content.itemContent.tweet_results.result
- Handles `TweetWithVisibilityResults` wrapper (unwraps to inner tweet)
- Retweets detected via `retweeted_status_result` — original author tracked, inner tweet content used
- Promoted/ad tweets detected via `promotedMetadata` — skipped by default
- Missing fields handled gracefully (empty strings, zero counts, empty lists)
- Cursor entries and non-tweet items filtered out
- Deduplication by tweet ID across multiple responses
- Wired parser into `collector.py` — parse + save after interception
- Created test suite with 12 tests covering all acceptance criteria
- Added pytest to requirements.txt
- Files changed: src/interceptor.py, src/collector.py, requirements.txt, tests/test_parser.py

## 2026-02-22 - S1.5 Structured Data Output complete

- Enhanced `storage.py` with collection metadata (run_timestamp, tweet_count, collection_duration_seconds)
- Used `dataclasses.asdict()` for proper serialization instead of `__dict__`
- Added `load_tweets_from_file()` for loading from arbitrary paths and `load_metadata()` helper
- Updated `collector.py` to track collection timing with `time.monotonic()` and pass duration to save_tweets
- JSON output is pretty-printed with `indent=2` and `ensure_ascii=False`
- Created `tests/test_storage.py` with 12 tests: save, pretty-print, metadata, round-trip, all fields
- All 24 tests pass (12 parser + 12 storage)
- Files changed: src/storage.py, src/collector.py, tests/test_storage.py

## 2026-02-22 - S2.1 Scroll Automation complete

- Enhanced `src/scroller.py` with `scroll_loop()` function that orchestrates scrolling with the interceptor
- `scroll_feed()` scrolls one viewport height down with random delay between `scroll_delay_min` and `scroll_delay_max`
- `scroll_loop()` scrolls continuously, parsing tweets after each scroll via interceptor
- Stale detection: stops after N consecutive scrolls with no new tweets (default stale_limit=3)
- Max tweets stop condition: stops when enough tweets collected
- Detailed logging per scroll: scroll number, new tweets, total tweets, delay used
- Updated `collector.py` to use `scroll_loop()` after initial page load, passing config values
- Final summary includes scroll count, total tweets, and stop reason
- Created `tests/test_scroller.py` with 9 async tests covering: single scroll, max_tweets stop, stale detection, stale reset, zero tweets, delay range, dict keys
- Added `pytest-asyncio` to requirements.txt for async test support
- All 33 tests pass (12 parser + 9 scroller + 12 storage)
- Files changed: src/scroller.py, src/collector.py, requirements.txt, tests/test_scroller.py
