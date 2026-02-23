"""Image/video download from media URLs."""

from pathlib import Path

import aiohttp

from src.models import Tweet
from src.storage import get_today_dir


async def download_image(session: aiohttp.ClientSession, url: str, dest: Path) -> bool:
    """Download a single image. Returns True on success."""
    try:
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


def _image_download_url(media_url: str) -> str:
    """Ensure media URL has the large format suffix."""
    # Strip existing query params and add large format
    base = media_url.split("?")[0]
    return f"{base}?format=jpg&name=large"


async def download_tweet_images(
    tweets: list[Tweet], output_dir: str = "feed_data"
) -> tuple[int, int]:
    """Download images for all tweets that have media_urls.

    Updates each tweet's local_media_paths in place.
    Returns (downloaded_count, failed_count).
    """
    today_dir = get_today_dir(output_dir)
    media_dir = today_dir / "media"

    # Collect all (tweet, index, url) tuples to download
    tasks: list[tuple[Tweet, int, str, Path]] = []
    for tweet in tweets:
        for i, url in enumerate(tweet.media_urls):
            dest = media_dir / f"{tweet.id}_{i}.jpg"
            tasks.append((tweet, i, url, dest))

    if not tasks:
        print("[download] No images to download.")
        return 0, 0

    total = len(tasks)
    downloaded = 0
    failed = 0

    async with aiohttp.ClientSession() as session:
        for idx, (tweet, img_index, url, dest) in enumerate(tasks, 1):
            download_url = _image_download_url(url)
            success = await download_image(session, download_url, dest)
            if success:
                downloaded += 1
                # Store relative path from output_dir for portability
                rel_path = str(dest.relative_to(Path(output_dir)))
                tweet.local_media_paths.append(rel_path)
            else:
                failed += 1
            print(f"[download] Progress: {idx} of {total} images processed")

    print(f"[download] Complete: {downloaded} downloaded, {failed} failed out of {total}")
    return downloaded, failed
