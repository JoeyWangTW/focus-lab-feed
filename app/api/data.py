"""Data API endpoints — list runs, serve posts (date/job/platform hierarchy)."""

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.paths import FEED_DATA_DIR

router = APIRouter()

# Patterns for detecting directory types
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
JOB_PATTERN = re.compile(r"^job_\d{6}$")
LEGACY_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{6})_(\w+)$")


def _parse_platform_dir(platform_dir: Path, date: str, job_id: str) -> dict | None:
    """Parse a platform directory within a job."""
    posts_file = platform_dir / "posts.json"
    if not posts_file.exists():
        posts_file = platform_dir / "tweets.json"

    platform = platform_dir.name
    run_id = f"{date}/job_{job_id}/{platform}"

    info = {
        "run_id": run_id,
        "platform": platform,
        "date": date,
        "job_id": job_id,
        "has_posts": posts_file.exists(),
    }

    if posts_file.exists():
        try:
            data = json.loads(posts_file.read_text())
            meta = data.get("metadata", {})
            info["post_count"] = meta.get("post_count", len(data.get("posts", data.get("tweets", []))))
            info["duration_seconds"] = meta.get("collection_duration_seconds")
            info["timestamp"] = meta.get("run_timestamp", "")
        except (json.JSONDecodeError, OSError):
            pass

    run_log = platform_dir / "run_log.json"
    if run_log.exists():
        try:
            info["run_log"] = json.loads(run_log.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    return info


def _walk_hierarchy() -> list[dict]:
    """Walk the date/job/platform hierarchy and return all runs."""
    if not FEED_DATA_DIR.exists():
        return []

    runs = []

    for date_dir in sorted(FEED_DATA_DIR.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue

        # New hierarchy: date/job_HHMMSS/platform/
        if DATE_PATTERN.match(date_dir.name):
            date = date_dir.name
            for job_dir in sorted(date_dir.iterdir(), reverse=True):
                if not job_dir.is_dir() or not JOB_PATTERN.match(job_dir.name):
                    continue
                job_id = job_dir.name.replace("job_", "")
                for platform_dir in sorted(job_dir.iterdir()):
                    if not platform_dir.is_dir() or platform_dir.name == "job.json":
                        continue
                    info = _parse_platform_dir(platform_dir, date, job_id)
                    if info:
                        runs.append(info)

        # Legacy flat: YYYY-MM-DD_HHMMSS_platform/
        elif LEGACY_PATTERN.match(date_dir.name):
            m = LEGACY_PATTERN.match(date_dir.name)
            date, time_id, platform = m.group(1), m.group(2), m.group(3)
            posts_file = date_dir / "posts.json"
            if not posts_file.exists():
                posts_file = date_dir / "tweets.json"
            info = {
                "run_id": date_dir.name,
                "platform": platform,
                "date": date,
                "job_id": time_id,
                "has_posts": posts_file.exists(),
                "legacy": True,
            }
            if posts_file.exists():
                try:
                    data = json.loads(posts_file.read_text())
                    meta = data.get("metadata", {})
                    info["post_count"] = meta.get("post_count", len(data.get("posts", data.get("tweets", []))))
                    info["duration_seconds"] = meta.get("collection_duration_seconds")
                    info["timestamp"] = meta.get("run_timestamp", "")
                except (json.JSONDecodeError, OSError):
                    pass
            runs.append(info)

    return runs


def _group_runs_by_date_and_job(runs: list[dict]) -> list[dict]:
    """Group flat run list into date > job > platforms hierarchy."""
    dates_map: dict[str, dict[str, list]] = {}

    for run in runs:
        date = run.get("date", "unknown")
        job_id = run.get("job_id", "unknown")
        if date not in dates_map:
            dates_map[date] = {}
        if job_id not in dates_map[date]:
            dates_map[date][job_id] = []
        dates_map[date][job_id].append(run)

    result = []
    for date in sorted(dates_map.keys(), reverse=True):
        jobs = []
        for job_id in sorted(dates_map[date].keys(), reverse=True):
            platforms = dates_map[date][job_id]
            # Try to load job.json for metadata
            job_dir = FEED_DATA_DIR / date / f"job_{job_id}"
            job_meta = {}
            job_json = job_dir / "job.json"
            if job_json.exists():
                try:
                    job_meta = json.loads(job_json.read_text())
                except (json.JSONDecodeError, OSError):
                    pass

            jobs.append({
                "job_id": job_id,
                "started_at": job_meta.get("started_at", ""),
                "platforms": platforms,
            })
        result.append({"date": date, "jobs": jobs})

    return result


def _resolve_run_dir(run_id: str) -> Path:
    """Resolve a run_id to its directory path, handling both new and legacy formats."""
    # New format: 2026-03-22/job_002223/twitter
    run_dir = FEED_DATA_DIR / run_id
    if run_dir.is_dir():
        return run_dir

    # Legacy format: 2026-03-22_002223_twitter
    run_dir = FEED_DATA_DIR / run_id
    if run_dir.is_dir():
        return run_dir

    raise HTTPException(404, f"Run not found: {run_id}")


@router.get("/runs")
async def list_runs():
    runs = _walk_hierarchy()
    grouped = _group_runs_by_date_and_job(runs)
    # Also return flat list for backward compat
    return {"dates": grouped, "runs": runs}


@router.get("/runs/latest")
async def get_latest_runs():
    runs = _walk_hierarchy()
    if not runs:
        return {"runs": {}}

    latest: dict[str, dict] = {}
    for run in runs:
        if run.get("has_posts"):
            platform = run.get("platform", "unknown")
            if platform not in latest:
                latest[platform] = run

    result = {}
    for platform, info in latest.items():
        run_dir = _resolve_run_dir(info["run_id"])
        posts_file = run_dir / "posts.json"
        if not posts_file.exists():
            posts_file = run_dir / "tweets.json"
        if posts_file.exists():
            try:
                data = json.loads(posts_file.read_text())
                result[platform] = {
                    "metadata": data.get("metadata", {}),
                    "posts": data.get("posts", data.get("tweets", [])),
                    "run_id": info["run_id"],
                }
            except (json.JSONDecodeError, OSError):
                pass

    return {"runs": result}


@router.get("/runs/{run_id:path}")
async def get_run(run_id: str):
    run_dir = _resolve_run_dir(run_id)

    posts_file = run_dir / "posts.json"
    if not posts_file.exists():
        posts_file = run_dir / "tweets.json"
    if not posts_file.exists():
        raise HTTPException(404, f"No posts file in run: {run_id}")

    return json.loads(posts_file.read_text())
