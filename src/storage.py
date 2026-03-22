"""Data persistence — JSON output, per-run storage."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import Post


def get_run_dir(output_dir: str = "feed_data", platform: str = "unknown") -> Path:
    """Return a unique run directory (timestamped + platform), creating it if needed."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = Path(output_dir) / f"{timestamp}_{platform}"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
