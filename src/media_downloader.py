"""Image/video download from media URLs."""

from pathlib import Path

import aiohttp

from src.models import Tweet
from src.storage import get_today_dir as get_run_dir_compat


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


def _video_download_url(video_url: str) -> str:
    """Clean video URL (strip query params after the tag)."""
    # Keep the URL as-is — Twitter video URLs work directly
    return video_url


async def download_tweet_media(
    tweets: list[Tweet], output_dir: str = "feed_data"
) -> tuple[int, int, int, int]:
    """Download images and videos for all tweets.

    Updates each tweet's local_media_paths in place.
    Returns (images_downloaded, images_failed, videos_downloaded, videos_failed).
    """
    run_dir = get_run_dir_compat(output_dir)
    media_dir = run_dir / "media"

    # Collect all download tasks: (tweet, url, dest, is_video)
    tasks: list[tuple[Tweet, str, Path, bool]] = []
    for tweet in tweets:
        for i, url in enumerate(tweet.media_urls):
            dest = media_dir / f"{tweet.id}_{i}.jpg"
            tasks.append((tweet, url, dest, False))
        for i, url in enumerate(tweet.video_urls):
            dest = media_dir / f"{tweet.id}_v{i}.mp4"
            tasks.append((tweet, url, dest, True))

    if not tasks:
        print("[download] No media to download.")
        return 0, 0, 0, 0

    total = len(tasks)
    img_ok = img_fail = vid_ok = vid_fail = 0

    async with aiohttp.ClientSession() as session:
        for idx, (tweet, url, dest, is_video) in enumerate(tasks, 1):
            if is_video:
                download_url = _video_download_url(url)
            else:
                download_url = _image_download_url(url)

            success = await download_file(session, download_url, dest)
            if success:
                rel_path = str(dest.relative_to(run_dir.parent))
                tweet.local_media_paths.append(rel_path)
                if is_video:
                    vid_ok += 1
                else:
                    img_ok += 1
            else:
                if is_video:
                    vid_fail += 1
                else:
                    img_fail += 1

            kind = "video" if is_video else "image"
            print(f"[download] Progress: {idx}/{total} ({kind})")

    print(
        f"[download] Complete: {img_ok} images, {vid_ok} videos downloaded | "
        f"{img_fail} image failures, {vid_fail} video failures"
    )
    return img_ok, img_fail, vid_ok, vid_fail


# Keep backward-compatible alias
async def download_tweet_images(
    tweets: list[Tweet], output_dir: str = "feed_data"
) -> tuple[int, int]:
    """Legacy wrapper — downloads all media (images + videos)."""
    img_ok, img_fail, vid_ok, vid_fail = await download_tweet_media(tweets, output_dir)
    return img_ok + vid_ok, img_fail + vid_fail
