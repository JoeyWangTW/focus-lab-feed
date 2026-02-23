"""Tests for tweet parsing from GraphQL responses."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.interceptor import ResponseInterceptor
from src.models import Tweet


def make_tweet_result(
    tweet_id="123",
    text="Hello world",
    screen_name="testuser",
    name="Test User",
    created_at="Mon Jan 01 12:00:00 +0000 2024",
    favorite_count=10,
    retweet_count=5,
    reply_count=2,
    quote_count=1,
    media=None,
    retweeted_status_result=None,
):
    """Build a minimal tweet_results.result object."""
    legacy = {
        "full_text": text,
        "created_at": created_at,
        "favorite_count": favorite_count,
        "retweet_count": retweet_count,
        "reply_count": reply_count,
        "quote_count": quote_count,
    }
    if media:
        legacy["extended_entities"] = {"media": media}
    if retweeted_status_result:
        legacy["retweeted_status_result"] = {"result": retweeted_status_result}

    return {
        "__typename": "Tweet",
        "rest_id": tweet_id,
        "core": {
            "user_results": {
                "result": {
                    "legacy": {
                        "screen_name": screen_name,
                        "name": name,
                    }
                }
            }
        },
        "legacy": legacy,
    }


def make_entry(tweet_result, entry_id="tweet-123", promoted=False):
    """Wrap a tweet result into a timeline entry."""
    item_content = {
        "itemType": "TimelineTweet",
        "__typename": "TimelineTweet",
        "tweet_results": {"result": tweet_result},
    }
    if promoted:
        item_content["promotedMetadata"] = {"advertiser_results": {}}
    return {
        "entryId": entry_id,
        "content": {
            "entryType": "TimelineTimelineItem",
            "__typename": "TimelineTimelineItem",
            "itemContent": item_content,
        },
    }


def make_response(entries):
    """Wrap entries into a full GraphQL response body."""
    return {
        "data": {
            "home": {
                "home_timeline_urt": {
                    "instructions": [
                        {
                            "type": "TimelineAddEntries",
                            "entries": entries,
                        }
                    ]
                }
            }
        }
    }


def make_cursor_entry(entry_id="cursor-top"):
    """Build a cursor entry (non-tweet)."""
    return {
        "entryId": entry_id,
        "content": {
            "entryType": "TimelineTimelineCursor",
            "itemContent": {
                "itemType": "TimelineCursor",
                "value": "some-cursor-value",
            },
        },
    }


class TestTweetParsing:
    """Test parsing of individual tweets."""

    def test_basic_tweet(self):
        result = make_tweet_result()
        entry = make_entry(result)
        response = make_response([entry])

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response)
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 1
        tweet = tweets[0]
        assert tweet.id == "123"
        assert tweet.text == "Hello world"
        assert tweet.author_handle == "testuser"
        assert tweet.author_name == "Test User"
        assert tweet.likes == 10
        assert tweet.retweets == 5
        assert tweet.replies == 2
        assert tweet.quotes == 1
        assert tweet.is_retweet is False
        assert tweet.original_author is None
        assert tweet.is_ad is False

    def test_tweet_with_media(self):
        media = [
            {"media_url_https": "https://pbs.twimg.com/media/img1.jpg"},
            {"media_url_https": "https://pbs.twimg.com/media/img2.jpg"},
        ]
        result = make_tweet_result(media=media)
        entry = make_entry(result)
        response = make_response([entry])

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response)
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 1
        assert len(tweets[0].media_urls) == 2
        assert tweets[0].media_urls[0] == "https://pbs.twimg.com/media/img1.jpg"

    def test_promoted_tweet_skipped(self):
        result = make_tweet_result(tweet_id="ad-1", text="Buy stuff!")
        entry = make_entry(result, entry_id="promoted-tweet-1", promoted=True)
        response = make_response([entry])

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response)
        tweets = interceptor.parse_all_tweets(skip_ads=True)

        assert len(tweets) == 0

    def test_promoted_tweet_kept_when_not_skipping(self):
        result = make_tweet_result(tweet_id="ad-1", text="Buy stuff!")
        entry = make_entry(result, entry_id="promoted-tweet-1", promoted=True)
        response = make_response([entry])

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response)
        tweets = interceptor.parse_all_tweets(skip_ads=False)

        assert len(tweets) == 1
        assert tweets[0].is_ad is True

    def test_retweet(self):
        original = make_tweet_result(
            tweet_id="original-1",
            text="Original text",
            screen_name="originaluser",
            name="Original User",
        )
        rt = make_tweet_result(
            tweet_id="rt-1",
            text="RT @originaluser: Original text",
            screen_name="retweeter",
            name="Retweeter",
            retweeted_status_result=original,
        )
        entry = make_entry(rt, entry_id="tweet-rt-1")
        response = make_response([entry])

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response)
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 1
        tweet = tweets[0]
        assert tweet.id == "rt-1"
        assert tweet.is_retweet is True
        assert tweet.original_author == "retweeter"
        assert tweet.author_handle == "originaluser"
        assert tweet.text == "Original text"

    def test_cursor_entries_skipped(self):
        tweet_entry = make_entry(make_tweet_result())
        cursor_entry = make_cursor_entry()
        response = make_response([tweet_entry, cursor_entry])

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response)
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 1

    def test_tweet_with_visibility_results_wrapper(self):
        inner = make_tweet_result(tweet_id="wrapped-1", text="Wrapped tweet")
        wrapped = {
            "__typename": "TweetWithVisibilityResults",
            "tweet": inner,
        }
        entry = make_entry(wrapped, entry_id="tweet-wrapped-1")
        response = make_response([entry])

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response)
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 1
        assert tweets[0].id == "wrapped-1"
        assert tweets[0].text == "Wrapped tweet"

    def test_missing_fields_handled_gracefully(self):
        """Tweet with minimal data should not crash."""
        minimal = {
            "__typename": "Tweet",
            "rest_id": "minimal-1",
            "core": {},
            "legacy": {"full_text": "Just text, nothing else"},
        }
        entry = make_entry(minimal, entry_id="tweet-minimal-1")
        response = make_response([entry])

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response)
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 1
        assert tweets[0].text == "Just text, nothing else"
        assert tweets[0].author_handle == ""
        assert tweets[0].likes == 0
        assert tweets[0].media_urls == []

    def test_empty_response_handled(self):
        response = {"data": {}}

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response)
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 0

    def test_deduplication_across_responses(self):
        """Same tweet in multiple responses should appear once."""
        result = make_tweet_result(tweet_id="dup-1")
        entry = make_entry(result, entry_id="tweet-dup-1")
        response1 = make_response([entry])
        response2 = make_response([entry])

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response1)
        interceptor.responses.append(response2)
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 1

    def test_multiple_tweets_parsed(self):
        """Verify at least 10 tweets can be parsed from a response."""
        entries = []
        for i in range(15):
            result = make_tweet_result(
                tweet_id=f"tweet-{i}",
                text=f"Tweet number {i}",
                screen_name=f"user{i}",
                name=f"User {i}",
            )
            entries.append(make_entry(result, entry_id=f"tweet-{i}"))

        response = make_response(entries)

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response)
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 15
        assert len(tweets) >= 10  # AC: at least 10 from single interception

    def test_malformed_tweet_result_skipped(self):
        """Completely malformed entry should not crash the parser."""
        good = make_entry(make_tweet_result(tweet_id="good-1"), entry_id="tweet-good")
        bad = {
            "entryId": "tweet-bad",
            "content": {
                "itemContent": {
                    "itemType": "TimelineTweet",
                    "tweet_results": {"result": None},
                },
            },
        }
        response = make_response([good, bad])

        interceptor = ResponseInterceptor()
        interceptor.responses.append(response)
        tweets = interceptor.parse_all_tweets()

        assert len(tweets) == 1
        assert tweets[0].id == "good-1"
