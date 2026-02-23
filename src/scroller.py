"""Scroll automation — timing, depth, stop conditions."""

import asyncio
import random


async def scroll_feed(page, delay_min: float = 2.0, delay_max: float = 5.0):
    """Scroll the page down once with a random delay."""
    await page.evaluate("window.scrollBy(0, window.innerHeight)")
    delay = random.uniform(delay_min, delay_max)
    await asyncio.sleep(delay)
    return delay
