"""YouTube feed collector — orchestrates a collection run."""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from playwright.async_api import async_playwright

from src.platforms.youtube.auth import load_session
from src.platforms.youtube.interceptor import ResponseInterceptor
from src.storage import deduplicate_within_run, get_run_dir, save_posts, save_run_summary, set_run_dir


def print_summary(summary: dict):
    print("\n" + "=" * 50)
    print("  YouTube Collection Summary")
    print("=" * 50)
    print(f"  Videos captured:        {summary['videos']}")
    print(f"  Shorts captured:        {summary['shorts']}")
    print(f"  Total items:            {summary['unique_posts']}")
    print(f"  Scrolls performed:      {summary['scroll_count']}")
    print(f"  Total run time:         {summary['run_time_seconds']:.1f}s")
    print(f"  Stop reason:            {summary['stop_reason']}")
    if summary["warnings"]:
        for w in summary["warnings"]:
            print(f"    - {w}")
    print("=" * 50 + "\n")


async def run(config: dict) -> dict:
    """Run the YouTube feed collector."""
    output_dir = config.get("output_dir", "feed_data")
    platform_config = config.get("platforms", {}).get("youtube", config)

    run_dir = get_run_dir(output_dir, platform="youtube")
    set_run_dir(run_dir)
    print(f"[youtube] Run directory: {run_dir}")

    start_time = time.monotonic()
    warnings: list[str] = []

    interceptor = ResponseInterceptor(run_dir=run_dir)
    session_file = platform_config.get("session_file", None)

    async with async_playwright() as p:
        try:
            browser, context, page = await load_session(p, session_file=session_file)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"[youtube] {e}")
            return {"error": str(e)}

        # Attach browse API interceptor for scroll-loaded content
        page.on("response", interceptor.handle_response)
        print("[youtube] Browse API interceptor attached.")

        # Reload to get fresh ytInitialData
        await page.reload(wait_until="domcontentloaded")
        print("[youtube] Page reloaded. Waiting for feed to render...")
        await page.wait_for_timeout(6000)

        # Extract initial feed data
        await interceptor.extract_from_page(page)

        initial_count = len(interceptor.parse_all_posts())
        print(f"[youtube] Items from initial load: {initial_count}")

        if initial_count == 0:
            await page.wait_for_timeout(5000)
            await interceptor.extract_from_page(page)
            initial_count = len(interceptor.parse_all_posts())
            if initial_count == 0:
                warnings.append("No feed items found after extended wait")

        # Scroll loop — YouTube may load more via browse API
        max_posts = platform_config.get("max_posts", 50)
        max_minutes = platform_config.get("max_minutes", 5)
        delay_min = platform_config.get("scroll_delay_min", 2)
        delay_max = platform_config.get("scroll_delay_max", 5)
        stale_limit = 3
        scroll_count = 0
        stale_scrolls = 0
        stop_reason = "Unknown"
        prev_count = initial_count

        import random
        while True:
            if prev_count >= max_posts:
                stop_reason = f"Reached max_posts limit ({max_posts})"
                break

            elapsed = (time.monotonic() - start_time) / 60
            if max_minutes and elapsed >= max_minutes:
                stop_reason = f"Reached max_minutes limit ({max_minutes} min)"
                break

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            delay = random.uniform(delay_min, delay_max)
            await asyncio.sleep(delay)
            scroll_count += 1
            await page.wait_for_timeout(3000)

            # Also re-extract from page in case ytInitialData was updated
            await interceptor.extract_from_page(page)

            current_count = len(interceptor.parse_all_posts())
            new_posts = current_count - prev_count

            print(f"[youtube] Scroll #{scroll_count}: +{new_posts} new items | total={current_count} | delay={delay:.1f}s")

            if new_posts == 0:
                stale_scrolls += 1
                if stale_scrolls >= stale_limit:
                    stop_reason = f"No new items after {stale_limit} consecutive scrolls"
                    break
            else:
                stale_scrolls = 0

            prev_count = current_count

        print(f"[youtube] Stopping: {stop_reason}")

        posts = interceptor.parse_all_posts()
        duration = time.monotonic() - start_time

        if posts:
            unique_posts, dupes_removed = deduplicate_within_run(posts)
            # No media download for YouTube — we use embeds
            save_posts(unique_posts, run_dir, platform="youtube", duration_seconds=duration)
        else:
            unique_posts = []
            warnings.append("No items parsed")

        duration = time.monotonic() - start_time

        videos = [p for p in unique_posts if p.platform_data.get("type") == "video"]
        shorts = [p for p in unique_posts if p.platform_data.get("type") == "short"]

        summary = {
            "platform": "youtube",
            "run_timestamp": datetime.now().isoformat(),
            "run_dir": str(run_dir),
            "total_posts": len(posts),
            "unique_posts": len(unique_posts),
            "videos": len(videos),
            "shorts": len(shorts),
            "scroll_count": scroll_count,
            "run_time_seconds": round(duration, 2),
            "stop_reason": stop_reason,
            "warnings": warnings,
        }

        print_summary(summary)
        save_run_summary(summary, run_dir)
        await browser.close()

    return summary


async def main():
    config_path = Path("config.json")
    config = json.loads(config_path.read_text()) if config_path.exists() else {"output_dir": "feed_data"}
    await run(config)


if __name__ == "__main__":
    asyncio.run(main())
