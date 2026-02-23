"""Main entry point — orchestrates collection run."""

import asyncio
import json
import sys
from pathlib import Path


def load_config() -> dict:
    """Load configuration from config.json."""
    config_path = Path("config.json")
    if not config_path.exists():
        print("[collector] config.json not found, using defaults")
        return {
            "scroll_delay_min": 2,
            "scroll_delay_max": 5,
            "max_tweets": 50,
            "output_dir": "feed_data",
        }
    return json.loads(config_path.read_text())


async def main():
    """Run the feed collector."""
    config = load_config()
    print(f"[collector] Loaded config: {json.dumps(config, indent=2)}")
    print("[collector] Feed collector ready.")
    print("[collector] To start collecting, ensure you have a saved session.")
    print("[collector]   1. Run 'python src/auth.py' to log in")
    print("[collector]   2. Then run this collector again to begin collection")


if __name__ == "__main__":
    asyncio.run(main())
