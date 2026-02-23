# Roadmap

## Vision

An AI agent scrolls your social media so you never have to. It collects, curates, and delivers goal-aligned content -- replacing the toxic infinite scroll with intentional consumption.

## Core Hypothesis

If we collect social media feed data via browser automation and apply AI curation aligned to user goals, users will get more value in less time than scrolling themselves.

## Milestones

### Milestone 1: Twitter/X Feed Collection (Current -- Sprint 1-2)

**Goal:** Prove we can reliably capture a full page of tweets via API interception.

**Sprint 1: Session + Interception PoC (This Week)**
- [ ] S1.1 - Project scaffolding: `src/` structure, `requirements.txt`, `.gitignore`, `config.json`
- [ ] S1.2 - Session management: open browser, manual Twitter login, save `storage_state` to `session/twitter_state.json`
- [ ] S1.3 - GraphQL interception: load saved session, navigate to home feed, intercept `HomeTimeline` / `HomeLatestTimeline` responses
- [ ] S1.4 - Tweet parsing: extract tweet text, author handle, author display name, timestamp, engagement counts (likes, retweets, replies), media URLs from intercepted JSON
- [ ] S1.5 - Data output: save parsed tweets as structured JSON to `feed_data/YYYY-MM-DD/tweets.json`

**Sprint 2: Scroll + Media Download**
- [ ] S2.1 - Scroll automation: scroll the feed with randomized delays (2-5s), collect multiple pages of tweets
- [ ] S2.2 - Stop conditions: configurable stop (N tweets collected, M minutes elapsed, or date threshold reached)
- [ ] S2.3 - Deduplication: skip tweets already captured (by tweet ID) within and across sessions
- [ ] S2.4 - Image download: download images from `media_url_https` URLs to `feed_data/YYYY-MM-DD/media/`
- [ ] S2.5 - Run summary: print stats after collection (tweets captured, images downloaded, time elapsed, duplicates skipped)

**Done Criteria for Milestone 1:**
- Can capture 50+ tweets from home timeline as structured JSON
- Images downloaded locally and linked in tweet JSON
- Deduplication works across runs
- Human-readable summary printed at end

### Milestone 2: Curation Layer (Phase 2)
- [ ] Define user goal/interest model (JSON config to start)
- [ ] Rage bait / engagement bait classifier (Claude API call)
- [ ] Content quality scoring: informativeness, originality, relevance to user goals
- [ ] Ranked/filtered output: curated feed as HTML or simple web UI
- [ ] Agent-generated digest: "here is what matters from your feed today"

### Milestone 3: Multi-Platform (Phase 3)
- [ ] Instagram feed collection (same Playwright + interception pattern)
- [ ] Video download support via gallery-dl + yt-dlp
- [ ] Cross-platform deduplication and content merging
- [ ] Platform-agnostic data model

### Milestone 4: Personal Growth Engine (Phase 4)
- [ ] User goal onboarding flow
- [ ] Agent-researched content aligned to user goals (beyond social media)
- [ ] Daily digest with action items
- [ ] Monthly review and goal adjustment
- [ ] Interleaved educational content and calls to action

## Current Focus

Sprint 1 of Milestone 1 -- get the interception PoC working end-to-end.
