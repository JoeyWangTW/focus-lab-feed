# Inbox

Action items from co-founder discussions, standups, and meetings appear here.
Mark items as `[SEEN]` after reading them.

---

## From discussion: Focus Lab Social Media Data Collection (2026-02-22)
- [SEEN] Build proof of concept: Playwright + API interception to capture 50 tweets as structured JSON
- [SEEN] Download images from captured media URLs
- [SEEN] Study fa0311/twitter-openapi and proxidize/x-scraper for reference patterns
- [SEEN] Study MIT Gobo for alternative feed reader UX patterns
- [SEEN] Run captured tweets through Claude for rage bait classification as first curation test

## From planning session: VP Fiona Feed (2026-02-22)
- Sprint 1 plan locked in: S1.1 through S1.5 (scaffolding, session, interception, parsing, output)
- prd.json populated with 10 user stories across Sprint 1 and Sprint 2
- Technical decisions: Python, JSON files for storage, manual login with saved storage_state
- Branch name for Ralph loop: `milestone-1-twitter-collection`
- Ralph can begin executing stories in order -- S1.1 first

## From session: Reply capture & smart targeting (2026-03-22)
- Reply capture implemented: parallel tabs, top 20 tweets by reply count, up to 5 replies each
- **Future work: LLM-powered reply targeting** — Current approach naively picks tweets with most replies. Ideally an LLM (large or small/fast model) should triage which tweets are worth drilling into for replies, based on user interests, goals, or explicit input. This is the bridge between raw collection and Focus Lab's curation layer. Don't implement yet — just keep the simple "top N by reply count" approach for now.
- [ ] Design the LLM triage interface: what signals go in (tweet text, user profile, goals), what comes out (score/priority, reason)
- [ ] Evaluate small models (Haiku, local models) for fast triage at collection time vs. post-collection batch

## Action items (2026-02-23)
- [ ] Create a dedicated/throwaway email for Focus Lab testing
- [ ] Sign up for Twitter/X with the new email (dedicated test account)
- [ ] Sign up for other social media platforms as needed (future platforms)
- [ ] Run `python3 src/auth.py` to log in with the test account and save session
