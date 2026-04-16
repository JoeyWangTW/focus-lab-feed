"""Auth API endpoints — platform connection management."""

import asyncio
import json

from fastapi import APIRouter, HTTPException

from app.paths import CONFIG_PATH
from app.tasks.auth_task import (
    PLATFORM_LOGIN_URLS,
    check_session_status,
    get_session_file,
    run_auth_flow,
)
from app.tasks.manager import task_manager

router = APIRouter()

PLATFORMS = list(PLATFORM_LOGIN_URLS.keys())


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


@router.get("/status")
async def get_status():
    config = _load_config()
    statuses = {}
    for platform in PLATFORMS:
        statuses[platform] = check_session_status(platform, config)
    return statuses


@router.post("/connect/{platform}")
async def connect_platform(platform: str):
    if platform not in PLATFORMS:
        raise HTTPException(400, f"Unknown platform: {platform}")

    # Clean up any stuck/finished tasks for this platform first
    existing = task_manager.get_active_auth_task(platform)
    if existing:
        # Check if the asyncio task is actually still alive
        if existing._asyncio_task and existing._asyncio_task.done():
            # Task finished but status wasn't updated — mark it
            if existing.status in ("starting", "running", "waiting_for_login"):
                existing.status = "failed"
                existing.error = "Task ended unexpectedly"
        else:
            return {"task_id": existing.task_id, "status": existing.status, "message": "Auth already in progress"}

    task = task_manager.create_task("auth", platform)
    task._asyncio_task = asyncio.create_task(run_auth_flow(task))

    return {"task_id": task.task_id, "status": task.status}


@router.get("/connect/{platform}/status")
async def get_connect_status(platform: str):
    if platform not in PLATFORMS:
        raise HTTPException(400, f"Unknown platform: {platform}")

    task = task_manager.get_active_auth_task(platform)
    if not task:
        for t in reversed(task_manager.get_tasks_by_type("auth")):
            if t.platform == platform:
                return t.to_dict()
        return {"status": "idle", "platform": platform}

    return task.to_dict()


@router.post("/connect/{platform}/complete")
async def complete_connect(platform: str):
    task = task_manager.get_active_auth_task(platform)
    if not task:
        raise HTTPException(404, "No active auth task for this platform")

    if task.status != "waiting_for_login":
        raise HTTPException(400, f"Auth task is in state '{task.status}', not waiting for login")

    task._event.set()

    for _ in range(20):
        if task.status in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.25)

    return task.to_dict()


@router.post("/connect/{platform}/cancel")
async def cancel_connect(platform: str):
    """Cancel an in-progress auth flow and close the browser."""
    task = task_manager.get_active_auth_task(platform)
    if not task:
        return {"status": "no_active_task", "platform": platform}

    # Signal cancellation
    task._cancel_flag = True
    task._event.set()

    # Also cancel the asyncio task to force cleanup
    if task._asyncio_task and not task._asyncio_task.done():
        task._asyncio_task.cancel()

    # Wait briefly for cleanup
    for _ in range(10):
        if task.status in ("cancelled", "failed"):
            break
        await asyncio.sleep(0.25)

    # Force status if still stuck
    if task.status not in ("cancelled", "failed", "completed"):
        task.status = "cancelled"
        task.error = "Cancelled by user"

    return task.to_dict()


@router.post("/disconnect/{platform}")
async def disconnect_platform(platform: str):
    if platform not in PLATFORMS:
        raise HTTPException(400, f"Unknown platform: {platform}")

    config = _load_config()
    session_file = get_session_file(platform, config)

    if session_file.exists():
        session_file.unlink()
        return {"status": "disconnected", "platform": platform}

    return {"status": "already_disconnected", "platform": platform}
