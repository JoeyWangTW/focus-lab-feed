"""Tests for media_downloader module."""

import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from src.models import Tweet
from src.media_downloader import (
    download_image,
    download_tweet_images,
    _image_download_url,
)


def make_tweet(id: str, media_urls: list[str] = None) -> Tweet:
    return Tweet(
        id=id,
        text=f"Tweet {id}",
        author_handle="user",
        author_name="User",
        created_at="Mon Jan 01 00:00:00 +0000 2024",
        media_urls=media_urls or [],
    )


class FakeResponse:
    """Fake aiohttp response for testing."""

    def __init__(self, status=200, body=b"fake image data"):
        self.status = status
        self._body = body

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeSession:
    """Fake aiohttp session with configurable responses."""

    def __init__(self, responses=None, default_status=200):
        self._responses = responses or {}
        self._default_status = default_status

    def get(self, url):
        if url in self._responses:
            return self._responses[url]
        return FakeResponse(status=self._default_status)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# --- Unit tests for _image_download_url ---


def test_image_download_url_adds_large_suffix():
    url = "https://pbs.twimg.com/media/abc123.jpg"
    assert _image_download_url(url) == "https://pbs.twimg.com/media/abc123.jpg?format=jpg&name=large"


def test_image_download_url_replaces_existing_params():
    url = "https://pbs.twimg.com/media/abc123.jpg?format=jpg&name=small"
    assert _image_download_url(url) == "https://pbs.twimg.com/media/abc123.jpg?format=jpg&name=large"


# --- Unit tests for download_image ---


@pytest.mark.asyncio
async def test_download_image_success(tmp_path):
    dest = tmp_path / "media" / "test.jpg"
    session = FakeSession()
    result = await download_image(session, "https://example.com/img.jpg", dest)
    assert result is True
    assert dest.exists()
    assert dest.read_bytes() == b"fake image data"


@pytest.mark.asyncio
async def test_download_image_creates_parent_dirs(tmp_path):
    dest = tmp_path / "deep" / "nested" / "dir" / "test.jpg"
    session = FakeSession()
    result = await download_image(session, "https://example.com/img.jpg", dest)
    assert result is True
    assert dest.exists()


@pytest.mark.asyncio
async def test_download_image_http_error(tmp_path):
    dest = tmp_path / "media" / "test.jpg"
    session = FakeSession(default_status=404)
    result = await download_image(session, "https://example.com/img.jpg", dest)
    assert result is False
    assert not dest.exists()


@pytest.mark.asyncio
async def test_download_image_exception(tmp_path):
    dest = tmp_path / "media" / "test.jpg"
    session = MagicMock()
    session.get.side_effect = Exception("Connection failed")
    result = await download_image(session, "https://example.com/img.jpg", dest)
    assert result is False


# --- Integration tests for download_tweet_images ---


@pytest.mark.asyncio
async def test_download_tweet_images_no_media(tmp_path):
    tweets = [make_tweet("1"), make_tweet("2")]
    downloaded, failed = await download_tweet_images(tweets, str(tmp_path))
    assert downloaded == 0
    assert failed == 0


@pytest.mark.asyncio
async def test_download_tweet_images_saves_to_correct_paths(tmp_path):
    tweets = [
        make_tweet("100", media_urls=["https://pbs.twimg.com/media/a.jpg"]),
        make_tweet("200", media_urls=[
            "https://pbs.twimg.com/media/b.jpg",
            "https://pbs.twimg.com/media/c.jpg",
        ]),
    ]

    with patch("src.media_downloader.aiohttp.ClientSession", return_value=FakeSession()):
        downloaded, failed = await download_tweet_images(tweets, str(tmp_path))

    assert downloaded == 3
    assert failed == 0

    # Check files exist at expected locations
    from src.storage import get_today_dir
    today_dir = get_today_dir(str(tmp_path))
    assert (today_dir / "media" / "100_0.jpg").exists()
    assert (today_dir / "media" / "200_0.jpg").exists()
    assert (today_dir / "media" / "200_1.jpg").exists()


@pytest.mark.asyncio
async def test_download_tweet_images_updates_local_media_paths(tmp_path):
    tweets = [
        make_tweet("300", media_urls=[
            "https://pbs.twimg.com/media/x.jpg",
            "https://pbs.twimg.com/media/y.jpg",
        ]),
    ]

    with patch("src.media_downloader.aiohttp.ClientSession", return_value=FakeSession()):
        await download_tweet_images(tweets, str(tmp_path))

    assert len(tweets[0].local_media_paths) == 2
    assert "300_0.jpg" in tweets[0].local_media_paths[0]
    assert "300_1.jpg" in tweets[0].local_media_paths[1]


@pytest.mark.asyncio
async def test_download_tweet_images_failed_download_does_not_crash(tmp_path):
    tweets = [
        make_tweet("400", media_urls=["https://pbs.twimg.com/media/bad.jpg"]),
    ]

    with patch("src.media_downloader.aiohttp.ClientSession", return_value=FakeSession(default_status=500)):
        downloaded, failed = await download_tweet_images(tweets, str(tmp_path))

    assert downloaded == 0
    assert failed == 1
    # local_media_paths should remain empty for failed downloads
    assert tweets[0].local_media_paths == []


@pytest.mark.asyncio
async def test_download_tweet_images_mixed_success_and_failure(tmp_path):
    tweets = [
        make_tweet("500", media_urls=[
            "https://pbs.twimg.com/media/good.jpg",
            "https://pbs.twimg.com/media/bad.jpg",
        ]),
    ]

    good_url = "https://pbs.twimg.com/media/good.jpg?format=jpg&name=large"
    bad_url = "https://pbs.twimg.com/media/bad.jpg?format=jpg&name=large"
    responses = {
        good_url: FakeResponse(status=200),
        bad_url: FakeResponse(status=403),
    }
    session = FakeSession(responses=responses)

    with patch("src.media_downloader.aiohttp.ClientSession", return_value=session):
        downloaded, failed = await download_tweet_images(tweets, str(tmp_path))

    assert downloaded == 1
    assert failed == 1
    # Only the successful download should be in local_media_paths
    assert len(tweets[0].local_media_paths) == 1
    assert "500_0.jpg" in tweets[0].local_media_paths[0]


@pytest.mark.asyncio
async def test_download_tweet_images_uses_large_format_suffix(tmp_path):
    tweets = [
        make_tweet("600", media_urls=["https://pbs.twimg.com/media/test.jpg?format=jpg&name=small"]),
    ]

    called_urls = []

    class TrackingSession(FakeSession):
        def get(self, url):
            called_urls.append(url)
            return FakeResponse()

    with patch("src.media_downloader.aiohttp.ClientSession", return_value=TrackingSession()):
        await download_tweet_images(tweets, str(tmp_path))

    assert len(called_urls) == 1
    assert called_urls[0] == "https://pbs.twimg.com/media/test.jpg?format=jpg&name=large"
