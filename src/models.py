"""Data models for tweet and media objects."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Tweet:
    id: str
    text: str
    author_handle: str
    author_name: str
    created_at: str
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    quotes: int = 0
    media_urls: list[str] = field(default_factory=list)
    local_media_paths: list[str] = field(default_factory=list)
    is_retweet: bool = False
    original_author: Optional[str] = None
    is_ad: bool = False
