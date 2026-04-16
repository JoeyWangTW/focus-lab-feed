"""First-launch setup — Chromium browser installation for Playwright."""

import os
import subprocess
import sys
from pathlib import Path

from app.paths import BROWSERS_PATH, IS_BUNDLED


def _check_path_for_chromium(path: Path) -> bool:
    """Check if a directory contains a Chromium installation."""
    if not path.exists():
        return False
    for item in path.iterdir():
        if item.is_dir() and item.name.startswith("chromium"):
            return True
    return False


def is_chromium_installed() -> bool:
    """Check if Playwright's Chromium browser is available."""
    # Check our custom path first
    if _check_path_for_chromium(BROWSERS_PATH):
        return True

    # In dev mode, also check the default Playwright cache
    if not IS_BUNDLED:
        default_cache = Path.home() / "Library" / "Caches" / "ms-playwright"
        if _check_path_for_chromium(default_cache):
            return True

    return False


def _find_python() -> str:
    """Find a working Python executable for subprocess calls."""
    if not IS_BUNDLED:
        return sys.executable

    # When bundled, sys.executable is the app binary, not Python.
    # Try to find a system Python.
    import shutil
    for name in ("python3", "python"):
        path = shutil.which(name)
        if path:
            return path

    raise RuntimeError("Could not find a Python interpreter. Please install Python 3.11+.")


def install_chromium() -> tuple[bool, str]:
    """Install Playwright Chromium browser. Returns (success, message)."""
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_PATH)
    BROWSERS_PATH.mkdir(parents=True, exist_ok=True)

    try:
        python = _find_python()

        # First ensure playwright package is available
        # In bundled mode, use playwright's internal install CLI directly
        if IS_BUNDLED:
            # Use playwright's bundled node + CLI directly
            from playwright._impl._driver import compute_driver_executable
            node_path, cli_path = compute_driver_executable()
            cmd = [str(node_path), str(cli_path), "install", "chromium"]
        else:
            cmd = [python, "-m", "playwright", "install", "chromium"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes max
            env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(BROWSERS_PATH)},
        )

        if result.returncode == 0:
            return True, "Chromium installed successfully"
        else:
            error = result.stderr or result.stdout or "Unknown error"
            return False, f"Installation failed: {error}"

    except subprocess.TimeoutExpired:
        return False, "Installation timed out (5 minutes)"
    except Exception as e:
        return False, f"Installation error: {e}"


def get_setup_status() -> dict:
    """Get overall setup status."""
    chromium = is_chromium_installed()
    return {
        "chromium_installed": chromium,
        "setup_needed": not chromium,
        "browsers_path": str(BROWSERS_PATH),
    }
