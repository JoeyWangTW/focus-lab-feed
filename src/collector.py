"""Main entry point — orchestrates collection run."""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path when run directly (python3 src/collector.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

from src.auth import load_session
from src.interceptor import ResponseInterceptor
from src.media_downloader import download_tweet_images
from src.scroller import scroll_loop
from src.storage import deduplicate_within_run, get_run_dir, save_run_summary, save_tweets, set_run_dir


def load_config() -> dict:
    """Load configuration from config.json."""
    config_path = Path("config.json")
    if not config_path.exists():
        print("[collector] config.json not found, using defaults")
        return {
            "scroll_delay_min": 2,
            "scroll_delay_max": 5,
            "max_tweets": 50,
            "max_minutes": 5,
            "output_dir": "feed_data",
        }
    return json.loads(config_path.read_text())


def print_summary(summary: dict):
    """Print a formatted collection run summary."""
    print("\n" + "=" * 50)
    print("  Collection Run Summary")
    print("=" * 50)
    print(f"  Total tweets captured:  {summary['total_tweets']}")
    print(f"  Unique tweets:          {summary['unique_tweets']}")
    print(f"  Duplicates removed:     {summary['duplicates_removed']}")
    print(f"  Images downloaded:      {summary['images_downloaded']}")
    print(f"  Image failures:         {summary['images_failed']}")
    print(f"  Scrolls performed:      {summary['scroll_count']}")
    print(f"  Total run time:         {summary['run_time_seconds']:.1f}s")
    print(f"  Stop reason:            {summary['stop_reason']}")
    if summary["warnings"]:
        print(f"  Warnings:               {len(summary['warnings'])}")
        for w in summary["warnings"]:
            print(f"    - {w}")
    print("=" * 50 + "\n")


async def main():
    """Run the feed collector."""
    config = load_config()
    output_dir = config.get("output_dir", "feed_data")
    print(f"[collector] Loaded config: {json.dumps(config, indent=2)}")

    # Create a unique run directory
    run_dir = get_run_dir(output_dir)
    set_run_dir(run_dir)
    print(f"[collector] Run directory: {run_dir}")

    start_time = time.monotonic()
    warnings: list[str] = []

    # Set up interceptor — raw responses go into the run dir
    interceptor = ResponseInterceptor(run_dir=run_dir)

    async with async_playwright() as p:
        try:
            browser, context, page = await load_session(p)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"[collector] {e}")
            return

        # Attach GraphQL response listener
        page.on("response", interceptor.handle_response)
        print("[collector] GraphQL interceptor attached. Listening for Home timeline responses...")

        # Navigate to home feed to trigger initial GraphQL load
        await page.reload(wait_until="domcontentloaded")
        print("[collector] Page reloaded. Waiting for GraphQL responses...")

        # Wait for initial responses to arrive
        await page.wait_for_timeout(5000)

        # Report what was captured from initial load
        count = len(interceptor.responses)
        print(f"[collector] Captured {count} GraphQL response(s) from initial page load.")

        if count == 0:
            print("[collector] No GraphQL responses captured. The feed may not have loaded.")
            print("[collector] Waiting a few more seconds...")
            await page.wait_for_timeout(5000)
            count = len(interceptor.responses)
            print(f"[collector] After extended wait: {count} response(s) captured.")
            if count == 0:
                warnings.append("No GraphQL responses captured after extended wait")

        # Scroll to collect more tweets
        max_tweets = config.get("max_tweets", 50)
        max_minutes = config.get("max_minutes", None)
        oldest_tweet_date = config.get("oldest_tweet_date", None)
        delay_min = config.get("scroll_delay_min", 2)
        delay_max = config.get("scroll_delay_max", 5)

        scroll_stats = await scroll_loop(
            page,
            interceptor,
            delay_min=delay_min,
            delay_max=delay_max,
            max_tweets=max_tweets,
            max_minutes=max_minutes,
            oldest_tweet_date=oldest_tweet_date,
        )

        # Parse final tweet set
        tweets = interceptor.parse_all_tweets(skip_ads=True)

        # Calculate collection duration
        duration = time.monotonic() - start_time

        if tweets:
            # Deduplicate within this run
            unique_tweets, dupes_removed = deduplicate_within_run(tweets)

            # Download media (images + videos)
            downloaded, dl_failed = await download_tweet_images(unique_tweets, output_dir)
            if dl_failed > 0:
                warnings.append(f"{dl_failed} media download(s) failed")

            save_tweets(unique_tweets, run_dir, duration_seconds=duration)
        else:
            unique_tweets = []
            dupes_removed = 0
            downloaded = 0
            dl_failed = 0
            warnings.append("No tweets parsed from intercepted responses")

        # Build summary
        summary = {
            "run_timestamp": datetime.now().isoformat(),
            "run_dir": str(run_dir),
            "total_tweets": len(tweets),
            "unique_tweets": len(unique_tweets),
            "duplicates_removed": dupes_removed,
            "images_downloaded": downloaded,
            "images_failed": dl_failed,
            "scroll_count": scroll_stats["scroll_count"],
            "run_time_seconds": round(duration, 2),
            "stop_reason": scroll_stats["stop_reason"],
            "warnings": warnings,
        }

        print_summary(summary)
        save_run_summary(summary, run_dir)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
