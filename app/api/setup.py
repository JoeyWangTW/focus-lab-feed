"""Setup API endpoints — first-launch Chromium installation."""

import asyncio

from fastapi import APIRouter

from app.setup import get_setup_status, install_chromium

router = APIRouter()

_install_task = None
_install_result = None


@router.get("/status")
async def status():
    """Check setup status — is Chromium installed?"""
    result = get_setup_status()

    # Include install progress if running
    if _install_task and not _install_task.done():
        result["installing"] = True
    elif _install_result is not None:
        result["install_result"] = _install_result

    return result


@router.post("/install")
async def install():
    """Trigger Chromium installation in background."""
    global _install_task, _install_result

    # Already running?
    if _install_task and not _install_task.done():
        return {"status": "already_installing"}

    # Already installed?
    setup = get_setup_status()
    if not setup["setup_needed"]:
        return {"status": "already_installed"}

    _install_result = None

    async def _do_install():
        global _install_result
        # Run in thread to not block event loop
        loop = asyncio.get_event_loop()
        success, message = await loop.run_in_executor(None, install_chromium)
        _install_result = {"success": success, "message": message}

    _install_task = asyncio.create_task(_do_install())

    return {"status": "installing"}
