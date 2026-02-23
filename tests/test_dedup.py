"""Tests for tweet deduplication — within-run and cross-run."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import Tweet
from src.storage import deduplicate_tweets, save_tweets


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


class TestDeduplicateTweets:
    """Test cross-run deduplication via deduplicate_tweets()."""

    def test_no_existing_file(self, tmp_path):
        """All tweets are new when no existing file exists."""
        tweets = [make_tweet(id="1"), make_tweet(id="2")]
        merged, dupes = deduplicate_tweets(tweets, output_dir=str(tmp_path))

        assert len(merged) == 2
        assert dupes == 0

    def test_all_duplicates(self, tmp_path):
        """All tweets skipped when they already exist in today's file."""
        existing = [make_tweet(id="1"), make_tweet(id="2")]
        save_tweets(existing, output_dir=str(tmp_path))

        new_tweets = [make_tweet(id="1"), make_tweet(id="2")]
        merged, dupes = deduplicate_tweets(new_tweets, output_dir=str(tmp_path))

        assert len(merged) == 2  # only the existing ones
        assert dupes == 2

    def test_partial_overlap(self, tmp_path):
        """Only new tweets are added; duplicates are skipped."""
        existing = [make_tweet(id="1"), make_tweet(id="2")]
        save_tweets(existing, output_dir=str(tmp_path))

        new_tweets = [make_tweet(id="2"), make_tweet(id="3"), make_tweet(id="4")]
        merged, dupes = deduplicate_tweets(new_tweets, output_dir=str(tmp_path))

        assert len(merged) == 4  # 2 existing + 2 new
        assert dupes == 1
        merged_ids = [t.id for t in merged]
        assert "1" in merged_ids
        assert "2" in merged_ids
        assert "3" in merged_ids
        assert "4" in merged_ids

    def test_dedup_preserves_existing_order(self, tmp_path):
        """Existing tweets come first, then new tweets appended."""
        existing = [make_tweet(id="A", text="first"), make_tweet(id="B", text="second")]
        save_tweets(existing, output_dir=str(tmp_path))

        new_tweets = [make_tweet(id="C", text="third")]
        merged, dupes = deduplicate_tweets(new_tweets, output_dir=str(tmp_path))

        assert dupes == 0
        assert merged[0].id == "A"
        assert merged[1].id == "B"
        assert merged[2].id == "C"

    def test_dedup_by_id_not_content(self, tmp_path):
        """Dedup is by tweet ID, not by content."""
        existing = [make_tweet(id="1", text="original text")]
        save_tweets(existing, output_dir=str(tmp_path))

        # Same ID but different text — should be treated as duplicate
        new_tweets = [make_tweet(id="1", text="updated text")]
        merged, dupes = deduplicate_tweets(new_tweets, output_dir=str(tmp_path))

        assert len(merged) == 1
        assert dupes == 1
        assert merged[0].text == "original text"  # existing version kept

    def test_empty_new_tweets(self, tmp_path):
        """No changes when no new tweets provided."""
        existing = [make_tweet(id="1")]
        save_tweets(existing, output_dir=str(tmp_path))

        merged, dupes = deduplicate_tweets([], output_dir=str(tmp_path))

        assert len(merged) == 1
        assert dupes == 0

    def test_multiple_runs_accumulate(self, tmp_path):
        """Multiple collection runs accumulate unique tweets."""
        # First run
        run1 = [make_tweet(id="1"), make_tweet(id="2")]
        merged1, _ = deduplicate_tweets(run1, output_dir=str(tmp_path))
        save_tweets(merged1, output_dir=str(tmp_path))

        # Second run with partial overlap
        run2 = [make_tweet(id="2"), make_tweet(id="3")]
        merged2, dupes2 = deduplicate_tweets(run2, output_dir=str(tmp_path))
        save_tweets(merged2, output_dir=str(tmp_path))

        assert dupes2 == 1
        assert len(merged2) == 3

        # Third run with all duplicates
        run3 = [make_tweet(id="1"), make_tweet(id="2"), make_tweet(id="3")]
        merged3, dupes3 = deduplicate_tweets(run3, output_dir=str(tmp_path))

        assert dupes3 == 3
        assert len(merged3) == 3


class TestWithinRunDedup:
    """Test that within-run dedup still works in interceptor.parse_all_tweets()."""

    def test_same_tweet_in_multiple_responses(self):
        """Same tweet appearing in multiple GraphQL responses is stored once."""
        from src.interceptor import ResponseInterceptor

        interceptor = ResponseInterceptor()

        # Two responses with overlapping tweets
        response1 = _make_graphql_response(["t1", "t2", "t3"])
        response2 = _make_graphql_response(["t2", "t3", "t4"])

        interceptor.responses = [response1, response2]
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 4
        ids = {t.id for t in tweets}
        assert ids == {"t1", "t2", "t3", "t4"}

    def test_within_run_duplicate_in_same_response(self):
        """Same tweet ID twice in one response is stored once."""
        from src.interceptor import ResponseInterceptor

        interceptor = ResponseInterceptor()

        # Build a response with duplicate entry
        entry = _make_tweet_entry("dup1")
        response = {
            "data": {
                "home": {
                    "home_timeline_urt": {
                        "instructions": [{"entries": [entry, entry]}]
                    }
                }
            }
        }
        interceptor.responses = [response]
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 1
        assert tweets[0].id == "dup1"


def _make_tweet_entry(tweet_id: str) -> dict:
    """Build a minimal GraphQL timeline tweet entry."""
    return {
        "content": {
            "itemContent": {
                "itemType": "TimelineTweet",
                "tweet_results": {
                    "result": {
                        "__typename": "Tweet",
                        "rest_id": tweet_id,
                        "legacy": {
                            "full_text": f"Tweet {tweet_id}",
                            "created_at": "Mon Jan 01 12:00:00 +0000 2024",
                            "favorite_count": 0,
                            "retweet_count": 0,
                            "reply_count": 0,
                            "quote_count": 0,
                        },
                        "core": {
                            "user_results": {
                                "result": {
                                    "legacy": {
                                        "screen_name": "user",
                                        "name": "User",
                                    }
                                }
                            }
                        },
                    }
                },
            }
        }
    }


def _make_graphql_response(tweet_ids: list[str]) -> dict:
    """Build a minimal GraphQL response with the given tweet IDs."""
    entries = [_make_tweet_entry(tid) for tid in tweet_ids]
    return {
        "data": {
            "home": {
                "home_timeline_urt": {
                    "instructions": [{"entries": entries}]
                }
            }
        }
    }
