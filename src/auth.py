"""Session management — login, save/load cookies."""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

SESSION_DIR = Path("session")
SESSION_FILE = SESSION_DIR / "twitter_state.json"


async def login_and_save_session():
    """Open browser for manual Twitter login, then save session state."""
    SESSION_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://twitter.com/login")
        print("[auth] Browser opened to Twitter login page.")
        print("[auth] Please log in to Twitter in the browser window.")
        print("[auth] Once you see your home feed, press Enter here to save the session...")
        await asyncio.get_event_loop().run_in_executor(None, input)

        await context.storage_state(path=str(SESSION_FILE))
        print(f"[auth] Session saved to {SESSION_FILE}")

        await browser.close()
        print("[auth] Browser closed. You can now run the collector.")


async def load_session(playwright):
    """Launch browser with saved session state. Returns (browser, context, page)."""
    if not SESSION_FILE.exists():
        raise FileNotFoundError(
            f"No saved session at {SESSION_FILE}. "
            "Run 'python3 src/auth.py' to log in first."
        )

    # Validate session file is readable JSON
    try:
        json.loads(SESSION_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise RuntimeError(
            f"Session file at {SESSION_FILE} is corrupted: {e}. "
            "Run 'python3 src/auth.py' to re-authenticate."
        )

    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(storage_state=str(SESSION_FILE))
    page = await context.new_page()

    # Navigate to home feed — use domcontentloaded instead of networkidle
    # because Twitter constantly streams data and networkidle may never fire
    await page.goto("https://twitter.com/home", wait_until="domcontentloaded")
    # Give the page a moment to settle and redirect if session is invalid
    await page.wait_for_timeout(3000)

    # Check if redirected to login page (session expired)
    if "/login" in page.url or "/i/flow/login" in page.url:
        await browser.close()
        raise RuntimeError(
            "Session expired or invalid. "
            "Run 'python3 src/auth.py' to re-authenticate."
        )

    print(f"[auth] Session loaded successfully. Current URL: {page.url}")
    return browser, context, page


if __name__ == "__main__":
    asyncio.run(login_and_save_session())
