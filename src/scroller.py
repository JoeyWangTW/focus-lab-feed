"""Scroll automation — timing, depth, stop conditions."""

import asyncio
import random


async def scroll_feed(page, delay_min: float = 2.0, delay_max: float = 5.0):
    """Scroll the page down once with a random delay."""
    await page.evaluate("window.scrollBy(0, window.innerHeight)")
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
    stale_limit: int = 3,
) -> dict:
    """Scroll the feed in a loop, collecting tweets via the interceptor.

    Returns a dict with scroll stats: scroll_count, total_tweets, stop_reason.
    """
    scroll_count = 0
    stale_scrolls = 0
    prev_tweet_count = len(interceptor.parse_all_tweets(skip_ads=True))

    print(f"[scroller] Starting scroll loop (max_tweets={max_tweets}, stale_limit={stale_limit})")
    print(f"[scroller] Tweets from initial load: {prev_tweet_count}")

    while True:
        # Check tweet limit before scrolling
        if prev_tweet_count >= max_tweets:
            reason = f"Reached max_tweets limit ({max_tweets})"
            print(f"[scroller] Stopping: {reason}")
            return {
                "scroll_count": scroll_count,
                "total_tweets": prev_tweet_count,
                "stop_reason": reason,
            }

        # Scroll once
        delay = await scroll_feed(page, delay_min, delay_max)
        scroll_count += 1

        # Wait briefly for GraphQL responses to arrive after scroll
        await page.wait_for_timeout(2000)

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
