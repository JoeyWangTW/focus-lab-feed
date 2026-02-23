"""Tests for structured data output — save/load round-trip and metadata."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import Tweet
from src.storage import save_tweets, load_tweets_from_file, load_tweets


def make_tweet(**kwargs) -> Tweet:
    """Build a Tweet with sensible defaults."""
    defaults = {
        "id": "123",
        "text": "Hello world",
        "author_handle": "testuser",
        "author_name": "Test User",
        "created_at": "Mon Jan 01 12:00:00 +0000 2024",
        "likes": 10,
        "retweets": 5,
        "replies": 2,
        "quotes": 1,
        "media_urls": [],
        "local_media_paths": [],
        "is_retweet": False,
        "original_author": None,
        "is_ad": False,
    }
    defaults.update(kwargs)
    return Tweet(**defaults)


class TestSaveTweets:
    """Test saving tweets to JSON."""

    def test_saves_to_tweets_json(self, tmp_path):
        tweets = [make_tweet()]
        result = save_tweets(tweets, output_dir=str(tmp_path))

        assert result.name == "tweets.json"
        assert result.exists()

    def test_json_is_pretty_printed(self, tmp_path):
        tweets = [make_tweet()]
        result = save_tweets(tweets, output_dir=str(tmp_path))
        content = result.read_text()

        # Pretty-printed JSON has newlines and indentation
        assert "\n" in content
        lines = content.split("\n")
        # Should have indented lines (more than just opening/closing braces)
        indented = [l for l in lines if l.startswith("  ")]
        assert len(indented) > 0

    def test_metadata_included(self, tmp_path):
        tweets = [make_tweet(), make_tweet(id="456")]
        result = save_tweets(tweets, output_dir=str(tmp_path), duration_seconds=12.345)
        data = json.loads(result.read_text())

        assert "metadata" in data
        meta = data["metadata"]
        assert "run_timestamp" in meta
        assert meta["tweet_count"] == 2
        assert meta["collection_duration_seconds"] == 12.35  # rounded to 2 decimals

    def test_metadata_without_duration(self, tmp_path):
        tweets = [make_tweet()]
        result = save_tweets(tweets, output_dir=str(tmp_path))
        data = json.loads(result.read_text())

        meta = data["metadata"]
        assert meta["collection_duration_seconds"] is None

    def test_tweets_array_present(self, tmp_path):
        tweets = [make_tweet(id="1"), make_tweet(id="2"), make_tweet(id="3")]
        result = save_tweets(tweets, output_dir=str(tmp_path))
        data = json.loads(result.read_text())

        assert "tweets" in data
        assert len(data["tweets"]) == 3

    def test_tweet_fields_preserved(self, tmp_path):
        tweet = make_tweet(
            id="999",
            text="Test text",
            author_handle="handle",
            author_name="Name",
            likes=42,
            retweets=7,
            media_urls=["https://example.com/img.jpg"],
            is_retweet=True,
            original_author="someone",
        )
        result = save_tweets([tweet], output_dir=str(tmp_path))
        data = json.loads(result.read_text())

        saved = data["tweets"][0]
        assert saved["id"] == "999"
        assert saved["text"] == "Test text"
        assert saved["author_handle"] == "handle"
        assert saved["likes"] == 42
        assert saved["media_urls"] == ["https://example.com/img.jpg"]
        assert saved["is_retweet"] is True
        assert saved["original_author"] == "someone"

    def test_output_dir_structure(self, tmp_path):
        tweets = [make_tweet()]
        result = save_tweets(tweets, output_dir=str(tmp_path))

        # Should be in a date-stamped subdirectory
        assert result.parent.parent == tmp_path
        # Date directory name should be YYYY-MM-DD format
        date_dir = result.parent.name
        parts = date_dir.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4  # year


class TestLoadTweets:
    """Test loading tweets back from JSON."""

    def test_round_trip(self, tmp_path):
        """Save and load should produce identical Tweet objects."""
        original = [
            make_tweet(id="1", text="First"),
            make_tweet(id="2", text="Second", is_retweet=True, original_author="other"),
        ]
        save_tweets(original, output_dir=str(tmp_path))

        # load_tweets uses get_today_dir internally, so use load_tweets_from_file
        tweets_file = list(tmp_path.rglob("tweets.json"))[0]
        loaded = load_tweets_from_file(tweets_file)

        assert len(loaded) == 2
        assert loaded[0].id == "1"
        assert loaded[0].text == "First"
        assert loaded[1].id == "2"
        assert loaded[1].is_retweet is True
        assert loaded[1].original_author == "other"

    def test_round_trip_with_media(self, tmp_path):
        original = [make_tweet(media_urls=["https://img1.jpg", "https://img2.jpg"])]
        save_tweets(original, output_dir=str(tmp_path))

        tweets_file = list(tmp_path.rglob("tweets.json"))[0]
        loaded = load_tweets_from_file(tweets_file)

        assert loaded[0].media_urls == ["https://img1.jpg", "https://img2.jpg"]

    def test_round_trip_all_fields(self, tmp_path):
        """Every field should survive the round-trip."""
        original = make_tweet(
            id="rt-1",
            text="Full tweet",
            author_handle="author",
            author_name="Author Name",
            created_at="Tue Feb 01 10:00:00 +0000 2024",
            likes=100,
            retweets=50,
            replies=25,
            quotes=10,
            media_urls=["https://img.jpg"],
            local_media_paths=["/path/to/img.jpg"],
            is_retweet=True,
            original_author="retweeter",
            is_ad=False,
        )
        save_tweets([original], output_dir=str(tmp_path))

        tweets_file = list(tmp_path.rglob("tweets.json"))[0]
        loaded = load_tweets_from_file(tweets_file)[0]

        assert loaded.id == original.id
        assert loaded.text == original.text
        assert loaded.author_handle == original.author_handle
        assert loaded.author_name == original.author_name
        assert loaded.created_at == original.created_at
        assert loaded.likes == original.likes
        assert loaded.retweets == original.retweets
        assert loaded.replies == original.replies
        assert loaded.quotes == original.quotes
        assert loaded.media_urls == original.media_urls
        assert loaded.local_media_paths == original.local_media_paths
        assert loaded.is_retweet == original.is_retweet
        assert loaded.original_author == original.original_author
        assert loaded.is_ad == original.is_ad

    def test_load_empty_dir(self, tmp_path):
        """Loading from directory with no tweets.json returns empty list."""
        loaded = load_tweets(output_dir=str(tmp_path))
        assert loaded == []

    def test_valid_json_structure(self, tmp_path):
        """Verify the output JSON can be parsed as valid JSON."""
        tweets = [make_tweet(id=str(i)) for i in range(10)]
        result = save_tweets(tweets, output_dir=str(tmp_path), duration_seconds=5.5)

        # Should parse without errors
        data = json.loads(result.read_text())
        assert isinstance(data, dict)
        assert isinstance(data["metadata"], dict)
        assert isinstance(data["tweets"], list)
        assert data["metadata"]["tweet_count"] == 10
