"""Image/video download from media URLs."""

from pathlib import Path

import aiohttp

from src.models import Post
from src.storage import get_current_run_dir


async def download_file(session: aiohttp.ClientSession, url: str, dest: Path) -> bool:
    """Download a single file. Returns True on success."""
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
    base = media_url.split("?")[0]
    return f"{base}?format=jpg&name=large"


async def download_media(
    posts: list[Post], output_dir: str = "feed_data"
) -> tuple[int, int]:
    """Download images and videos for all posts.

    Updates each post's local_media_paths in place.
    Returns (downloaded_count, failed_count).
    """
    run_dir = get_current_run_dir(output_dir)
    media_dir = run_dir / "media"

    # Collect all download tasks: (post, url, dest, is_video)
    tasks: list[tuple[Post, str, Path, bool]] = []
    for post in posts:
        for i, url in enumerate(post.media_urls):
            dest = media_dir / f"{post.id}_{i}.jpg"
            tasks.append((post, url, dest, False))
        for i, url in enumerate(post.video_urls):
            dest = media_dir / f"{post.id}_v{i}.mp4"
            tasks.append((post, url, dest, True))

    if not tasks:
        print("[download] No media to download.")
        return 0, 0

    total = len(tasks)
    downloaded = 0
    failed = 0

    async with aiohttp.ClientSession() as session:
        for idx, (post, url, dest, is_video) in enumerate(tasks, 1):
            download_url = url if is_video else _image_download_url(url)

            success = await download_file(session, download_url, dest)
            if success:
                rel_path = str(dest.relative_to(run_dir.parent))
                post.local_media_paths.append(rel_path)
                downloaded += 1
            else:
                failed += 1

            kind = "video" if is_video else "image"
            print(f"[download] Progress: {idx}/{total} ({kind})")

    print(f"[download] Complete: {downloaded} downloaded, {failed} failed out of {total}")
    return downloaded, failed
