"""Background task tracking for auth and collection flows."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TrackedTask:
    task_id: str
    task_type: str  # "auth" or "collection"
    platform: str
    status: str = "starting"  # starting, running, waiting_for_login, completed, failed, cancelled
    started_at: str = ""
    job_id: str = ""  # collection-only: groups platforms run together for auto-export
    progress: dict = field(default_factory=dict)
    summary: dict | None = None
    error: str | None = None
    _asyncio_task: asyncio.Task | None = field(default=None, repr=False)
    _event: asyncio.Event | None = field(default=None, repr=False)
    _cancel_flag: bool = False

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "platform": self.platform,
            "status": self.status,
            "started_at": self.started_at,
            "progress": self.progress,
            "summary": self.summary,
            "error": self.error,
        }


class TaskManager:
    """Manages background auth and collection tasks."""

    def __init__(self):
        self._tasks: dict[str, TrackedTask] = {}

    def create_task(self, task_type: str, platform: str) -> TrackedTask:
        task_id = str(uuid.uuid4())[:8]
        task = TrackedTask(
            task_id=task_id,
            task_type=task_type,
            platform=platform,
            started_at=datetime.now().isoformat(),
            _event=asyncio.Event(),
        )
        self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> TrackedTask | None:
        return self._tasks.get(task_id)

    def get_tasks_by_type(self, task_type: str) -> list[TrackedTask]:
        return [t for t in self._tasks.values() if t.task_type == task_type]

    def get_active_auth_task(self, platform: str) -> TrackedTask | None:
        """Get an active auth task for a platform (if any)."""
        for t in self._tasks.values():
            if t.task_type == "auth" and t.platform == platform and t.status in ("starting", "running", "waiting_for_login"):
                return t
        return None

    def get_active_collection_task(self, platform: str) -> TrackedTask | None:
        """Get an active collection task for a platform (if any)."""
        for t in self._tasks.values():
            if t.task_type == "collection" and t.platform == platform and t.status in ("starting", "running"):
                return t
        return None

    def get_collection_tasks_by_job(self, job_id: str) -> list[TrackedTask]:
        """All collection tasks (active or finished) for a given job_id."""
        return [t for t in self._tasks.values()
                if t.task_type == "collection" and t.job_id == job_id]


# Singleton
task_manager = TaskManager()
