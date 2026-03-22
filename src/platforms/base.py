"""Abstract base classes for platform collectors."""

from abc import ABC, abstractmethod
from pathlib import Path

from src.models import Post


class BaseInterceptor(ABC):
    """Intercepts API responses and parses them into Post objects."""

    @abstractmethod
    async def handle_response(self, response):
        ...

    @abstractmethod
    def parse_all_posts(self, skip_ads: bool = True) -> list[Post]:
        ...


class BaseCollector(ABC):
    """Orchestrates a collection run for a single platform."""

    platform_name: str

    @abstractmethod
    async def run(self, config: dict, run_dir: Path) -> dict:
        """Run collection. Returns a summary dict."""
        ...
