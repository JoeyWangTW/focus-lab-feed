"""Data models for social media posts."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Post:
    id: str
    platform: str
    text: str
    author_handle: str
    author_name: str
    created_at: str
    url: str = ""
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    quotes: int = 0
    media_urls: list[str] = field(default_factory=list)
    video_urls: list[str] = field(default_factory=list)
    local_media_paths: list[str] = field(default_factory=list)
    is_repost: bool = False
    original_author: Optional[str] = None
    is_ad: bool = False
    top_replies: list[dict] = field(default_factory=list)
    platform_data: dict = field(default_factory=dict)


# Backward-compatible alias
Tweet = Post
