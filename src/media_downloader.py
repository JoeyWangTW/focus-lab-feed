"""Image/video download from media URLs."""

import asyncio
from pathlib import Path

import aiohttp


async def download_image(url: str, dest: Path) -> bool:
    """Download a single image. Returns True on success."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(await resp.read())
                    return True
                print(f"[download] Failed {url}: HTTP {resp.status}")
                return False
    except Exception as e:
        print(f"[download] Error downloading {url}: {e}")
        return False
