"""GraphQL response interception and parsing for Threads."""

import json
import re
from datetime import datetime
from pathlib import Path

from src.models import Post


class ResponseInterceptor:
    """Intercepts and stores Threads GraphQL API responses."""

    GRAPHQL_PATTERN = re.compile(r"threads\.com/graphql/query")

    def __init__(self, run_dir: Path):
        self.responses: list[dict] = []
        self.run_dir = run_dir

    async def handle_response(self, response):
        if not self.GRAPHQL_PATTERN.search(response.url):
            return

        try:
            body = await response.json()
            status = response.status

            # Only capture feed responses (have feedData)
            data = body.get("data", {})
            feed_data = data.get("feedData") or data.get("data", {}).get("feedData")
            if not feed_data:
                return

            self.responses.append(body)

            raw_dir = self.run_dir / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%H%M%S_%f")
            raw_path = raw_dir / f"threads_feed_{timestamp}.json"
            raw_path.write_text(json.dumps(body, indent=2))

            edges = feed_data.get("edges", [])
            size = len(json.dumps(body))
            print(f"[interceptor:threads] Feed response | status={status} | size={size:,}B | edges={len(edges)}")

        except Exception as e:
            print(f"[interceptor:threads] Error processing response: {e}")

    def parse_all_posts(self, skip_ads: bool = True) -> list[Post]:
        posts_by_id: dict[str, Post] = {}
        for response_body in self.responses:
            data = response_body.get("data", {})
            feed_data = data.get("feedData") or data.get("data", {}).get("feedData")
            if not feed_data:
                continue

            for edge in feed_data.get("edges", []):
                post = self._parse_edge(edge)
                if post and post.id not in posts_by_id:
                    posts_by_id[post.id] = post

        posts = list(posts_by_id.values())
        print(f"[parser:threads] Parsed {len(posts)} unique posts from {len(self.responses)} response(s)")
        return posts

    def _parse_edge(self, edge: dict) -> Post | None:
        try:
            node = edge.get("node", {})
            thread = node.get("text_post_app_thread", {})
            items = thread.get("thread_items", [])
            if not items:
                return None

            item = items[0]
            post_data = item.get("post", {})
            if not post_data:
                return None

            user = post_data.get("user", {})
            username = user.get("username", "")
            full_name = user.get("full_name", username)

            caption = post_data.get("caption", {})
            text = caption.get("text", "") if caption else ""

            code = post_data.get("code", "")
            post_id = str(post_data.get("pk", code))

            taken_at = post_data.get("taken_at", 0)
            created_at = datetime.fromtimestamp(taken_at).isoformat() if taken_at else ""

            like_count = post_data.get("like_count", 0)
            tp_info = post_data.get("text_post_app_info", {})
            reply_count = tp_info.get("direct_reply_count", 0)
            repost_count = tp_info.get("repost_count", 0)
            quote_count = tp_info.get("quote_count", 0)

            # Media
            image_urls = []
            video_urls = []

            media_type = post_data.get("media_type")

            # Carousel
            carousel = post_data.get("carousel_media", [])
            if carousel:
                for cm in carousel:
                    self._extract_media(cm, image_urls, video_urls)
            else:
                self._extract_media(post_data, image_urls, video_urls)

            # Ad detection
            is_ad = bool(post_data.get("is_paid_partnership"))

            return Post(
                id=post_id,
                platform="threads",
                text=text,
                author_handle=username,
                author_name=full_name,
                created_at=created_at,
                url=f"https://www.threads.net/@{username}/post/{code}" if code else "",
                likes=like_count,
                reposts=repost_count,
                replies=reply_count,
                quotes=quote_count,
                media_urls=image_urls,
                video_urls=video_urls,
                is_ad=is_ad,
            )

        except Exception as e:
            print(f"[parser:threads] Error parsing edge: {e}")
            return None

    def _extract_media(self, media_data: dict, image_urls: list, video_urls: list):
        """Extract image and video URLs from a media object."""
        video_versions = media_data.get("video_versions", [])
        if video_versions:
            # Pick highest quality video
            best = max(video_versions, key=lambda v: v.get("width", 0) * v.get("height", 0))
            url = best.get("url", "")
            if url:
                video_urls.append(url)
        else:
            image_versions = media_data.get("image_versions2", {})
            candidates = image_versions.get("candidates", [])
            if candidates:
                # Pick largest image
                best = max(candidates, key=lambda c: c.get("width", 0) * c.get("height", 0))
                url = best.get("url", "")
                if url:
                    image_urls.append(url)
