"""Data persistence — JSON output, per-run storage."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import Tweet


def get_run_dir(output_dir: str = "feed_data") -> Path:
    """Return a unique run directory (timestamped), creating it if needed."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = Path(output_dir) / timestamp
    path.mkdir(parents=True, exist_ok=True)
    return path


# Keep backward compat for media_downloader which uses this
def get_today_dir(output_dir: str = "feed_data") -> Path:
    """Alias — returns the current run dir. Set by collector before use."""
    return _current_run_dir or get_run_dir(output_dir)


_current_run_dir: Optional[Path] = None


def set_run_dir(run_dir: Path):
    """Set the current run directory (called once by collector at start)."""
    global _current_run_dir
    _current_run_dir = run_dir


def save_tweets(
    tweets: list[Tweet],
    run_dir: Path,
    duration_seconds: Optional[float] = None,
) -> Path:
    """Save tweets to this run's tweets.json with collection metadata."""
    tweets_file = run_dir / "tweets.json"

    data = {
        "metadata": {
            "run_timestamp": datetime.now().isoformat(),
            "tweet_count": len(tweets),
            "collection_duration_seconds": round(duration_seconds, 2) if duration_seconds is not None else None,
        },
        "tweets": [asdict(tweet) for tweet in tweets],
    }

    tweets_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"[storage] Saved {len(tweets)} tweets to {tweets_file}")
    return tweets_file


def save_run_summary(summary: dict, run_dir: Path) -> Path:
    """Save the run summary to this run's run_log.json."""
    log_file = run_dir / "run_log.json"
    log_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[storage] Run summary saved to {log_file}")
    return log_file


def deduplicate_within_run(tweets: list[Tweet]) -> tuple[list[Tweet], int]:
    """Deduplicate tweets within a single run by ID.

    Returns (unique_tweets, duplicates_skipped).
    """
    seen: dict[str, Tweet] = {}
    for t in tweets:
        if t.id not in seen:
            seen[t.id] = t
    dupes = len(tweets) - len(seen)
    print(f"[storage] Dedup: {len(tweets)} collected, {dupes} duplicates removed, {len(seen)} unique")
    return list(seen.values()), dupes


def load_tweets_from_file(path: Path) -> list[Tweet]:
    """Load tweets from a specific tweets.json file."""
    data = json.loads(path.read_text())
    return [Tweet(**t) for t in data.get("tweets", [])]
