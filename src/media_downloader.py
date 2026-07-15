"""Image/video download from media URLs."""

import asyncio
from pathlib import Path

import aiohttp

from src.models import Post
from src.storage import get_current_run_dir

# Downloads run concurrently — one platform's feed can carry 100+ files and
# several hundred MB of video. Sequential downloads made a run take 10+ minutes
# and look hung.
CONCURRENCY = 6

# Per-file ceilings. Without these a single stalled CDN connection blocks the
# whole run: aiohttp's default is a 5-minute total timeout per request, and a
# collector downloading 100 files could sit there for hours.
CONNECT_TIMEOUT = 15      # seconds to establish the connection
READ_TIMEOUT = 60         # seconds of no data before we give up
TOTAL_TIMEOUT = 180       # hard ceiling for one file (a big video on a slow CDN)


async def download_file(session: aiohttp.ClientSession, url: str, dest: Path) -> bool:
    """Download a single file. Returns True on success."""
    if dest.exists() and dest.stat().st_size > 0:
        return True  # already fetched (e.g. a retried run)
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                dest.parent.mkdir(parents=True, exist_ok=True)
                # Stream to disk so a huge video doesn't sit in memory whole.
                tmp = dest.with_suffix(dest.suffix + ".part")
                with tmp.open("wb") as f:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        f.write(chunk)
                tmp.replace(dest)
                return True
            print(f"[download] Failed {url}: HTTP {resp.status}")
            return False
    except asyncio.TimeoutError:
        print(f"[download] Timeout after {TOTAL_TIMEOUT}s: {url[:80]}")
        return False
    except Exception as e:
        print(f"[download] Error downloading {url}: {e}")
        return False


def _image_download_url(media_url: str) -> str:
    """Ensure media URL has the large format suffix."""
    base = media_url.split("?")[0]
    return f"{base}?format=jpg&name=large"


async def download_media(
    posts: list[Post],
    output_dir: str = "feed_data",
    run_dir: Path | None = None,
) -> tuple[int, int]:
    """Download images and videos for all posts.

    Updates each post's local_media_paths in place.
    Returns (downloaded_count, failed_count).

    `run_dir` must be passed by the caller. The app runs every platform's
    collector concurrently in one event loop, so the module-level "current run
    dir" is whatever platform started last — relying on it sent every
    platform's media into one other platform's folder. The fallback is kept
    only for standalone/legacy callers.
    """
    if run_dir is None:
        run_dir = get_current_run_dir(output_dir)
    media_dir = run_dir / "media"

    # Collect all download tasks: (post, url, dest, is_video, platform)
    tasks: list[tuple[Post, str, Path, bool, str]] = []
    for post in posts:
        for i, url in enumerate(post.media_urls):
            ext = "jpg"
            if ".webp" in url:
                ext = "webp"
            elif ".png" in url:
                ext = "png"
            dest = media_dir / f"{post.id}_{i}.{ext}"
            tasks.append((post, url, dest, False, post.platform))
        for i, url in enumerate(post.video_urls):
            dest = media_dir / f"{post.id}_v{i}.mp4"
            tasks.append((post, url, dest, True, post.platform))

    if not tasks:
        print("[download] No media to download.")
        return 0, 0

    total = len(tasks)
    done = 0
    downloaded = 0
    failed = 0
    # Posts collect their own paths, then we append in URL order per post so
    # local_media_paths stays aligned with media_urls + video_urls.
    results: dict[int, list[tuple[int, str]]] = {}
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(CONCURRENCY)

    timeout = aiohttp.ClientTimeout(
        total=TOTAL_TIMEOUT, connect=CONNECT_TIMEOUT, sock_read=READ_TIMEOUT
    )

    async def fetch_one(order: int, post: Post, url: str, dest: Path, is_video: bool, platform: str, session):
        nonlocal done, downloaded, failed
        if is_video:
            download_url = url
        elif platform == "x":
            download_url = _image_download_url(url)
        else:
            download_url = url

        async with sem:
            success = await download_file(session, download_url, dest)

        async with lock:
            done += 1
            if success:
                downloaded += 1
                rel_path = str(dest.relative_to(Path(output_dir)))
                results.setdefault(id(post), []).append((order, rel_path))
            else:
                failed += 1
            if done % 10 == 0 or done == total:
                print(f"[download] Progress: {done}/{total} ({downloaded} ok, {failed} failed)")

    # Assemble in a finally so that even if this phase is cancelled (e.g. a
    # collector's media-phase timeout fires), every file that DID download is
    # still linked onto its post — in URL order — rather than orphaned on disk.
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            await asyncio.gather(*[
                fetch_one(i, post, url, dest, is_video, platform, session)
                for i, (post, url, dest, is_video, platform) in enumerate(tasks)
            ])
    finally:
        for post in posts:
            paths = results.get(id(post))
            if paths:
                post.local_media_paths.extend(p for _, p in sorted(paths))

    print(f"[download] Complete: {downloaded} downloaded, {failed} failed out of {total}")
    return downloaded, failed
