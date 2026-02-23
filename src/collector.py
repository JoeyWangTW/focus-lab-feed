"""Main entry point — orchestrates collection run."""

import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path when run directly (python3 src/collector.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

from src.auth import load_session
from src.interceptor import ResponseInterceptor
from src.storage import save_tweets


def load_config() -> dict:
    """Load configuration from config.json."""
    config_path = Path("config.json")
    if not config_path.exists():
        print("[collector] config.json not found, using defaults")
        return {
            "scroll_delay_min": 2,
            "scroll_delay_max": 5,
            "max_tweets": 50,
            "output_dir": "feed_data",
        }
    return json.loads(config_path.read_text())


async def main():
    """Run the feed collector."""
    config = load_config()
    output_dir = config.get("output_dir", "feed_data")
    print(f"[collector] Loaded config: {json.dumps(config, indent=2)}")

    # Set up interceptor
    interceptor = ResponseInterceptor(output_dir=output_dir)

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
        # The page is already on /home from load_session, but we reload to
        # ensure the interceptor captures the initial timeline request
        await page.reload(wait_until="domcontentloaded")
        print("[collector] Page reloaded. Waiting for GraphQL responses...")

        # Wait for initial responses to arrive
        await page.wait_for_timeout(5000)

        # Report what was captured
        count = len(interceptor.responses)
        print(f"[collector] Captured {count} GraphQL response(s) from initial page load.")

        if count == 0:
            print("[collector] No GraphQL responses captured. The feed may not have loaded.")
            print("[collector] Waiting a few more seconds...")
            await page.wait_for_timeout(5000)
            count = len(interceptor.responses)
            print(f"[collector] After extended wait: {count} response(s) captured.")

        # Parse tweets from captured responses
        tweets = interceptor.parse_all_tweets(skip_ads=True)

        if tweets:
            tweets_file = save_tweets(tweets, output_dir)
            print(f"[collector] Saved {len(tweets)} tweets to {tweets_file}")
        else:
            print("[collector] No tweets parsed from responses.")

        print(f"[collector] Collection complete. {count} raw response(s), {len(tweets)} tweets parsed.")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
