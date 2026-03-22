"""Feed data extraction and interception for Instagram.

Instagram embeds initial feed data in <script type="application/json"> tags in the HTML.
Subsequent pages may come via graphql/query responses.
Both sources are parsed into Post objects.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from src.models import Post

FEED_CONNECTION_KEY = "xdt_api__v1__feed__timeline__connection"


class ResponseInterceptor:
    """Extracts Instagram feed data from HTML and intercepts GraphQL responses."""

    GRAPHQL_PATTERN = re.compile(r"instagram\.com/graphql/query")

    def __init__(self, run_dir: Path):
        self.posts_by_id: dict[str, Post] = {}
        self.response_count = 0
        self.run_dir = run_dir

    async def extract_from_page(self, page):
        """Extract feed data from the page's embedded JSON script tags."""
        html = await page.content()

        scripts = re.findall(
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )

        found = 0
        for script_content in scripts:
            try:
                data = json.loads(script_content)
                posts = self._find_feed_posts(data)
                for post in posts:
                    if post.id not in self.posts_by_id:
                        self.posts_by_id[post.id] = post
                        found += 1
            except (json.JSONDecodeError, TypeError):
                continue

        if found:
            print(f"[interceptor:instagram] Extracted {found} posts from page HTML")

            raw_dir = self.run_dir / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%H%M%S_%f")
            raw_path = raw_dir / f"ig_html_extract_{timestamp}.json"
            raw_path.write_text(json.dumps(
                [{"id": p.id, "author": p.author_handle, "text": p.text[:100]}
                 for p in list(self.posts_by_id.values())[-found:]],
                indent=2,
            ))

    async def handle_response(self, response):
        """Intercept GraphQL responses for additional feed pages."""
        if not self.GRAPHQL_PATTERN.search(response.url):
            return

        try:
            body = await response.json()
            data = body.get("data", {})
            conn = data.get(FEED_CONNECTION_KEY)
            if not conn:
                return

            self.response_count += 1
            edges = conn.get("edges", [])
            found = 0

            for edge in edges:
                post = self._parse_feed_edge(edge)
                if post and post.id not in self.posts_by_id:
                    self.posts_by_id[post.id] = post
                    found += 1

            if found:
                print(f"[interceptor:instagram] GraphQL response: +{found} new posts")

                raw_dir = self.run_dir / "raw"
                raw_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%H%M%S_%f")
                raw_path = raw_dir / f"ig_graphql_{timestamp}.json"
                raw_path.write_text(json.dumps(body, indent=2))

        except Exception as e:
            print(f"[interceptor:instagram] Error processing response: {e}")

    def parse_all_posts(self, skip_ads: bool = True) -> list[Post]:
        posts = [p for p in self.posts_by_id.values() if not (skip_ads and p.is_ad)]
        print(f"[parser:instagram] {len(posts)} unique posts collected")
        return posts

    def _find_feed_posts(self, data, depth=0) -> list[Post]:
        """Recursively search JSON for feed connection data."""
        posts = []
        if depth > 10:
            return posts

        if isinstance(data, dict):
            # Check if this dict has the feed connection
            conn = data.get(FEED_CONNECTION_KEY)
            if conn and isinstance(conn, dict):
                for edge in conn.get("edges", []):
                    post = self._parse_feed_edge(edge)
                    if post:
                        posts.append(post)

            # Recurse into values
            for v in data.values():
                posts.extend(self._find_feed_posts(v, depth + 1))

        elif isinstance(data, list):
            for item in data:
                posts.extend(self._find_feed_posts(item, depth + 1))

        return posts

    def _parse_feed_edge(self, edge: dict) -> Post | None:
        """Parse an Instagram feed edge into a Post."""
        try:
            node = edge.get("node", {})
            if not node:
                return None

            # Instagram feed items can have media in different locations
            media = node.get("media")
            if not media:
                # Try explore_story.media path
                explore = node.get("explore_story", {})
                if explore:
                    media = explore.get("media")

            if not media or not isinstance(media, dict):
                return None

            # Skip if no code (not a real post)
            code = media.get("code", "")
            if not code:
                return None

            owner = media.get("owner", {}) or {}
            username = owner.get("username", "")
            full_name = owner.get("full_name", username)

            caption_data = media.get("caption", {})
            text = caption_data.get("text", "") if caption_data else ""

            post_id = str(media.get("pk", code))
            taken_at = media.get("taken_at", 0)
            created_at = datetime.fromtimestamp(taken_at).isoformat() if taken_at else ""

            like_count = media.get("like_count", 0)
            comment_count = media.get("comment_count", 0)

            # Media
            image_urls = []
            video_urls = []

            # Carousel
            carousel = media.get("carousel_media", [])
            if carousel:
                for cm in carousel:
                    self._extract_media(cm, image_urls, video_urls)
            else:
                self._extract_media(media, image_urls, video_urls)

            # Check for ad
            is_ad = bool(media.get("ad_id") or media.get("is_paid_partnership"))

            return Post(
                id=post_id,
                platform="instagram",
                text=text,
                author_handle=username,
                author_name=full_name,
                created_at=created_at,
                url=f"https://www.instagram.com/p/{code}/" if code else "",
                likes=like_count,
                replies=comment_count,
                media_urls=image_urls,
                video_urls=video_urls,
                is_ad=is_ad,
            )

        except Exception as e:
            print(f"[parser:instagram] Error parsing edge: {e}")
            return None

    def _extract_media(self, media_data: dict, image_urls: list, video_urls: list):
        """Extract image and video URLs from a media object."""
        video_versions = media_data.get("video_versions", [])
        if video_versions:
            best = max(video_versions, key=lambda v: v.get("width", 0) * v.get("height", 0))
            url = best.get("url", "")
            if url:
                video_urls.append(url)
        else:
            image_versions = media_data.get("image_versions2", {})
            candidates = image_versions.get("candidates", [])
            if candidates:
                best = max(candidates, key=lambda c: c.get("width", 0) * c.get("height", 0))
                url = best.get("url", "")
                if url:
                    image_urls.append(url)
