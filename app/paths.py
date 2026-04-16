"""Centralized path resolution for bundled and development modes.

When running from source (dev): paths resolve relative to project root.
When bundled with PyInstaller: data goes to ~/Library/Application Support/,
browsers go to ~/Library/Caches/, and static assets come from _MEIPASS.
"""

import json
import os
import platform
import shutil
import sys
from pathlib import Path

# Detect PyInstaller bundle
IS_BUNDLED = getattr(sys, "_MEIPASS", None) is not None
MEIPASS = Path(sys._MEIPASS) if IS_BUNDLED else None

# Project root (only valid in dev mode)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get_data_dir() -> Path:
    """User data directory for config, sessions, and collected data."""
    if not IS_BUNDLED:
        return PROJECT_ROOT

    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    return base / "Focus Lab Feed Collector"


def _get_cache_dir() -> Path:
    """Cache directory for Playwright browsers."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Caches"
    elif system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))

    return base / "focus-lab-feed-collector"


# Core paths
DATA_DIR = _get_data_dir()
CACHE_DIR = _get_cache_dir()
BROWSERS_PATH = CACHE_DIR / "playwright"

# Derived paths
CONFIG_PATH = DATA_DIR / "config.json"
SESSION_DIR = DATA_DIR / "session"
FEED_DATA_DIR = DATA_DIR / "feed_data"

# Static assets (HTML/CSS/JS)
if IS_BUNDLED:
    STATIC_DIR = MEIPASS / "app" / "static"
else:
    STATIC_DIR = Path(__file__).resolve().parent / "static"


def get_default_config() -> dict:
    """Return the default config.json content."""
    return {
        "output_dir": str(FEED_DATA_DIR),
        "platforms": {
            "twitter": {
                "enabled": True,
                "scroll_delay_min": 2,
                "scroll_delay_max": 5,
                "max_posts": 50,
                "max_minutes": 5,
                "oldest_post_date": None,
                "max_reply_tweets": 20,
                "max_replies_per_tweet": 5,
                "reply_batch_size": 4,
                "session_file": str(SESSION_DIR / "twitter_state.json"),
            },
            "threads": {
                "enabled": True,
                "scroll_delay_min": 3,
                "scroll_delay_max": 6,
                "max_posts": 50,
                "max_minutes": 5,
                "session_file": str(SESSION_DIR / "threads_state.json"),
            },
            "instagram": {
                "enabled": True,
                "scroll_delay_min": 3,
                "scroll_delay_max": 7,
                "max_posts": 50,
                "max_minutes": 5,
                "session_file": str(SESSION_DIR / "instagram_state.json"),
            },
            "youtube": {
                "enabled": True,
                "scroll_delay_min": 2,
                "scroll_delay_max": 5,
                "max_posts": 50,
                "max_minutes": 5,
                "session_file": str(SESSION_DIR / "youtube_state.json"),
            },
        },
    }


def initialize():
    """Create data directories and default config on first launch."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    FEED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Copy default config if missing
    if not CONFIG_PATH.exists():
        if not IS_BUNDLED and (PROJECT_ROOT / "config.json").exists():
            # Dev mode: copy existing config
            shutil.copy2(PROJECT_ROOT / "config.json", CONFIG_PATH)
        else:
            # Bundled or no existing config: write defaults
            CONFIG_PATH.write_text(json.dumps(get_default_config(), indent=2))

    # Set Playwright browser path
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_PATH)
