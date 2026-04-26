# Focus Lab Feed — landing copy

> Source-of-truth copy for the landing page. Hand this to whoever is building
> the site. Placeholders in ALL_CAPS are meant to be filled in (e.g.
> `HOSTED_VIEWER_URL`).

---

## What Focus Lab Feed is

**One-liner.** Focus Lab Feed scrolls your social feeds for you, lets your own AI agent curate them against your goals, and hands you back a phone-sized feed you actually want to open.

**Longer version.** Modern social feeds are engineered to keep you there. The algorithm's goal (your attention) is not your goal (your life). Focus Lab Feed flips the loop: a desktop app does the scrolling, an AI agent you choose does the curation, and a lightweight phone viewer does the consuming. Everything you see on your phone is something *you* asked to see.

### The core insight

A feed that's *purely* useful — only goal-relevant content — is boring. People close it and go read a book. (Which is fine, but it's not the problem we're solving.) The secret sauce of social media is engagement: dopamine, laughter, surprise. That part matters.

So the curated feed has three goals, in order:

1. **Help you toward your goals** — the stuff you're actually trying to learn or build.
2. **Keep the joy** — humor, art, hobbies, whatever delights you. Non-negotiable.
3. **Drop the drain** — outrage loops, engagement bait, content that leaves you feeling worse.

That's the pitch. Not "quit social media." Not "productivity feed." A *joy-aware* feed that nudges you toward your goals.

---

## How it works

Three steps, three places:

**1. Collect (Mac desktop app).** A native macOS app opens a real browser under the hood and scrolls Twitter, Threads, Instagram, and YouTube for you. It captures posts, media, and engagement data — no API tokens, no rate limits, just automation of what you'd be doing anyway. Your session stays on your machine.

**2. Curate (your AI agent).** You export a *pack* — a folder with `posts.json`, the media files, and a Markdown skill file. You `cd` into it and run any agent you like: Claude Code, Cursor, Codex CLI, anything. You say "curate this feed." The agent reads your `goals.md` (or interviews you if you haven't written one), scores every post 0–100, and writes `posts.filtered.json`.

**3. Consume (in-app viewer).** Open the Focus Lab desktop app's **AI Curation** tab. The curated pack shows up automatically — scroll like any other feed, except the posts are yours, ordered by what matters to you, with the media inline and the scroll position remembered for next time.

---

## The viewer

### What it is

A single HTML file. No app install, no account, no backend. Drop a pack `.zip` onto it and it renders your feed.

### How it's built

- **Single file, vanilla JS.** No frameworks, no build step. ~600 lines of HTML/CSS/JS.
- **In-browser zip extraction.** [JSZip](https://stuk.github.io/jszip/) reads the pack; media files become blob URLs on the fly — nothing touches a server.
- **Post-anchor resume.** We save the `post_id` you were viewing (not pixel scroll) in `localStorage`, keyed per pack. When you come back, `scrollIntoView` drops you at the same post, even if images have loaded differently.
- **IndexedDB cache.** The whole extracted pack is stored locally, so reopening the viewer takes you straight back without re-importing.
- **IntersectionObserver autoplay.** Videos play muted as they enter the viewport, pause when off-screen. Tap to unmute.
- **CSS scroll-snap** for a native-feeling phone UX. Works on iOS Safari, Chrome, Firefox, and every desktop browser that supports `fetch` and Blob.
- **Rendering metadata.** If the pack contains a `posts.filtered.json` produced by the curator skill, each post shows its score + filter reason inline, so you can see *why* a post was ranked where it was.

### How to use it

1. Open `HOSTED_VIEWER_URL` in Safari on your phone.
2. Tap **Add to Home Screen** if you want it to feel like an app — no install, just a bookmark icon.
3. On your Mac, export a pack from the desktop app.
4. Back in the viewer, tap the drop zone → **Choose File** → pick the pack zip.
5. Scroll. Videos autoplay. Tap to unmute. Tap "Open on X" on any post to jump to the original.
6. Close the tab. Reopen later — the viewer remembers the pack and where you were.

Because everything runs client-side, the viewer works offline once the page is loaded. The zip, the media, and your scroll position all live in your browser's local storage.

---

## Try it

- **Hosted viewer** → `HOSTED_VIEWER_URL`
- **Desktop app** (macOS) → `APP_DOWNLOAD_URL`
- **Source code** → `GITHUB_URL`

---

## FAQ (optional for landing)

**Is this legal?** The desktop app runs a real browser under your account — same data you could see yourself, same terms of service. Nothing is re-hosted or republished.

**Which agents are supported?** Any agent that can follow Markdown instructions and read/write files. Tested with Claude Code, Cursor, Codex CLI, and the general "paste SKILL.md into system prompt" pattern.

**What's in a pack?** A folder: `posts.json`, `media/`, `viewer.html`, `goals.md`, and a README. Plain files, portable, scriptable.

**Does it work on Android?** The desktop app is macOS-only for now. The viewer works in any modern browser — Android Chrome is fine.

**What happens to my data?** It never leaves your devices. Collection happens locally. Curation happens in whichever AI agent you run. The viewer is static HTML.
