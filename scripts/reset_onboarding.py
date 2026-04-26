#!/usr/bin/env python3
"""Reset onboarding state so the first-time walkthrough shows again.

Onboarding is gated by `App.checkOnboardingNeeded()` in `app/static/js/app.js`:
it shows when EITHER Chromium is missing OR no workspace is configured. The
cheapest way to re-trigger it is to clear `workspace_dir` from config.json.

Flags:
    --workspace   Clear workspace_dir from config.json (default reset).
    --platforms   Delete session/*.json so platforms show as disconnected.
    --chromium    Wipe the Playwright browsers cache — forces a 150 MB reinstall.
    --all         --workspace + --platforms (does NOT touch Chromium).

Run from the project root:
    python3 scripts/reset_onboarding.py --all
    python3 scripts/reset_onboarding.py --workspace
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.paths import BROWSERS_PATH, CONFIG_PATH, SESSION_DIR, IS_BUNDLED


def reset_workspace() -> bool:
    """Drop the workspace_dir key from config.json."""
    if not CONFIG_PATH.exists():
        print(f"[skip] no config.json at {CONFIG_PATH}")
        return False
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as e:
        print(f"[err]  config.json unreadable: {e}")
        return False
    if "workspace_dir" not in cfg:
        print(f"[ok]   no workspace_dir set ({CONFIG_PATH}); already reset")
        return False
    old = cfg.pop("workspace_dir")
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    print(f"[ok]   cleared workspace_dir (was: {old})")
    return True


def reset_platforms() -> int:
    """Remove saved session state files so all platforms show disconnected."""
    if not SESSION_DIR.exists():
        print(f"[skip] no session dir at {SESSION_DIR}")
        return 0
    count = 0
    for p in SESSION_DIR.glob("*_state.json"):
        p.unlink()
        print(f"[ok]   removed session {p.name}")
        count += 1
    if count == 0:
        print(f"[ok]   no saved sessions in {SESSION_DIR}; already reset")
    return count


def reset_chromium() -> bool:
    """Nuke the Playwright browser cache — forces the Chromium setup step."""
    if not BROWSERS_PATH.exists():
        print(f"[skip] no browsers at {BROWSERS_PATH}")
        return False
    shutil.rmtree(BROWSERS_PATH)
    print(f"[ok]   removed {BROWSERS_PATH} (expect a 150 MB re-download)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Reset onboarding state.")
    ap.add_argument("--workspace", action="store_true", help="Clear workspace_dir from config.json")
    ap.add_argument("--platforms", action="store_true", help="Remove saved platform sessions")
    ap.add_argument("--chromium", action="store_true", help="Wipe Playwright browsers cache")
    ap.add_argument("--all", action="store_true", help="--workspace + --platforms (not --chromium)")
    args = ap.parse_args()

    if not any([args.workspace, args.platforms, args.chromium, args.all]):
        # Sensible default: just the workspace — lightest touch that re-triggers onboarding.
        args.workspace = True

    if args.all:
        args.workspace = True
        args.platforms = True

    mode = "bundled" if IS_BUNDLED else "dev"
    print(f"[reset_onboarding] mode={mode}")
    print(f"[reset_onboarding] config  = {CONFIG_PATH}")
    print(f"[reset_onboarding] session = {SESSION_DIR}")
    print()

    if args.workspace: reset_workspace()
    if args.platforms: reset_platforms()
    if args.chromium:  reset_chromium()

    print()
    print("Next: relaunch the app (or hit Cmd+R in the dev window) to see onboarding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
