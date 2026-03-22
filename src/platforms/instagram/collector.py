"""Instagram feed collector — orchestrates a collection run."""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from playwright.async_api import async_playwright

from src.media_downloader import download_media
from src.platforms.instagram.auth import load_session
from src.platforms.instagram.interceptor import ResponseInterceptor
from src.storage import deduplicate_within_run, get_run_dir, save_posts, save_run_summary, set_run_dir


async def scroll_feed(page, delay_min: float = 3.0, delay_max: float = 7.0):
    import random
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    delay = random.uniform(delay_min, delay_max)
    await asyncio.sleep(delay)
    return delay


def print_summary(summary: dict):
    print("\n" + "=" * 50)
    print("  Instagram Collection Summary")
    print("=" * 50)
    print(f"  Total posts captured:   {summary['total_posts']}")
    print(f"  Unique posts:           {summary['unique_posts']}")
    print(f"  Media downloaded:       {summary['media_downloaded']}")
    print(f"  Media failures:         {summary['media_failed']}")
    print(f"  Scrolls performed:      {summary['scroll_count']}")
    print(f"  Total run time:         {summary['run_time_seconds']:.1f}s")
    print(f"  Stop reason:            {summary['stop_reason']}")
    if summary["warnings"]:
        for w in summary["warnings"]:
            print(f"    - {w}")
    print("=" * 50 + "\n")


async def run(config: dict) -> dict:
    """Run the Instagram feed collector."""
    output_dir = config.get("output_dir", "feed_data")
    platform_config = config.get("platforms", {}).get("instagram", config)

    run_dir = get_run_dir(output_dir, platform="instagram")
    set_run_dir(run_dir)
    print(f"[instagram] Run directory: {run_dir}")

    start_time = time.monotonic()
    warnings: list[str] = []

    interceptor = ResponseInterceptor(run_dir=run_dir)
    session_file = platform_config.get("session_file", None)

    async with async_playwright() as p:
        try:
            browser, context, page = await load_session(p, session_file=session_file)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"[instagram] {e}")
            return {"error": str(e)}

        # Attach GraphQL interceptor for scroll-loaded content
        page.on("response", interceptor.handle_response)
        print("[instagram] GraphQL interceptor attached.")

        # Reload to get fresh page
        await page.reload(wait_until="domcontentloaded")
        print("[instagram] Page reloaded. Waiting for feed to render...")
        await page.wait_for_timeout(8000)

        # Extract initial feed data from embedded HTML
        await interceptor.extract_from_page(page)

        initial_count = len(interceptor.parse_all_posts())
        print(f"[instagram] Posts from initial load: {initial_count}")

        if initial_count == 0:
            print("[instagram] No posts found in initial load. Waiting longer...")
            await page.wait_for_timeout(5000)
            await interceptor.extract_from_page(page)
            initial_count = len(interceptor.parse_all_posts())
            if initial_count == 0:
                warnings.append("No feed posts found after extended wait")

        # Scroll loop
        max_posts = platform_config.get("max_posts", 30)
        max_minutes = platform_config.get("max_minutes", 5)
        delay_min = platform_config.get("scroll_delay_min", 3)
        delay_max = platform_config.get("scroll_delay_max", 7)
        stale_limit = 3
        scroll_count = 0
        stale_scrolls = 0
        stop_reason = "Unknown"

        prev_count = initial_count

        while True:
            if prev_count >= max_posts:
                stop_reason = f"Reached max_posts limit ({max_posts})"
                break

            elapsed = (time.monotonic() - start_time) / 60
            if max_minutes and elapsed >= max_minutes:
                stop_reason = f"Reached max_minutes limit ({max_minutes} min)"
                break

            delay = await scroll_feed(page, delay_min, delay_max)
            scroll_count += 1
            await page.wait_for_timeout(3000)

            # Also try extracting from current page state (IG may inject into DOM)
            await interceptor.extract_from_page(page)

            current_count = len(interceptor.parse_all_posts())
            new_posts = current_count - prev_count

            print(f"[instagram] Scroll #{scroll_count}: +{new_posts} new posts | total={current_count} | delay={delay:.1f}s")

            if new_posts == 0:
                stale_scrolls += 1
                if stale_scrolls >= stale_limit:
                    stop_reason = f"No new posts after {stale_limit} consecutive scrolls"
                    break
            else:
                stale_scrolls = 0

            prev_count = current_count

        print(f"[instagram] Stopping: {stop_reason}")

        posts = interceptor.parse_all_posts()
        duration = time.monotonic() - start_time

        if posts:
            unique_posts, dupes_removed = deduplicate_within_run(posts)

            downloaded, dl_failed = await download_media(unique_posts, output_dir)
            if dl_failed > 0:
                warnings.append(f"{dl_failed} media download(s) failed")

            save_posts(unique_posts, run_dir, platform="instagram", duration_seconds=duration)
        else:
            unique_posts = []
            downloaded = 0
            dl_failed = 0
            warnings.append("No posts parsed")

        duration = time.monotonic() - start_time

        summary = {
            "platform": "instagram",
            "run_timestamp": datetime.now().isoformat(),
            "run_dir": str(run_dir),
            "total_posts": len(posts),
            "unique_posts": len(unique_posts),
            "media_downloaded": downloaded,
            "media_failed": dl_failed,
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
