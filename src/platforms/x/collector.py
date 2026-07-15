"""X feed collector — orchestrates a collection run."""

import asyncio
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from playwright.async_api import async_playwright

from src.media_downloader import download_media
from src.platforms.x.auth import load_session
from src.platforms.x.interceptor import ResponseInterceptor
from src.platforms.x.replies import fetch_replies
from src.platforms.x.scroller import scroll_loop
from src.platforms.reply_utils import MEDIA_PHASE_TIMEOUT, REPLY_PHASE_TIMEOUT
from src.storage import deduplicate_within_run, get_run_dir, save_posts, save_run_summary, set_run_dir


def print_summary(summary: dict):
    """Print a formatted collection run summary."""
    print("\n" + "=" * 50)
    print("  X Collection Summary")
    print("=" * 50)
    print(f"  Total posts captured:   {summary['total_posts']}")
    print(f"  Unique posts:           {summary['unique_posts']}")
    print(f"  Duplicates removed:     {summary['duplicates_removed']}")
    print(f"  Media downloaded:       {summary['media_downloaded']}")
    print(f"  Media failures:         {summary['media_failed']}")
    print(f"  Replies fetched:        {summary.get('replies_fetched', 0)}")
    print(f"  Scrolls performed:      {summary['scroll_count']}")
    print(f"  Total run time:         {summary['run_time_seconds']:.1f}s")
    print(f"  Stop reason:            {summary['stop_reason']}")
    if summary["warnings"]:
        print(f"  Warnings:               {len(summary['warnings'])}")
        for w in summary["warnings"]:
            print(f"    - {w}")
    print("=" * 50 + "\n")


async def run(config: dict) -> dict:
    """Run the X feed collector. Returns summary dict."""
    output_dir = config.get("output_dir", "feed_data")
    platform_config = config.get("platforms", {}).get("x", config)

    # Create a unique run directory
    job_id = config.get("_job_id")
    run_dir = get_run_dir(output_dir, platform="x", job_id=job_id)
    set_run_dir(run_dir)
    print(f"[x] Run directory: {run_dir}")

    start_time = time.monotonic()
    warnings: list[str] = []

    interceptor = ResponseInterceptor(run_dir=run_dir)

    session_file = platform_config.get("session_file", None)

    async with async_playwright() as p:
        try:
            browser, context, page = await load_session(p, session_file=session_file)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"[x] {e}")
            return {"error": str(e)}

        page.on("response", interceptor.handle_response)
        print("[x] GraphQL interceptor attached. Listening for Home timeline responses...")

        await page.reload(wait_until="domcontentloaded")
        print("[x] Page reloaded. Waiting for GraphQL responses...")

        await page.wait_for_timeout(5000)

        count = len(interceptor.responses)
        print(f"[x] Captured {count} GraphQL response(s) from initial page load.")

        if count == 0:
            print("[x] No GraphQL responses captured. Waiting a few more seconds...")
            await page.wait_for_timeout(5000)
            count = len(interceptor.responses)
            print(f"[x] After extended wait: {count} response(s) captured.")
            if count == 0:
                warnings.append("No GraphQL responses captured after extended wait")

        max_posts = platform_config.get("max_posts", platform_config.get("max_tweets", 50))
        max_minutes = platform_config.get("max_minutes", None)
        oldest_post_date = platform_config.get("oldest_post_date", platform_config.get("oldest_tweet_date", None))
        delay_min = platform_config.get("scroll_delay_min", 2)
        delay_max = platform_config.get("scroll_delay_max", 5)

        scroll_stats = await scroll_loop(
            page,
            interceptor,
            delay_min=delay_min,
            delay_max=delay_max,
            max_posts=max_posts,
            max_minutes=max_minutes,
            oldest_post_date=oldest_post_date,
        )

        posts = interceptor.parse_all_posts(skip_ads=True)
        duration = time.monotonic() - start_time

        if posts:
            unique_posts, dupes_removed = deduplicate_within_run(posts)
            downloaded = dl_failed = replies_fetched = 0

            # Save the scrape immediately. Media + replies below are best-effort
            # enrichment — a hang or crash in either must never lose the posts
            # we already captured (previously save ran only after replies, so a
            # wedged reply tab discarded the whole run).
            save_posts(unique_posts, run_dir, platform="x", duration_seconds=duration)

            # Media — bounded so a stall can't hang the run (per-file timeouts
            # inside; whole-phase cap here).
            try:
                downloaded, dl_failed = await asyncio.wait_for(
                    download_media(unique_posts, output_dir, run_dir=run_dir),
                    timeout=MEDIA_PHASE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                warnings.append(f"media phase exceeded {MEDIA_PHASE_TIMEOUT}s; saved with partial media")
            except Exception as e:
                warnings.append(f"media phase error: {e}")
            if dl_failed > 0:
                warnings.append(f"{dl_failed} media download(s) failed")

            # Replies — bounded; a wedged detail tab can't stall the run.
            reply_posts = [t for t in unique_posts if t.replies > 0 and t.author_handle]
            reply_posts.sort(key=lambda t: t.replies, reverse=True)
            reply_posts = reply_posts[:platform_config.get("max_reply_tweets", 20)]
            if reply_posts:
                tweet_dicts = [{"id": t.id, "author_handle": t.author_handle} for t in reply_posts]
                try:
                    replies_map = await asyncio.wait_for(
                        fetch_replies(
                            context, tweet_dicts,
                            max_replies_per_tweet=platform_config.get("max_replies_per_tweet", 5),
                            batch_size=platform_config.get("reply_batch_size", 4),
                        ),
                        timeout=REPLY_PHASE_TIMEOUT,
                    )
                    post_by_id = {t.id: t for t in unique_posts}
                    for tid, reply_list in replies_map.items():
                        if tid in post_by_id and reply_list:
                            post_by_id[tid].top_replies = [asdict(r) for r in reply_list]
                    replies_fetched = sum(len(r) for r in replies_map.values())
                except asyncio.TimeoutError:
                    warnings.append(f"reply phase exceeded {REPLY_PHASE_TIMEOUT}s; saved without replies")
                except Exception as e:
                    warnings.append(f"reply phase error: {e}")

            # Re-save with media paths + replies attached.
            save_posts(unique_posts, run_dir, platform="x", duration_seconds=duration)
        else:
            unique_posts = []
            dupes_removed = 0
            downloaded = 0
            dl_failed = 0
            replies_fetched = 0
            warnings.append("No posts parsed from intercepted responses")

        duration = time.monotonic() - start_time

        summary = {
            "platform": "x",
            "run_timestamp": datetime.now().isoformat(),
            "run_dir": str(run_dir),
            "total_posts": len(posts),
            "unique_posts": len(unique_posts),
            "duplicates_removed": dupes_removed,
            "media_downloaded": downloaded,
            "media_failed": dl_failed,
            "replies_fetched": replies_fetched,
            "scroll_count": scroll_stats["scroll_count"],
            "run_time_seconds": round(duration, 2),
            "stop_reason": scroll_stats["stop_reason"],
            "warnings": warnings,
        }

        print_summary(summary)
        save_run_summary(summary, run_dir)

        await browser.close()

    return summary


async def main():
    config_path = Path("config.json")
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {"output_dir": "feed_data"}
    await run(config)


if __name__ == "__main__":
    asyncio.run(main())
