"""Session management — login, save/load cookies for YouTube."""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

SESSION_DIR = Path("session")
SESSION_FILE = SESSION_DIR / "youtube_state.json"


async def login_and_save_session():
    """Open browser for manual YouTube/Google login, then save session state."""
    SESSION_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://accounts.google.com/signin")
        print("[auth:youtube] Browser opened to Google login page.")
        print("[auth:youtube] Please log in with your Google account.")
        print("[auth:youtube] Once you see YouTube's home page, press Enter here to save the session...")
        await asyncio.get_event_loop().run_in_executor(None, input)

        await context.storage_state(path=str(SESSION_FILE))
        print(f"[auth:youtube] Session saved to {SESSION_FILE}")

        await browser.close()
        print("[auth:youtube] Browser closed. You can now run the collector.")


CHANNEL_ITEM = "ytd-account-item-renderer"


async def _handle_channel_picker(page, context, session_path: Path) -> bool:
    """Get past YouTube's "Select a channel" interstitial.

    Accounts that own more than one channel get bounced from the home feed to
    /account with a channel picker. Until a channel is chosen there is no feed
    to scroll — ytInitialData is the settings page, so the collector sees zero
    items. Pick the first channel (the account's primary), tick "don't ask
    again" so future runs skip the interstitial, and persist the session.

    Returns True if the picker was present and handled.
    """
    items = page.locator(CHANNEL_ITEM)
    try:
        count = await items.count()
    except Exception:
        return False
    if count == 0:
        return False

    try:
        name = (await items.first.inner_text()).split("\n")[0].strip()
    except Exception:
        name = "(first channel)"
    print(f"[auth:youtube] Channel picker blocking the feed — selecting {name!r} of {count}.")

    # Tick "Don't ask again" first, if it's there: clicking the channel closes
    # the dialog, so the checkbox has to go first to be remembered.
    checkbox = page.locator("tp-yt-paper-checkbox, ytd-checkbox-renderer").first
    try:
        if await checkbox.count() > 0:
            await checkbox.click(timeout=3000)
    except Exception:
        pass  # cosmetic — we still select a channel below

    try:
        await items.first.click(timeout=5000)
    except Exception as e:
        print(f"[auth:youtube] Could not click the channel item: {e}")
        return False

    await page.wait_for_timeout(3000)

    # The picker sends us wherever it likes; go get the actual feed.
    await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
    await page.wait_for_timeout(4000)

    try:
        await context.storage_state(path=str(session_path))
        print("[auth:youtube] Channel selected; session re-saved.")
    except Exception as e:
        print(f"[auth:youtube] Warning: couldn't re-save session: {e}")

    return True


async def load_session(playwright, session_file: str | None = None):
    """Launch browser with saved session state. Returns (browser, context, page)."""
    session_path = Path(session_file) if session_file else SESSION_FILE

    if not session_path.exists():
        raise FileNotFoundError(
            f"No saved session at {session_path}. "
            "Run 'python3 -m src.platforms.youtube.auth' to log in first."
        )

    try:
        json.loads(session_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise RuntimeError(
            f"Session file at {session_path} is corrupted: {e}. "
            "Run 'python3 -m src.platforms.youtube.auth' to re-authenticate."
        )

    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(storage_state=str(session_path))
    page = await context.new_page()

    await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    if "accounts.google.com" in page.url:
        await browser.close()
        raise RuntimeError(
            "Session expired or invalid. "
            "Run 'python3 -m src.platforms.youtube.auth' to re-authenticate."
        )

    await _handle_channel_picker(page, context, session_path)

    # Whatever happened above, the collector needs to start on the home feed.
    if "/account" in page.url or not page.url.rstrip("/").endswith("youtube.com"):
        await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

    print(f"[auth:youtube] Session loaded successfully. Current URL: {page.url}")
    return browser, context, page


if __name__ == "__main__":
    asyncio.run(login_and_save_session())
