# Project Status

**Last updated:** 2026-03-22

**Current state:** Multi-platform collection working (Twitter, Threads, Instagram, YouTube)

## Recently Completed (2026-03-22)

- **Multi-platform architecture:** Restructured from flat Twitter-only to `src/platforms/{twitter,threads,instagram,youtube}/`
- **Unified Post model:** Replaced Tweet with Post (platform, url, reposts, platform_data fields)
- **Unified CLI:** `python3 src/collect.py --platform twitter` or run all enabled
- **Per-run storage:** `feed_data/YYYY-MM-DD_HHMMSS_{platform}/posts.json`
- **Twitter:** Video download, author fix (API changed `screen_name` to `core`), reply collection via parallel tabs
- **Threads:** GraphQL interception, feed parsing, media download, reply collection via DOM scraping
- **Instagram:** Hybrid HTML extraction + GraphQL interception, carousel support, comment collection
- **YouTube:** ytInitialData extraction, regular videos + Shorts, iframe embeds (no download)
- **Viewer:** Multi-platform tabs, carousel media, lightbox, video autoplay, collapsible replies, ad badges
- **Scroll fix:** `scrollTo(document.body.scrollHeight)` instead of `scrollBy(innerHeight)` for proper infinite scroll

## Platform Collection Stats (typical run)

| Platform | Posts | Media | Replies | Time |
|----------|-------|-------|---------|------|
| Twitter | ~63 | ~17-56 | 100 (20 posts) | ~56s |
| Threads | ~60 | ~49 | 50 (10 posts) | ~72s |
| Instagram | ~52 | ~133 | 50 (10 posts) | ~130s |
| YouTube | ~39 (21 vids + 18 shorts) | embeds | — | ~33s |

## What's Next

- LLM-powered reply targeting (documented in inbox.md — replace naive "most replies" with AI triage)
- AI curation layer: run collected posts through Claude for rage bait classification, goal alignment
- Additional platforms as needed

## Blockers

- (none)
