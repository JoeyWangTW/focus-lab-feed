"""Scroll automation — timing, depth, stop conditions."""

import asyncio
import random
import time
from datetime import datetime

TWITTER_DATE_FORMAT = "%a %b %d %H:%M:%S %z %Y"


def _parse_twitter_date(date_str: str) -> datetime | None:
    """Parse Twitter's date format into a datetime, or None if unparseable."""
    try:
        return datetime.strptime(date_str, TWITTER_DATE_FORMAT)
    except (ValueError, TypeError):
        return None


def _has_tweet_older_than(tweets, oldest_dt: datetime) -> bool:
    """Check if any tweet has a created_at date older than the threshold."""
    for tweet in tweets:
        dt = _parse_twitter_date(tweet.created_at)
        if dt and dt.date() < oldest_dt.date():
            return True
    return False


async def scroll_feed(page, delay_min: float = 2.0, delay_max: float = 5.0):
    """Scroll to the bottom of loaded content to trigger infinite scroll loading."""
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    delay = random.uniform(delay_min, delay_max)
    await asyncio.sleep(delay)
    return delay


async def scroll_loop(
    page,
    interceptor,
    *,
    delay_min: float = 2.0,
    delay_max: float = 5.0,
    max_tweets: int = 50,
    max_minutes: float | None = None,
    oldest_tweet_date: str | None = None,
    stale_limit: int = 3,
) -> dict:
    """Scroll the feed in a loop, collecting tweets via the interceptor.

    Stop conditions (whichever triggers first):
    - max_tweets: stop when this many tweets are collected
    - max_minutes: stop after this many minutes of scrolling
    - oldest_tweet_date: stop when a tweet older than this date (YYYY-MM-DD) is found
    - stale_limit: stop after N consecutive scrolls with no new tweets

    Returns a dict with scroll stats: scroll_count, total_tweets, stop_reason.
    """
    start = time.monotonic()
    scroll_count = 0
    stale_scrolls = 0

    # Parse oldest_tweet_date once
    oldest_dt = None
    if oldest_tweet_date:
        oldest_dt = datetime.fromisoformat(oldest_tweet_date)

    prev_tweet_count = len(interceptor.parse_all_tweets(skip_ads=True))

    conditions = [f"max_tweets={max_tweets}"]
    if max_minutes is not None:
        conditions.append(f"max_minutes={max_minutes}")
    if oldest_tweet_date:
        conditions.append(f"oldest_tweet_date={oldest_tweet_date}")
    print(f"[scroller] Starting scroll loop ({', '.join(conditions)}, stale_limit={stale_limit})")
    print(f"[scroller] Tweets from initial load: {prev_tweet_count}")

    while True:
        # Check time limit
        if max_minutes is not None:
            elapsed_min = (time.monotonic() - start) / 60
            if elapsed_min >= max_minutes:
                reason = f"Reached max_minutes limit ({max_minutes} min)"
                print(f"[scroller] Stopping: {reason}")
                return {
                    "scroll_count": scroll_count,
                    "total_tweets": prev_tweet_count,
                    "stop_reason": reason,
                }

        # Check tweet limit before scrolling
        if prev_tweet_count >= max_tweets:
            reason = f"Reached max_tweets limit ({max_tweets})"
            print(f"[scroller] Stopping: {reason}")
            return {
                "scroll_count": scroll_count,
                "total_tweets": prev_tweet_count,
                "stop_reason": reason,
            }

        # Check oldest_tweet_date before scrolling
        if oldest_dt is not None:
            tweets = interceptor.parse_all_tweets(skip_ads=True)
            if _has_tweet_older_than(tweets, oldest_dt):
                reason = f"Found tweet older than {oldest_tweet_date}"
                print(f"[scroller] Stopping: {reason}")
                return {
                    "scroll_count": scroll_count,
                    "total_tweets": len(tweets),
                    "stop_reason": reason,
                }

        # Scroll once
        delay = await scroll_feed(page, delay_min, delay_max)
        scroll_count += 1

        # Wait for GraphQL responses to arrive after scroll
        await page.wait_for_timeout(3000)

        # Count tweets now
        current_tweet_count = len(interceptor.parse_all_tweets(skip_ads=True))
        new_tweets = current_tweet_count - prev_tweet_count

        print(
            f"[scroller] Scroll #{scroll_count}: "
            f"+{new_tweets} new tweets | "
            f"total={current_tweet_count} | "
            f"delay={delay:.1f}s"
        )

        if new_tweets == 0:
            stale_scrolls += 1
            print(f"[scroller] No new tweets ({stale_scrolls}/{stale_limit} stale scrolls)")
            if stale_scrolls >= stale_limit:
                reason = f"No new tweets after {stale_limit} consecutive scrolls"
                print(f"[scroller] Stopping: {reason}")
                return {
                    "scroll_count": scroll_count,
                    "total_tweets": current_tweet_count,
                    "stop_reason": reason,
                }
        else:
            stale_scrolls = 0

        prev_tweet_count = current_tweet_count
