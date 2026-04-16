"""Export API endpoints — JSON, CSV, Focus Lab format. Bundled as ZIP with media."""

import csv
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.paths import FEED_DATA_DIR

router = APIRouter()


class ExportRequest(BaseModel):
    run_ids: list[str]
    format: str = "json"


def _load_posts_from_run(run_id: str) -> list[dict]:
    # run_id can be path-like: 2026-03-22/job_002223/twitter
    run_dir = FEED_DATA_DIR / run_id
    if not run_dir.is_dir():
        return []

    for filename in ["posts.json", "tweets.json"]:
        posts_file = run_dir / filename
        if posts_file.exists():
            try:
                data = json.loads(posts_file.read_text())
                return data.get("posts", data.get("tweets", []))
            except (json.JSONDecodeError, OSError):
                continue
    return []


def _collect_media_files(posts: list[dict]) -> list[tuple[Path, str]]:
    """Collect all local media files referenced by posts.

    Returns list of (absolute_path, archive_path) tuples.
    """
    files = []
    seen = set()
    for post in posts:
        for rel_path in post.get("local_media_paths") or []:
            if rel_path in seen:
                continue
            seen.add(rel_path)
            abs_path = FEED_DATA_DIR / rel_path
            if abs_path.exists():
                # In the ZIP, put all media in a flat media/ folder
                archive_name = f"media/{abs_path.name}"
                files.append((abs_path, archive_name))
    return files


def _rewrite_media_paths(posts: list[dict]) -> list[dict]:
    """Rewrite local_media_paths to point to the ZIP's media/ folder."""
    rewritten = []
    for post in posts:
        p = {**post}
        if p.get("local_media_paths"):
            p["local_media_paths"] = [
                f"media/{Path(path).name}" for path in p["local_media_paths"]
            ]
        rewritten.append(p)
    return rewritten


def _export_json(posts: list[dict], run_ids: list[str]) -> str:
    data = {
        "export_metadata": {
            "exported_at": datetime.now().isoformat(),
            "source": "focus-lab-feed-collector",
            "run_ids": run_ids,
            "total_posts": len(posts),
        },
        "posts": posts,
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def _export_csv(posts: list[dict]) -> str:
    output = io.StringIO()
    fields = [
        "id", "platform", "author_handle", "author_name", "text",
        "created_at", "url", "likes", "reposts", "replies", "quotes",
        "is_repost", "is_ad", "media_urls", "video_urls", "local_media_paths",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()

    for post in posts:
        row = {**post}
        row["media_urls"] = "|".join(row.get("media_urls") or [])
        row["video_urls"] = "|".join(row.get("video_urls") or [])
        row["local_media_paths"] = "|".join(row.get("local_media_paths") or [])
        writer.writerow(row)

    return output.getvalue()


def _export_focus_lab(posts: list[dict]) -> str:
    transformed = []
    for p in posts:
        media = []
        for i, path in enumerate(p.get("local_media_paths") or []):
            mtype = "video" if path.endswith(".mp4") else "image"
            media.append({"type": mtype, "local_path": path})
        # Fallback to URLs if no local paths
        if not media:
            for url in (p.get("media_urls") or []):
                media.append({"type": "image", "url": url})
            for url in (p.get("video_urls") or []):
                media.append({"type": "video", "url": url})

        transformed.append({
            "id": p.get("id"),
            "platform": p.get("platform"),
            "content": p.get("text", ""),
            "author": {
                "handle": p.get("author_handle"),
                "name": p.get("author_name"),
            },
            "engagement": {
                "likes": p.get("likes", 0),
                "reposts": p.get("reposts", 0),
                "replies": p.get("replies", 0),
            },
            "media": media,
            "timestamp": p.get("created_at"),
            "url": p.get("url"),
        })

    data = {
        "version": 1,
        "source": "feed-collector",
        "exported_at": datetime.now().isoformat(),
        "posts": transformed,
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


@router.post("")
async def export_data(request: ExportRequest):
    all_posts = []
    for run_id in request.run_ids:
        posts = _load_posts_from_run(run_id)
        all_posts.extend(posts)

    if not all_posts:
        raise HTTPException(404, "No posts found in selected runs")

    # Collect media files before rewriting paths
    media_files = _collect_media_files(all_posts)

    # Rewrite paths in posts to point to ZIP-internal media/ folder
    export_posts = _rewrite_media_paths(all_posts)

    # Generate the data content
    if request.format == "csv":
        content = _export_csv(export_posts)
        data_filename = "posts.csv"
    elif request.format == "focus_lab":
        content = _export_focus_lab(export_posts)
        data_filename = "posts.json"
    else:
        content = _export_json(export_posts, request.run_ids)
        data_filename = "posts.json"

    # Write ZIP to ~/Downloads
    downloads_dir = Path.home() / "Downloads"
    downloads_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"feed-export-{timestamp}.zip"
    dest = downloads_dir / filename

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add data file
        zf.writestr(data_filename, content)

        # Add all media files
        for abs_path, archive_name in media_files:
            zf.write(abs_path, archive_name)

    file_size = dest.stat().st_size
    size_label = f"{file_size / 1024 / 1024:.1f} MB" if file_size > 1024 * 1024 else f"{file_size / 1024:.0f} KB"

    return {
        "success": True,
        "path": str(dest),
        "filename": filename,
        "post_count": len(all_posts),
        "media_count": len(media_files),
        "size": size_label,
    }


@router.get("/formats")
async def list_formats():
    return {
        "formats": [
            {"id": "json", "name": "JSON", "description": "Raw post data with export metadata"},
            {"id": "csv", "name": "CSV", "description": "Flat table format for spreadsheets"},
            {"id": "focus_lab", "name": "Focus Lab", "description": "Normalized format for Focus Lab AI curation"},
        ]
    }
