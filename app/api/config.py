"""Config API endpoints — read/update config.json."""

import json

from fastapi import APIRouter, HTTPException

from app.paths import CONFIG_PATH

router = APIRouter()


def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"output_dir": "feed_data", "platforms": {}}
    return json.loads(CONFIG_PATH.read_text())


@router.get("")
async def get_config():
    return _read_config()


@router.patch("")
async def update_config(updates: dict):
    """Partial update to config. Merges into existing config."""
    config = _read_config()

    # Deep merge platform settings
    if "platforms" in updates:
        for platform, settings in updates["platforms"].items():
            if platform not in config.get("platforms", {}):
                raise HTTPException(400, f"Unknown platform: {platform}")
            config["platforms"][platform].update(settings)
        del updates["platforms"]

    # Top-level merge
    config.update(updates)

    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    return config
