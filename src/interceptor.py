"""GraphQL response interception and parsing."""

import json
import re
from datetime import datetime
from pathlib import Path

from src.models import Tweet


class ResponseInterceptor:
    """Intercepts and stores Twitter GraphQL API responses."""

    GRAPHQL_PATTERN = re.compile(r"/i/api/graphql/.*/Home")

    def __init__(self, output_dir: str = "feed_data"):
        self.responses: list[dict] = []
        self.output_dir = Path(output_dir)

    async def handle_response(self, response):
        """Callback for page.on('response') — captures matching GraphQL responses."""
        if not self.GRAPHQL_PATTERN.search(response.url):
            return

        try:
            body = await response.json()
            endpoint = response.url.split("/")[-1].split("?")[0]
            status = response.status

            self.responses.append(body)

            # Save raw response for debugging
            today = datetime.now().strftime("%Y-%m-%d")
            raw_dir = self.output_dir / today / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%H%M%S_%f")
            raw_path = raw_dir / f"{endpoint}_{timestamp}.json"
            raw_path.write_text(json.dumps(body, indent=2))

            # Count tweet entries
            tweet_count = self._count_entries(body)
            size = len(json.dumps(body))

            print(
                f"[interceptor] {endpoint} | status={status} | "
                f"size={size:,}B | entries={tweet_count}"
            )

        except Exception as e:
            print(f"[interceptor] Error processing response: {e}")

    def _count_entries(self, body: dict) -> int:
        """Count tweet entries in a GraphQL response."""
        try:
            instructions = (
                body.get("data", {})
                .get("home", {})
                .get("home_timeline_urt", {})
                .get("instructions", [])
            )
            count = 0
            for instruction in instructions:
                entries = instruction.get("entries", [])
                count += len(entries)
            return count
        except (AttributeError, TypeError):
            return 0

    def parse_all_tweets(self, skip_ads: bool = True) -> list[Tweet]:
        """Parse all captured responses into Tweet objects.

        Returns deduplicated list of tweets across all responses.
        """
        tweets_by_id: dict[str, Tweet] = {}
        ads_skipped = 0
        dupes_within_run = 0

        for response_body in self.responses:
            entries = self._extract_entries(response_body)
            for entry in entries:
                tweet = self._parse_entry(entry)
                if tweet is None:
                    continue
                if skip_ads and tweet.is_ad:
                    ads_skipped += 1
                    continue
                if tweet.id in tweets_by_id:
                    dupes_within_run += 1
                else:
                    tweets_by_id[tweet.id] = tweet

        tweets = list(tweets_by_id.values())
        print(
            f"[parser] Parsed {len(tweets)} unique tweets "
            f"({dupes_within_run} within-run duplicates, "
            f"{ads_skipped} ads skipped) from {len(self.responses)} response(s)"
        )
        return tweets

    def _extract_entries(self, body: dict) -> list[dict]:
        """Extract timeline entries from a GraphQL response body."""
        try:
            instructions = (
                body.get("data", {})
                .get("home", {})
                .get("home_timeline_urt", {})
                .get("instructions", [])
            )
            entries = []
            for instruction in instructions:
                entries.extend(instruction.get("entries", []))
            return entries
        except (AttributeError, TypeError):
            return []

    def _parse_entry(self, entry: dict) -> Tweet | None:
        """Parse a single timeline entry into a Tweet, or None if not a tweet."""
        try:
            content = entry.get("content", {})
            item_content = content.get("itemContent", {})

            # Only process tweet items (skip cursors, modules, etc.)
            item_type = item_content.get("itemType", "")
            if item_type != "TimelineTweet":
                return None

            # Check if promoted/ad
            is_ad = "promotedMetadata" in item_content

            # Navigate to the tweet result
            tweet_result = item_content.get("tweet_results", {}).get("result", {})
            if not tweet_result:
                return None

            return self._parse_tweet_result(tweet_result, is_ad=is_ad)

        except Exception as e:
            entry_id = entry.get("entryId", "unknown")
            print(f"[parser] Skipping entry {entry_id}: {e}")
            return None

    def _parse_tweet_result(
        self, result: dict, is_ad: bool = False
    ) -> Tweet | None:
        """Parse a tweet_results.result object into a Tweet."""
        try:
            # Handle TweetWithVisibilityResults wrapper
            typename = result.get("__typename", "")
            if typename == "TweetWithVisibilityResults":
                result = result.get("tweet", {})
                if not result:
                    return None

            tweet_id = result.get("rest_id", "")
            if not tweet_id:
                return None

            legacy = result.get("legacy", {})
            core = result.get("core", {})

            # Extract author info
            author_handle, author_name = self._extract_author(core)

            # Check for retweet
            is_retweet = False
            original_author = None
            rt_result = legacy.get("retweeted_status_result", {}).get("result", {})
            if rt_result:
                is_retweet = True
                # The outer tweet's author is the retweeter;
                # parse the inner tweet for the actual content
                original_author = author_handle
                inner = self._parse_tweet_result(rt_result)
                if inner:
                    return Tweet(
                        id=tweet_id,
                        text=inner.text,
                        author_handle=inner.author_handle,
                        author_name=inner.author_name,
                        created_at=inner.created_at,
                        likes=inner.likes,
                        retweets=inner.retweets,
                        replies=inner.replies,
                        quotes=inner.quotes,
                        media_urls=inner.media_urls,
                        is_retweet=True,
                        original_author=original_author,
                        is_ad=is_ad,
                    )

            # Extract engagement metrics
            text = legacy.get("full_text", "")
            created_at = legacy.get("created_at", "")
            likes = legacy.get("favorite_count", 0)
            retweets_count = legacy.get("retweet_count", 0)
            replies_count = legacy.get("reply_count", 0)
            quotes_count = legacy.get("quote_count", 0)

            # Extract media URLs from extended_entities (preferred) or entities
            media_urls = self._extract_media_urls(legacy)

            return Tweet(
                id=tweet_id,
                text=text,
                author_handle=author_handle,
                author_name=author_name,
                created_at=created_at,
                likes=likes,
                retweets=retweets_count,
                replies=replies_count,
                quotes=quotes_count,
                media_urls=media_urls,
                is_retweet=is_retweet,
                original_author=original_author,
                is_ad=is_ad,
            )

        except Exception as e:
            print(f"[parser] Error parsing tweet result: {e}")
            return None

    def _extract_author(self, core: dict) -> tuple[str, str]:
        """Extract (screen_name, display_name) from the core.user_results path."""
        try:
            user_legacy = (
                core.get("user_results", {})
                .get("result", {})
                .get("legacy", {})
            )
            return (
                user_legacy.get("screen_name", ""),
                user_legacy.get("name", ""),
            )
        except (AttributeError, TypeError):
            return ("", "")

    def _extract_media_urls(self, legacy: dict) -> list[str]:
        """Extract media URLs from tweet legacy data.

        Prefers extended_entities over entities for full media list.
        """
        urls = []
        # extended_entities has all media (entities only has first)
        media_source = legacy.get("extended_entities", legacy.get("entities", {}))
        media_items = media_source.get("media", [])

        for item in media_items:
            url = item.get("media_url_https", "")
            if url:
                urls.append(url)

        return urls
