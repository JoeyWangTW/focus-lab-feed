# Project Status

**Last updated:** 2026-07-14

**Current state:** Desktop app rebranded to **Focus Lab — Vibe Scrolling** with a proper gated onboarding, a focused Curate-with-AI tab, and a clarified Export page. Multi-platform collection working (Twitter, Threads, Instagram, YouTube, LinkedIn). Curator skill can now **publish the curated feed to Cloudflare R2** for phone scrolling.

## Recently Completed (2026-07-14) — branch `feature/publish-feed`

**Collection was broken; four bugs fixed.** Symptoms: x/threads/instagram appeared to hang and never finished; youtube/linkedin finished but collected 0 posts.

1. **Media race (all platforms).** `media_downloader` read a module-global `_current_run_dir`, but the desktop app launches all five collectors concurrently via `asyncio.create_task` in one event loop. Last writer won, so every platform's media was written into `linkedin/media/`. `run_dir` is now passed explicitly by each collector.
2. **The "hang" was unbounded sequential downloads.** ~1GB of video, one file at a time, no timeout — a run took 10+ minutes with no progress output. Now 6-way concurrent, streamed to disk, with connect (15s) / read (60s) / total (180s) timeouts. Runs dropped to 2–7 min.
3. **YouTube: channel-picker interstitial.** The account owns two channels, so YouTube redirected `youtube.com` → `/account` behind a "Select a channel" modal. `ytInitialData` was the *settings page*, so every run parsed 0 items. `auth.py` now selects the primary channel, ticks "don't ask again", and re-saves the session.
4. **LinkedIn: DOM redesign.** LinkedIn no longer ships feed updates over Voyager XHR (only notification cards carry activity URNs now) and server-renders the feed with hashed per-build class names (`div._1264a1eb`). Both the API parser and the `feed-shared-update-v2` selectors found nothing. Extractor rewritten against the durable hooks: `[data-testid="mainFeed"]`, `[componentkey^="container-update-list"]`, `[componentkey^="feed-commentary"]`; author anchored on the actor avatar (the first `/in/` link is often the social-context header); `blob:` video URLs dropped (unusable outside the page session).

Verified with a full run (`2026-07-14/job_093847`): x 56 · threads 62 · instagram 52 · youtube 31 · linkedin 5 posts. All media in its own platform folder (was 100% misrouted).

**LinkedIn caveats (by design, not bugs):** most cards no longer carry a `urn:li:activity`, so post IDs fall back to LinkedIn's opaque per-post key and `url` is empty for those posts (no canonical link to fabricate). LinkedIn also visibly throttles repeated automated loads — the feed thinned from 5 posts to 2 across back-to-back runs — so it yields far fewer posts than other platforms.

Also fixed: `src/collect.py` minted a separate job id per platform, scattering one CLI run across several job folders. All platforms in one invocation now share a job. Added `--output-dir`.

## Recently Completed (2026-07-12) — branch `feature/publish-feed`

- **Feed publishing to Cloudflare R2:** `skills/focus-lab-curator/publish.py` uploads a curated job (hosted viewer + posts.json + media) to an R2 bucket via the S3 API, so the daily feed is scrollable from a phone URL. Wired into the curator skill: when `<workspace>/publish.env` exists, the skill publishes automatically after filtering.
- **Free-tier guards:** media included in score order until `DAILY_BUDGET_MB` (500) is spent; videos over `MAX_VIDEO_MB` (50) and all YouTube videos become tap-through link-out cards to the original post; days older than `RETENTION_DAYS` (14) pruned from the bucket. Worst case ≈ 7 GB vs the 10 GB free tier.
- **Hosted viewer** (`skills/focus-lab-curator/hosted.html`): adapted from `viewer/mobile.html` — fetches `feed/index.json` + per-day `posts.json` from the same origin (no CORS), day picker, `hosted_media` rendering with link-out cards, per-day scroll anchor memory. Verified with Playwright against the real 2026-07-12 job (109 posts, 500 MB media, zero JS errors).
- `--dry-run` builds `<workspace>/publish_preview/` (symlinked media) for local testing without credentials.
- Setup guide in skill `install.md` § Publishing; `publish.env` + `publish_preview/` gitignored.
- **Zero-dependency uploader:** the R2 client is stdlib-only (SigV4 signing via hmac/hashlib + urllib) so the skill keeps its "never install anything" rule. Signer verified byte-for-byte against botocore on 5 request shapes; full publish flow (upload, index update, retention prune) exercised against a fake local S3 server.

### Waiting on user

- Cloudflare account + R2 bucket + API token → fill `<workspace>/publish.env` (see install.md), then the first real publish. Nothing to install.

### Observed during work (not yet fixed)

- **YouTube dates:** 10 of 31 posts have an empty `created_at` (matches known issue #1 below).
- **Threads parser noise:** `Error parsing edge: 'NoneType' object has no attribute 'get'` on a few edges each run — non-fatal, posts still parse.

## Recently Completed (2026-05-02)

- **LinkedIn collector:** new `src/platforms/linkedin/` module wired through CLI, FastAPI, and the desktop UI (Platforms, Onboarding, Settings, Collect tabs). DOM-based extractor against `feed-shared-update-v2` cards; Voyager API responses archived as `raw/voyager_*.json` for future parsing.

## Recently Completed (2026-04-22)

- **Rebrand to Focus Lab — Vibe Scrolling:** browser title, Dock/bundle name, window title, sidebar logo
- **Multi-step onboarding:** welcome walkthrough (emoji pipeline) → Chromium install → connect ≥1 platform → pick export folder with auto-export toggle. Main app stays hidden until all four are satisfied
- **Curate with AI tab:** focused workflow — goals editor → pack check → agent picker (Claude Code/Cursor/Codex/other) with copy-paste launch + prompt → link to AI Curation
- **Export page:** clearer "choose day and platform" framing + floating bottom-right "Open folder" FAB

## Recently Completed (2026-03-23)

- **Desktop app (FastAPI + web UI):** Built `app/` directory with full web-based GUI
  - Platforms page: connect/disconnect accounts with Playwright browser auth
  - Collection page: trigger collection with per-platform max post config, live status polling
  - Viewer page: ported from viewer.html with platform tabs, sorting, media carousel, lightbox, replies
  - Export page: JSON, CSV, Focus Lab format export with run selection
  - Setup/onboarding: first-launch Chromium download with progress UI
- **Auth flow improvements:**
  - Replaced stdin `input()` with asyncio.Event-based signaling for GUI use
  - Browser disconnect detection (user closes window → auto-cancel)
  - Cancel button properly kills Playwright and allows reconnection
  - Login verification: navigates to login page with saved session, checks if redirected away (= logged in)
  - Bad sessions auto-deleted on verification failure
- **macOS .app bundle:** PyInstaller packaging with:
  - `focus-lab.spec` — spec file with all hidden imports and macOS BUNDLE config
  - `scripts/build-macos.sh` — one-command build + .dmg creation
  - Relocatable paths (`app/paths.py`): data in `~/Library/Application Support/`, browsers in `~/Library/Caches/`
  - ~64MB .dmg download, Chromium downloaded on first launch
- **Config/Data API:** Full REST API for config management, run listing, data serving

## Previously Completed (2026-03-22)

- Multi-platform architecture: `src/platforms/{twitter,threads,instagram,youtube}/`
- Unified Post model, CLI, per-run storage
- Twitter: GraphQL interception, video download, reply collection
- Threads: GraphQL interception, feed parsing, reply collection
- Instagram: Hybrid HTML + GraphQL, carousel support, comments
- YouTube: ytInitialData + browse API, videos + Shorts
- Viewer: Multi-platform tabs, carousel, lightbox, video autoplay, replies

## Known Issues / Next Steps

### Small Fixes
1. **YouTube date not captured correctly** — shows "Invalid Date" in viewer (date parsing issue)
2. **YouTube Shorts missing author** — shows "Unknown" for Shorts content
3. **Viewer left nav scrolls with content** — sidebar should be fixed/sticky, not scroll
4. **Viewer posts too wide** — posts take full width, need narrower layout or multi-column

### Medium Work
5. **Collection history hierarchy** — group runs by date and/or platform instead of flat list
6. **Export UI organization** — better structure for selecting and managing exports

### Larger Work
7. **Design system overhaul** — current UI is functional but needs proper design principles, typography, spacing, color refinement, and polished components
8. **LLM-powered reply targeting** — replace naive "most replies" with AI triage
9. **AI curation layer** — rage bait classification, goal alignment scoring

## Blockers

- (none)
