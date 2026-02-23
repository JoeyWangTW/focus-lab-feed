"""Tests for scroll automation."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import Tweet
from src.scroller import scroll_feed, scroll_loop, _parse_twitter_date, _has_tweet_older_than


def make_tweet(tweet_id: str) -> Tweet:
    return Tweet(
        id=tweet_id,
        text=f"Tweet {tweet_id}",
        author_handle="user",
        author_name="User",
        created_at="Mon Jan 01 12:00:00 +0000 2024",
    )


def make_tweet_with_date(tweet_id: str, date_str: str) -> Tweet:
    return Tweet(
        id=tweet_id,
        text=f"Tweet {tweet_id}",
        author_handle="user",
        author_name="User",
        created_at=date_str,
    )


def make_mock_page():
    """Create a mock Playwright page."""
    page = AsyncMock()
    page.evaluate = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    return page


class FakeInterceptor:
    """Fake interceptor that returns a growing list of tweets."""

    def __init__(self, tweet_schedule: list[int]):
        """tweet_schedule: list of tweet counts to return on each parse_all_tweets call."""
        self._schedule = tweet_schedule
        self._call_index = 0

    def parse_all_tweets(self, skip_ads=True) -> list[Tweet]:
        if self._call_index < len(self._schedule):
            count = self._schedule[self._call_index]
        else:
            count = self._schedule[-1] if self._schedule else 0
        self._call_index += 1
        return [make_tweet(str(i)) for i in range(count)]


@pytest.mark.asyncio
async def test_scroll_feed_scrolls_page():
    """scroll_feed calls page.evaluate to scroll down."""
    page = make_mock_page()
    delay = await scroll_feed(page, delay_min=0.01, delay_max=0.02)
    page.evaluate.assert_called_once_with("window.scrollBy(0, window.innerHeight)")
    assert 0.01 <= delay <= 0.02


@pytest.mark.asyncio
async def test_scroll_loop_stops_at_max_tweets():
    """Scroll loop stops when max_tweets is reached."""
    page = make_mock_page()
    # Initial call returns 5, then after scroll returns 10 (>= max_tweets=10)
    interceptor = FakeInterceptor([5, 10])

    result = await scroll_loop(
        page, interceptor,
        delay_min=0.01, delay_max=0.02,
        max_tweets=10,
    )

    assert result["total_tweets"] == 10
    assert "max_tweets" in result["stop_reason"]


@pytest.mark.asyncio
async def test_scroll_loop_stops_at_max_tweets_before_first_scroll():
    """If initial load already has enough tweets, no scrolling happens."""
    page = make_mock_page()
    interceptor = FakeInterceptor([50])

    result = await scroll_loop(
        page, interceptor,
        delay_min=0.01, delay_max=0.02,
        max_tweets=50,
    )

    assert result["scroll_count"] == 0
    assert result["total_tweets"] == 50
    assert "max_tweets" in result["stop_reason"]


@pytest.mark.asyncio
async def test_scroll_loop_stops_on_stale():
    """Scroll loop stops after N stale scrolls with no new tweets."""
    page = make_mock_page()
    # Initial: 5 tweets, then stays at 5 for 3 more calls (3 stale scrolls)
    interceptor = FakeInterceptor([5, 5, 5, 5])

    result = await scroll_loop(
        page, interceptor,
        delay_min=0.01, delay_max=0.02,
        max_tweets=100,
        stale_limit=3,
    )

    assert result["scroll_count"] == 3
    assert result["total_tweets"] == 5
    assert "No new tweets" in result["stop_reason"]


@pytest.mark.asyncio
async def test_scroll_loop_resets_stale_on_new_tweets():
    """Stale counter resets when new tweets arrive."""
    page = make_mock_page()
    # Initial: 5, stale, stale, then +5 new (resets stale), then stale x3 -> stop
    interceptor = FakeInterceptor([5, 5, 5, 10, 10, 10, 10])

    result = await scroll_loop(
        page, interceptor,
        delay_min=0.01, delay_max=0.02,
        max_tweets=100,
        stale_limit=3,
    )

    assert result["scroll_count"] == 6
    assert result["total_tweets"] == 10
    assert "No new tweets" in result["stop_reason"]


@pytest.mark.asyncio
async def test_scroll_loop_returns_scroll_count():
    """Scroll count tracks how many times the page was scrolled."""
    page = make_mock_page()
    # 5, 10, 15, 20 (reaches max_tweets=20 after 3 scrolls)
    interceptor = FakeInterceptor([5, 10, 15, 20])

    result = await scroll_loop(
        page, interceptor,
        delay_min=0.01, delay_max=0.02,
        max_tweets=20,
    )

    assert result["scroll_count"] == 3
    assert result["total_tweets"] == 20


@pytest.mark.asyncio
async def test_scroll_loop_stats_dict_keys():
    """Return dict has expected keys."""
    page = make_mock_page()
    interceptor = FakeInterceptor([50])

    result = await scroll_loop(
        page, interceptor,
        delay_min=0.01, delay_max=0.02,
        max_tweets=50,
    )

    assert "scroll_count" in result
    assert "total_tweets" in result
    assert "stop_reason" in result


@pytest.mark.asyncio
async def test_scroll_feed_random_delay_range():
    """Delay is within the configured range."""
    page = make_mock_page()
    delays = []
    for _ in range(20):
        d = await scroll_feed(page, delay_min=0.01, delay_max=0.05)
        delays.append(d)
    assert all(0.01 <= d <= 0.05 for d in delays)


@pytest.mark.asyncio
async def test_scroll_loop_zero_initial_tweets():
    """Handles case where initial load has zero tweets and stays stale."""
    page = make_mock_page()
    interceptor = FakeInterceptor([0, 0, 0, 0])

    result = await scroll_loop(
        page, interceptor,
        delay_min=0.01, delay_max=0.02,
        max_tweets=50,
        stale_limit=3,
    )

    assert result["scroll_count"] == 3
    assert result["total_tweets"] == 0
    assert "No new tweets" in result["stop_reason"]


# --- Stop condition tests: max_minutes ---


@pytest.mark.asyncio
async def test_scroll_loop_stops_at_max_minutes():
    """Scroll loop stops when max_minutes is exceeded."""
    page = make_mock_page()
    # 5 tweets initially, growing — but time will run out first
    interceptor = FakeInterceptor([5, 10, 15, 20, 25])

    # Simulate time: start at 0, then jump to 6 minutes on second call
    time_values = iter([0.0, 360.0, 360.0, 360.0])
    with patch("src.scroller.time.monotonic", side_effect=time_values):
        result = await scroll_loop(
            page, interceptor,
            delay_min=0.01, delay_max=0.02,
            max_tweets=100,
            max_minutes=5,
        )

    assert "max_minutes" in result["stop_reason"]
    assert result["scroll_count"] == 0  # time check fires at top of loop, before scrolling


@pytest.mark.asyncio
async def test_scroll_loop_max_minutes_not_reached():
    """max_minutes doesn't trigger if time hasn't elapsed."""
    page = make_mock_page()
    interceptor = FakeInterceptor([50])

    # Time stays at 0 — max_tweets fires first
    with patch("src.scroller.time.monotonic", return_value=0.0):
        result = await scroll_loop(
            page, interceptor,
            delay_min=0.01, delay_max=0.02,
            max_tweets=50,
            max_minutes=5,
        )

    assert "max_tweets" in result["stop_reason"]


@pytest.mark.asyncio
async def test_scroll_loop_max_minutes_before_max_tweets():
    """Time limit fires before tweet limit when time runs out first."""
    page = make_mock_page()
    interceptor = FakeInterceptor([5, 10, 15])

    # Start at 0, then 6 minutes later on second check
    time_values = iter([0.0, 360.0, 360.0])
    with patch("src.scroller.time.monotonic", side_effect=time_values):
        result = await scroll_loop(
            page, interceptor,
            delay_min=0.01, delay_max=0.02,
            max_tweets=100,
            max_minutes=5,
        )

    assert "max_minutes" in result["stop_reason"]


# --- Stop condition tests: oldest_tweet_date ---


class FakeDateInterceptor:
    """Fake interceptor that returns specific tweet batches with dates."""

    def __init__(self, tweet_batches: list[list[Tweet]]):
        self._batches = tweet_batches
        self._call_index = 0

    def parse_all_tweets(self, skip_ads=True) -> list[Tweet]:
        if self._call_index < len(self._batches):
            batch = self._batches[self._call_index]
        else:
            batch = self._batches[-1] if self._batches else []
        self._call_index += 1
        return batch


@pytest.mark.asyncio
async def test_scroll_loop_stops_at_oldest_tweet_date():
    """Scroll loop stops when a tweet older than oldest_tweet_date is found."""
    page = make_mock_page()

    recent_tweets = [
        make_tweet_with_date("1", "Mon Feb 10 12:00:00 +0000 2025"),
        make_tweet_with_date("2", "Sun Feb 09 12:00:00 +0000 2025"),
    ]
    old_tweets = recent_tweets + [
        make_tweet_with_date("3", "Sat Jan 01 12:00:00 +0000 2025"),  # older than threshold
    ]
    # Call sequence: initial check (recent), date check (recent), after scroll count+date check (old)
    interceptor = FakeDateInterceptor([recent_tweets, recent_tweets, old_tweets, old_tweets])

    result = await scroll_loop(
        page, interceptor,
        delay_min=0.01, delay_max=0.02,
        max_tweets=100,
        oldest_tweet_date="2025-02-01",
    )

    assert "older than" in result["stop_reason"]
    assert result["total_tweets"] == 3


@pytest.mark.asyncio
async def test_scroll_loop_oldest_tweet_date_not_triggered():
    """oldest_tweet_date doesn't trigger if all tweets are recent enough."""
    page = make_mock_page()

    recent_tweets = [
        make_tweet_with_date("1", "Mon Feb 10 12:00:00 +0000 2025"),
        make_tweet_with_date("2", "Sun Feb 09 12:00:00 +0000 2025"),
    ]
    # Returns 2 tweets initially, which is >= max_tweets=2
    interceptor = FakeDateInterceptor([recent_tweets, recent_tweets])

    result = await scroll_loop(
        page, interceptor,
        delay_min=0.01, delay_max=0.02,
        max_tweets=2,
        oldest_tweet_date="2025-01-01",
    )

    # max_tweets fires first — all tweets are newer than threshold
    assert "max_tweets" in result["stop_reason"]


@pytest.mark.asyncio
async def test_scroll_loop_oldest_tweet_date_initial_load():
    """oldest_tweet_date triggers on initial load before any scrolling."""
    page = make_mock_page()

    old_tweets = [
        make_tweet_with_date("1", "Mon Dec 01 12:00:00 +0000 2024"),
    ]
    interceptor = FakeDateInterceptor([old_tweets, old_tweets])

    result = await scroll_loop(
        page, interceptor,
        delay_min=0.01, delay_max=0.02,
        max_tweets=100,
        oldest_tweet_date="2025-01-01",
    )

    assert "older than" in result["stop_reason"]
    assert result["scroll_count"] == 0


# --- Helper function tests ---


def test_parse_twitter_date_valid():
    """Parses standard Twitter date format."""
    dt = _parse_twitter_date("Mon Jan 01 12:00:00 +0000 2024")
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 1


def test_parse_twitter_date_invalid():
    """Returns None for invalid date strings."""
    assert _parse_twitter_date("not a date") is None
    assert _parse_twitter_date("") is None
    assert _parse_twitter_date(None) is None


def test_has_tweet_older_than_true():
    """Detects tweets older than the threshold date."""
    from datetime import datetime
    tweets = [
        make_tweet_with_date("1", "Mon Feb 10 12:00:00 +0000 2025"),
        make_tweet_with_date("2", "Sat Dec 01 12:00:00 +0000 2024"),
    ]
    threshold = datetime(2025, 1, 1)
    assert _has_tweet_older_than(tweets, threshold) is True


def test_has_tweet_older_than_false():
    """Returns False when all tweets are newer than threshold."""
    from datetime import datetime
    tweets = [
        make_tweet_with_date("1", "Mon Feb 10 12:00:00 +0000 2025"),
        make_tweet_with_date("2", "Sun Feb 09 12:00:00 +0000 2025"),
    ]
    threshold = datetime(2025, 1, 1)
    assert _has_tweet_older_than(tweets, threshold) is False


def test_has_tweet_older_than_unparseable_dates():
    """Gracefully handles tweets with unparseable dates."""
    from datetime import datetime
    tweets = [
        make_tweet_with_date("1", "not a date"),
        make_tweet_with_date("2", ""),
    ]
    threshold = datetime(2025, 1, 1)
    assert _has_tweet_older_than(tweets, threshold) is False
