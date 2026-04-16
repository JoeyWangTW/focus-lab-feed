"""Data persistence — JSON output, per-run storage with date/job/platform hierarchy."""

import json
import re
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import Post


def create_job_id() -> str:
    """Generate a job ID from current timestamp (HHMMSS)."""
    return datetime.now().strftime("%H%M%S")


def get_run_dir(output_dir: str = "feed_data", platform: str = "unknown", job_id: str | None = None) -> Path:
    """Return a run directory in date/job/platform hierarchy, creating it if needed.

    Structure: feed_data/YYYY-MM-DD/job_HHMMSS/{platform}/
    """
    today = datetime.now().strftime("%Y-%m-%d")
    if not job_id:
        job_id = create_job_id()

    job_dir = Path(output_dir) / today / f"job_{job_id}"
    path = job_dir / platform
    path.mkdir(parents=True, exist_ok=True)

    # Create job.json if it doesn't exist yet
    job_meta_path = job_dir / "job.json"
    if not job_meta_path.exists():
        save_job_metadata(job_dir, job_id, today)

    return path


def save_job_metadata(job_dir: Path, job_id: str, date: str, platforms: list[str] | None = None):
    """Save or update job.json in the job directory."""
    job_meta_path = job_dir / "job.json"

    if job_meta_path.exists():
        existing = json.loads(job_meta_path.read_text())
        if platforms:
            existing_platforms = set(existing.get("platforms", []))
            existing_platforms.update(platforms)
            existing["platforms"] = sorted(existing_platforms)
        job_meta_path.write_text(json.dumps(existing, indent=2))
        return

    meta = {
        "job_id": job_id,
        "date": date,
        "started_at": datetime.now().isoformat(),
        "platforms": platforms or [],
    }
    job_meta_path.write_text(json.dumps(meta, indent=2))


_current_run_dir: Optional[Path] = None


def set_run_dir(run_dir: Path):
    """Set the current run directory (called once by collector at start)."""
    global _current_run_dir
    _current_run_dir = run_dir


def get_current_run_dir(output_dir: str = "feed_data") -> Path:
    """Return the current run dir. Falls back to creating a new one."""
    return _current_run_dir or get_run_dir(output_dir)


def save_posts(
    posts: list[Post],
    run_dir: Path,
    platform: str = "unknown",
    duration_seconds: Optional[float] = None,
) -> Path:
    """Save posts to this run's posts.json with collection metadata."""
    posts_file = run_dir / "posts.json"

    data = {
        "metadata": {
            "platform": platform,
            "run_timestamp": datetime.now().isoformat(),
            "post_count": len(posts),
            "collection_duration_seconds": round(duration_seconds, 2) if duration_seconds is not None else None,
        },
        "posts": [asdict(post) for post in posts],
    }

    posts_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"[storage] Saved {len(posts)} posts to {posts_file}")
    return posts_file


def save_run_summary(summary: dict, run_dir: Path) -> Path:
    """Save the run summary to this run's run_log.json."""
    log_file = run_dir / "run_log.json"
    log_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[storage] Run summary saved to {log_file}")
    return log_file


def deduplicate_within_run(posts: list[Post]) -> tuple[list[Post], int]:
    """Deduplicate posts within a single run by ID."""
    seen: dict[str, Post] = {}
    for p in posts:
        if p.id not in seen:
            seen[p.id] = p
    dupes = len(posts) - len(seen)
    print(f"[storage] Dedup: {len(posts)} collected, {dupes} duplicates removed, {len(seen)} unique")
    return list(seen.values()), dupes


def load_posts_from_file(path: Path) -> list[Post]:
    """Load posts from a posts.json or tweets.json file."""
    data = json.loads(path.read_text())
    posts_data = data.get("posts", data.get("tweets", []))
    return [Post(**p) for p in posts_data]


def migrate_legacy_runs(output_dir: str = "feed_data"):
    """Migrate old flat run directories (YYYY-MM-DD_HHMMSS_platform/) to new hierarchy.

    Old: feed_data/2026-03-22_002223_twitter/
    New: feed_data/2026-03-22/job_002223/twitter/
    """
    feed_dir = Path(output_dir)
    if not feed_dir.exists():
        return

    # Pattern: YYYY-MM-DD_HHMMSS_platform
    legacy_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{6})_(\w+)$")
    legacy_dirs = []

    for d in feed_dir.iterdir():
        if d.is_dir():
            m = legacy_pattern.match(d.name)
            if m:
                legacy_dirs.append((d, m.group(1), m.group(2), m.group(3)))

    if not legacy_dirs:
        return

    print(f"[storage] Migrating {len(legacy_dirs)} legacy run directories...")

    for old_dir, date, time_id, platform in legacy_dirs:
        new_job_dir = feed_dir / date / f"job_{time_id}"
        new_platform_dir = new_job_dir / platform

        if new_platform_dir.exists():
            print(f"[storage] Skipping {old_dir.name} — destination already exists")
            continue

        new_job_dir.mkdir(parents=True, exist_ok=True)

        # Move the entire platform directory
        shutil.move(str(old_dir), str(new_platform_dir))

        # Update local_media_paths in posts.json to reflect new structure
        posts_file = new_platform_dir / "posts.json"
        if posts_file.exists():
            try:
                data = json.loads(posts_file.read_text())
                old_prefix = f"{date}_{time_id}_{platform}/"
                new_prefix = f"{date}/job_{time_id}/{platform}/"
                for post in data.get("posts", data.get("tweets", [])):
                    if "local_media_paths" in post:
                        post["local_media_paths"] = [
                            p.replace(old_prefix, new_prefix) for p in post["local_media_paths"]
                        ]
                posts_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            except (json.JSONDecodeError, OSError) as e:
                print(f"[storage] Warning: could not update paths in {posts_file}: {e}")

        # Create job.json if not already there
        job_meta = new_job_dir / "job.json"
        if not job_meta.exists():
            save_job_metadata(new_job_dir, time_id, date, [platform])
        else:
            # Update platforms list
            save_job_metadata(new_job_dir, time_id, date, [platform])

        print(f"[storage] Migrated {old_dir.name} → {date}/job_{time_id}/{platform}/")

    print(f"[storage] Migration complete.")
