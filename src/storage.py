"""Data persistence — JSON output, deduplication."""

import json
from datetime import datetime
from pathlib import Path

from src.models import Tweet


def get_today_dir(output_dir: str = "feed_data") -> Path:
    """Return today's output directory, creating it if needed."""
    today = datetime.now().strftime("%Y-%m-%d")
    path = Path(output_dir) / today
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_tweets(tweets: list[Tweet], output_dir: str = "feed_data") -> Path:
    """Save tweets to today's tweets.json file."""
    today_dir = get_today_dir(output_dir)
    tweets_file = today_dir / "tweets.json"

    data = {
        "collected_at": datetime.now().isoformat(),
        "count": len(tweets),
        "tweets": [tweet.__dict__ for tweet in tweets],
    }

    tweets_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return tweets_file


def load_tweets(output_dir: str = "feed_data") -> list[Tweet]:
    """Load tweets from today's tweets.json if it exists."""
    today_dir = get_today_dir(output_dir)
    tweets_file = today_dir / "tweets.json"

    if not tweets_file.exists():
        return []

    data = json.loads(tweets_file.read_text())
    return [Tweet(**t) for t in data.get("tweets", [])]
