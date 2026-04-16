# Project Status

**Last updated:** 2026-03-23

**Current state:** Desktop app built and bundled as macOS .app with FastAPI backend, web UI, and PyWebView native window. Multi-platform collection working (Twitter, Threads, Instagram, YouTube).

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
