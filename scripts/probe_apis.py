"""Probe script — captures API response patterns from Threads and Instagram feeds."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright


async def probe_platform(name: str, session_file: str, feed_url: str):
    """Load a platform, scroll once, and log all API responses."""
    print(f"\n{'='*60}")
    print(f"  Probing {name}")
    print(f"{'='*60}\n")

    session_path = Path(session_file)
    if not session_path.exists():
        print(f"[probe] No session file at {session_path}, skipping {name}")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(storage_state=str(session_path))
        page = await context.new_page()

        responses_log = []

        async def log_response(response):
            url = response.url
            # Skip static assets
            if any(ext in url for ext in ['.js', '.css', '.png', '.jpg', '.gif', '.woff', '.ico', '.svg']):
                return
            if 'graphql' in url.lower() or '/api/' in url.lower() or '/ajax/' in url.lower():
                status = response.status
                size = 0
                body_preview = ""
                try:
                    body = await response.text()
                    size = len(body)
                    # Try to parse as JSON and get top-level keys
                    try:
                        data = json.loads(body)
                        if isinstance(data, dict):
                            body_preview = f"keys={list(data.keys())[:5]}"
                        elif isinstance(data, list):
                            body_preview = f"list[{len(data)}]"
                    except:
                        body_preview = body[:100]
                except:
                    pass

                entry = {
                    "url": url[:200],
                    "status": status,
                    "size": size,
                    "preview": body_preview,
                }
                responses_log.append(entry)
                print(f"[{name}] {status} | {size:>8,}B | {url[:120]}")
                if body_preview:
                    print(f"         {body_preview[:120]}")

        page.on("response", log_response)

        print(f"[probe] Navigating to {feed_url}...")
        await page.goto(feed_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(8000)

        print(f"\n[probe] Scrolling once...")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(5000)

        print(f"\n[probe] Captured {len(responses_log)} API responses from {name}")

        # Save full log
        out_dir = Path("feed_data") / "probes"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{name}_api_responses.json"
        with open(out_file, "w") as f:
            json.dump(responses_log, f, indent=2)
        print(f"[probe] Saved to {out_file}")

        # Also save one raw response body for the largest graphql response
        graphql_responses = []
        page2 = await context.new_page()

        async def capture_raw(response):
            url = response.url
            if 'graphql' in url.lower() or '/api/' in url.lower():
                try:
                    body = await response.text()
                    if len(body) > 5000:  # Only save substantial responses
                        graphql_responses.append({"url": url, "body": body})
                except:
                    pass

        page2.on("response", capture_raw)
        await page2.goto(feed_url, wait_until="domcontentloaded")
        await page2.wait_for_timeout(8000)

        if graphql_responses:
            # Save the largest response
            largest = max(graphql_responses, key=lambda r: len(r["body"]))
            raw_file = out_dir / f"{name}_largest_response.json"
            try:
                parsed = json.loads(largest["body"])
                with open(raw_file, "w") as f:
                    json.dump({"url": largest["url"], "data": parsed}, f, indent=2)
            except:
                with open(raw_file, "w") as f:
                    f.write(largest["body"])
            print(f"[probe] Largest response ({len(largest['body']):,}B) saved to {raw_file}")
            print(f"         URL: {largest['url'][:150]}")

        await page2.close()
        await browser.close()


async def main():
    await probe_platform(
        "threads",
        "session/threads_state.json",
        "https://www.threads.net",
    )
    await probe_platform(
        "instagram",
        "session/instagram_state.json",
        "https://www.instagram.com/",
    )


if __name__ == "__main__":
    asyncio.run(main())
