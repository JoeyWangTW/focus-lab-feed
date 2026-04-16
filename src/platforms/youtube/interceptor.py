"""YouTube feed data extraction from ytInitialData and browse API responses."""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

from src.models import Post


class ResponseInterceptor:
    """Extracts YouTube feed data from page JS and intercepts browse API responses."""

    def __init__(self, run_dir: Path):
        self.posts_by_id: dict[str, Post] = {}
        self.run_dir = run_dir

    async def extract_from_page(self, page):
        """Extract feed data from ytInitialData embedded in the page."""
        yt_data = await page.evaluate("window.ytInitialData")
        if not yt_data:
            print("[interceptor:youtube] No ytInitialData found")
            return

        raw_dir = self.run_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%H%M%S_%f")
        raw_path = raw_dir / f"ytInitialData_{timestamp}.json"
        raw_path.write_text(json.dumps(yt_data, indent=2))

        found = 0
        try:
            contents = (
                yt_data.get("contents", {})
                .get("twoColumnBrowseResultsRenderer", {})
                .get("tabs", [{}])[0]
                .get("tabRenderer", {})
                .get("content", {})
                .get("richGridRenderer", {})
                .get("contents", [])
            )

            for item in contents:
                posts = self._parse_grid_item(item)
                for post in posts:
                    if post.id not in self.posts_by_id:
                        self.posts_by_id[post.id] = post
                        found += 1
        except Exception as e:
            print(f"[interceptor:youtube] Error parsing ytInitialData: {e}")

        if found:
            print(f"[interceptor:youtube] Extracted {found} items from page")

    async def handle_response(self, response):
        """Intercept browse API continuation responses."""
        if "youtubei/v1/browse" not in response.url or response.status != 200:
            return

        try:
            data = await response.json()
            actions = data.get("onResponseReceivedActions", [])
            found = 0

            for action in actions:
                items = action.get("appendContinuationItemsAction", {}).get("continuationItems", [])
                for item in items:
                    posts = self._parse_grid_item(item)
                    for post in posts:
                        if post.id not in self.posts_by_id:
                            self.posts_by_id[post.id] = post
                            found += 1

            if found:
                print(f"[interceptor:youtube] Browse continuation: +{found} items")

                raw_dir = self.run_dir / "raw"
                raw_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%H%M%S_%f")
                raw_path = raw_dir / f"browse_{timestamp}.json"
                raw_path.write_text(json.dumps(data, indent=2))

        except Exception as e:
            print(f"[interceptor:youtube] Error processing browse response: {e}")

    def parse_all_posts(self, skip_ads: bool = True) -> list[Post]:
        posts = [p for p in self.posts_by_id.values() if not (skip_ads and p.is_ad)]
        videos = [p for p in posts if p.platform_data.get("type") == "video"]
        shorts = [p for p in posts if p.platform_data.get("type") == "short"]
        print(f"[parser:youtube] {len(posts)} items ({len(videos)} videos, {len(shorts)} shorts)")
        return posts

    async def enrich_missing_authors(self, posts: list[Post]) -> list[Post]:
        """Use YouTube oEmbed API to fill in missing author names for shorts/videos."""
        missing = [p for p in posts if not p.author_name]
        if not missing:
            return posts

        print(f"[enricher:youtube] Enriching {len(missing)} posts missing author info via oEmbed...")

        enriched = 0
        # Process in batches of 5 to avoid hammering the API
        for i in range(0, len(missing), 5):
            batch = missing[i:i+5]
            tasks = [self._fetch_oembed(p) for p in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for post, result in zip(batch, results):
                if isinstance(result, dict):
                    if result.get("author_name"):
                        post.author_name = result["author_name"]
                        post.author_handle = result.get("author_handle", result["author_name"])
                        enriched += 1
            # Small delay between batches
            if i + 5 < len(missing):
                await asyncio.sleep(0.5)

        print(f"[enricher:youtube] Enriched {enriched}/{len(missing)} posts with author info")
        return posts

    async def _fetch_oembed(self, post: Post) -> dict:
        """Fetch oEmbed data for a YouTube video/short."""
        url = f"https://www.youtube.com/oembed?url={post.url}&format=json"
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: urlopen(req, timeout=10))
            data = json.loads(response.read())
            result = {"author_name": data.get("author_name", "")}
            # Extract handle from author_url (e.g., https://www.youtube.com/@handle)
            author_url = data.get("author_url", "")
            if "/@" in author_url:
                result["author_handle"] = author_url.split("/@")[-1]
            return result
        except Exception as e:
            print(f"[enricher:youtube] oEmbed failed for {post.id}: {e}")
            return {}

    def _parse_grid_item(self, item: dict) -> list[Post]:
        """Parse a richGridRenderer item (video, shorts shelf, or ad)."""
        posts = []

        # Regular video via richItemRenderer
        rir = item.get("richItemRenderer", {})
        if rir:
            content = rir.get("content", {})

            # lockupViewModel = regular video
            lvm = content.get("lockupViewModel")
            if lvm:
                post = self._parse_lockup_video(lvm)
                if post:
                    posts.append(post)

            # adSlotRenderer = ad
            if content.get("adSlotRenderer"):
                pass  # skip ads

        # Shorts shelf via richSectionRenderer
        rsr = item.get("richSectionRenderer", {})
        if rsr:
            shelf = rsr.get("content", {}).get("richShelfRenderer", {})
            title = shelf.get("title", {}).get("runs", [{}])[0].get("text", "")
            if title == "Shorts":
                for shelf_item in shelf.get("contents", []):
                    slvm = shelf_item.get("richItemRenderer", {}).get("content", {}).get("shortsLockupViewModel")
                    if slvm:
                        post = self._parse_short(slvm)
                        if post:
                            posts.append(post)

        return posts

    def _parse_lockup_video(self, lvm: dict) -> Post | None:
        """Parse a lockupViewModel into a Post."""
        try:
            video_id = lvm.get("contentId", "")
            if not video_id:
                return None

            meta = lvm.get("metadata", {}).get("lockupMetadataViewModel", {})
            title = meta.get("title", {}).get("content", "")

            # Channel name and view count from metadata rows
            channel = ""
            views_text = ""
            time_text = ""
            content_meta = meta.get("metadata", {}).get("contentMetadataViewModel", {})
            for row in content_meta.get("metadataRows", []):
                parts = row.get("metadataParts", [])
                for part in parts:
                    text = part.get("text", {}).get("content", "")
                    if not text:
                        continue
                    if "view" in text.lower() or "watching" in text.lower():
                        views_text = text
                    elif "ago" in text.lower() or "hour" in text.lower() or "day" in text.lower():
                        time_text = text
                    elif not channel:
                        channel = text

            # Thumbnail URL
            thumbnail = ""
            thumb_data = lvm.get("contentImage", {}).get("collectionThumbnailViewModel", {})
            primary = thumb_data.get("primaryThumbnail", {}).get("thumbnailViewModel", {})
            sources = primary.get("image", {}).get("sources", [])
            if sources:
                # Pick largest thumbnail
                best = max(sources, key=lambda s: s.get("width", 0))
                thumbnail = best.get("url", "")

            # Duration
            duration = ""
            time_overlay = thumb_data.get("primaryThumbnail", {}).get("thumbnailViewModel", {}).get("overlays", [])
            for overlay in time_overlay:
                tov = overlay.get("thumbnailOverlayBadgeViewModel", {})
                badges = tov.get("thumbnailBadges", [])
                for badge in badges:
                    bvm = badge.get("thumbnailBadgeViewModel", {})
                    duration = bvm.get("text", "")

            return Post(
                id=video_id,
                platform="youtube",
                text=title,
                author_handle=channel,
                author_name=channel,
                created_at=time_text,
                url=f"https://www.youtube.com/watch?v={video_id}",
                likes=0,
                media_urls=[thumbnail] if thumbnail else [],
                platform_data={
                    "type": "video",
                    "video_id": video_id,
                    "views": views_text,
                    "duration": duration,
                    "embed_url": f"https://www.youtube.com/embed/{video_id}",
                },
            )
        except Exception as e:
            print(f"[parser:youtube] Error parsing video: {e}")
            return None

    def _parse_short(self, slvm: dict) -> Post | None:
        """Parse a shortsLockupViewModel into a Post."""
        try:
            # Video ID from onTap command
            on_tap = slvm.get("onTap", {}).get("innertubeCommand", {})
            reel_ep = on_tap.get("reelWatchEndpoint", {})
            video_id = reel_ep.get("videoId", "")

            if not video_id:
                # Try inlinePlayerData
                ipd = slvm.get("inlinePlayerData", {}).get("onVisible", {}).get("innertubeCommand", {})
                video_id = ipd.get("watchEndpoint", {}).get("videoId", "")

            if not video_id:
                return None

            # Title from accessibilityText (contains title + view count)
            acc_text = slvm.get("accessibilityText", "")
            # Parse: "Title here, X views - play Short"
            title = acc_text.split(", ")[0] if ", " in acc_text else acc_text

            # Views from overlay metadata
            views_text = slvm.get("overlayMetadata", {}).get("secondaryText", {}).get("content", "")

            # Thumbnail
            thumbnail = ""
            thumb_sources = slvm.get("inlinePlayerData", {}).get("onVisible", {}).get("innertubeCommand", {}).get("watchEndpoint", {})
            # Try getting thumbnail from entity
            ipd = slvm.get("inlinePlayerData", {})

            return Post(
                id=video_id,
                platform="youtube",
                text=title,
                author_handle="",
                author_name="",
                created_at="",
                url=f"https://www.youtube.com/shorts/{video_id}",
                likes=0,
                platform_data={
                    "type": "short",
                    "video_id": video_id,
                    "views": views_text,
                    "embed_url": f"https://www.youtube.com/embed/{video_id}",
                },
            )
        except Exception as e:
            print(f"[parser:youtube] Error parsing short: {e}")
            return None
