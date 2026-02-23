"""Session management — login, save/load cookies."""

import asyncio
import json
import os
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
        print("Please log in to Twitter in the browser window.")
        print("Press Enter here after you've logged in and see your feed...")
        await asyncio.get_event_loop().run_in_executor(None, input)

        await context.storage_state(path=str(SESSION_FILE))
        print(f"Session saved to {SESSION_FILE}")

        await browser.close()


async def load_session(playwright):
    """Launch browser with saved session state. Returns (browser, context, page)."""
    if not SESSION_FILE.exists():
        raise FileNotFoundError(
            f"No saved session at {SESSION_FILE}. "
            "Run 'python src/auth.py' to log in first."
        )

    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(storage_state=str(SESSION_FILE))
    page = await context.new_page()

    # Verify login by navigating to home
    await page.goto("https://twitter.com/home")
    await page.wait_for_load_state("networkidle")

    # Check if redirected to login page
    if "/login" in page.url:
        await browser.close()
        raise RuntimeError(
            "Session expired or invalid. "
            "Run 'python src/auth.py' to re-authenticate."
        )

    return browser, context, page


if __name__ == "__main__":
    asyncio.run(login_and_save_session())
