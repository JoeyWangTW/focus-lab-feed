"""Data persistence — JSON output, deduplication."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import Tweet


def get_today_dir(output_dir: str = "feed_data") -> Path:
    """Return today's output directory, creating it if needed."""
    today = datetime.now().strftime("%Y-%m-%d")
    path = Path(output_dir) / today
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_tweets(
    tweets: list[Tweet],
    output_dir: str = "feed_data",
    duration_seconds: Optional[float] = None,
) -> Path:
    """Save tweets to today's tweets.json with collection metadata."""
    today_dir = get_today_dir(output_dir)
    tweets_file = today_dir / "tweets.json"

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


def load_tweets(output_dir: str = "feed_data") -> list[Tweet]:
    """Load tweets from today's tweets.json if it exists."""
    today_dir = get_today_dir(output_dir)
    tweets_file = today_dir / "tweets.json"

    if not tweets_file.exists():
        return []

    data = json.loads(tweets_file.read_text())
    return [Tweet(**t) for t in data.get("tweets", [])]


def load_tweets_from_file(path: Path) -> list[Tweet]:
    """Load tweets from a specific tweets.json file."""
    data = json.loads(path.read_text())
    return [Tweet(**t) for t in data.get("tweets", [])]


def load_metadata(output_dir: str = "feed_data") -> Optional[dict]:
    """Load collection metadata from today's tweets.json if it exists."""
    today_dir = get_today_dir(output_dir)
    tweets_file = today_dir / "tweets.json"

    if not tweets_file.exists():
        return None

    data = json.loads(tweets_file.read_text())
    return data.get("metadata")
