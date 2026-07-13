#!/usr/bin/env python3
"""Focus Lab Publisher — push one curated job to a Cloudflare R2 bucket so the
feed is scrollable from a phone.

Takes the latest job that has a `posts.filtered.json` (i.e. already curated),
builds a static bundle (hosted viewer + posts JSON + media files), and uploads
it to R2 via the S3 API. Everything is served from the same origin, so media
just works — no CORS, no expiring platform CDN links.

Bucket layout:

    index.html                      ← the phone viewer (uploaded every publish)
    feed/index.json                 ← list of published days, newest first
    feed/<YYYY-MM-DD>/posts.json    ← curated posts + hosted_media entries
    feed/<YYYY-MM-DD>/media/<file>  ← images and small videos

Large videos are NOT uploaded (podcasts/interviews would blow through R2's
free tier). Three guards keep the bucket small:

    MAX_VIDEO_MB    (default 50)  — bigger videos become tap-through links
    DAILY_BUDGET_MB (default 500) — media included in score order until spent
    RETENTION_DAYS  (default 14)  — older days deleted from the bucket

YouTube videos are never uploaded regardless of size — the right UX for
long-form video is tapping through to YouTube anyway.

Credentials + config live in `<workspace>/publish.env` (KEY=VALUE lines):

    R2_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
    R2_BUCKET=focus-lab-feed
    R2_ACCESS_KEY_ID=...
    R2_SECRET_ACCESS_KEY=...
    PUBLIC_BASE_URL=https://pub-xxxxxxxx.r2.dev
    # optional overrides:
    # MAX_VIDEO_MB=50
    # DAILY_BUDGET_MB=500
    # RETENTION_DAYS=14

Typical use, from the workspace root:

    python3 skills/focus-lab-curator/publish.py              # latest curated job
    python3 skills/focus-lab-curator/publish.py --dry-run    # build publish_preview/ only
    python3 skills/focus-lab-curator/publish.py --job 2026-07-12/job_132135

Requirements: Python 3.9+; boto3 for real uploads (`pip install boto3`).
`--dry-run` needs no boto3 and no publish.env.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MB = 1024 * 1024

DEFAULT_MAX_VIDEO_MB = 50
DEFAULT_DAILY_BUDGET_MB = 500
DEFAULT_RETENTION_DAYS = 14

JOB_DIR_RE = re.compile(r"^job_\d{6}$")
DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VIDEO_EXT_RE = re.compile(r"\.(mp4|mov|m4v|webm)$", re.IGNORECASE)

REQUIRED_ENV = (
    "R2_ENDPOINT",
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "PUBLIC_BASE_URL",
)

VIEWER_TEMPLATE = Path(__file__).resolve().parent / "hosted.html"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ----- Workspace / job discovery (mirrors curate.py) -------------------------

def resolve_workspace(arg: str | None) -> Path:
    if arg:
        ws = Path(arg).expanduser().resolve()
        if not ws.is_dir():
            sys.exit(f"error: --workspace {ws} is not a directory")
        return ws
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "data").is_dir() or (candidate / "goals.md").is_file():
            return candidate
        if candidate.name == "data" and candidate.parent.is_dir():
            return candidate.parent
    sys.exit(
        f"error: couldn't find a Focus Lab workspace from {cwd}.\n"
        "Run from inside one (a folder that contains `data/` or `goals.md`),\n"
        "or pass --workspace /path/to/workspace."
    )


def latest_curated_job(data_dir: Path) -> Path:
    """Most recent job dir that already has a posts.filtered.json."""
    if not data_dir.is_dir():
        sys.exit(f"error: {data_dir} not found — collect and curate something first.")
    dates = sorted(
        [d for d in data_dir.iterdir() if d.is_dir() and DATE_DIR_RE.match(d.name)],
        reverse=True,
    )
    for date_dir in dates:
        jobs = sorted(
            [j for j in date_dir.iterdir() if j.is_dir() and JOB_DIR_RE.match(j.name)],
            reverse=True,
        )
        for job_dir in jobs:
            if (job_dir / "posts.filtered.json").exists():
                return job_dir
    sys.exit(
        f"error: no curated job (posts.filtered.json) found under {data_dir}.\n"
        "Run curate.py first."
    )


def job_from_arg(data_dir: Path, arg: str) -> Path:
    arg = arg.strip().strip("/")
    if "/" in arg:
        date, job = arg.split("/", 1)
    else:
        date, job = datetime.now().strftime("%Y-%m-%d"), arg
    if not job.startswith("job_"):
        job = "job_" + job
    job_dir = data_dir / date / job
    if not job_dir.is_dir():
        sys.exit(f"error: job {date}/{job} not found under {data_dir}")
    if not (job_dir / "posts.filtered.json").exists():
        sys.exit(f"error: {date}/{job} has no posts.filtered.json — curate it first.")
    return job_dir


# ----- publish.env ------------------------------------------------------------

def load_env_file(path: Path) -> dict:
    cfg: dict = {}
    if not path.is_file():
        return cfg
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        cfg[key.strip()] = value.strip().strip('"').strip("'")
    return cfg


def env_int(cfg: dict, key: str, default: int) -> int:
    try:
        return int(cfg.get(key, default))
    except ValueError:
        sys.exit(f"error: {key} in publish.env must be an integer, got {cfg.get(key)!r}")


# ----- Media planning -----------------------------------------------------------

def plan_media(posts: list[dict], data_dir: Path, max_video_mb: int, budget_mb: int) -> tuple[list, dict]:
    """Decide, in score order, which media files get uploaded vs linked out.

    Mutates each post: adds `hosted_media`, a list the hosted viewer renders
    exclusively. Original fields are left untouched.

    Returns (uploads, stats) where uploads is [(abs_path, bucket_name, size)].
    """
    budget = budget_mb * MB
    max_video = max_video_mb * MB
    spent = 0
    uploads: list[tuple[Path, str, int]] = []
    name_owner: dict[str, Path] = {}   # bucket file name -> source path (collision guard)
    key_of: dict[Path, str] = {}       # source path -> bucket file name (dedupe)
    stats = {"images": 0, "videos": 0, "bytes": 0,
             "linkout_large": 0, "linkout_youtube": 0,
             "skipped_budget": 0, "missing": 0}

    def alloc_name(abs_path: Path) -> str:
        if abs_path in key_of:
            return key_of[abs_path]
        name = abs_path.name
        if name in name_owner and name_owner[name] != abs_path:
            # Same basename from a different file — disambiguate with a short
            # hash of the source path so both survive in the bucket.
            import hashlib
            digest = hashlib.sha1(str(abs_path).encode()).hexdigest()[:8]
            name = f"{digest}_{name}"
        name_owner[name] = abs_path
        key_of[abs_path] = name
        return name

    for post in posts:
        platform = (post.get("platform") or "").lower()
        rel_paths = post.get("local_media_paths") or []
        fallbacks = [*(post.get("media_urls") or []), *(post.get("video_urls") or [])]
        hosted: list[dict] = []
        post_images: list[str] = []   # uploaded image srcs, reused as linkout posters

        for i, rel in enumerate(rel_paths):
            remote = fallbacks[i] if i < len(fallbacks) else None
            is_video = bool(VIDEO_EXT_RE.search(rel))
            abs_path = (data_dir / rel).resolve()
            # Paths come from collected JSON — never follow one outside data/.
            if not str(abs_path).startswith(str(data_dir.resolve())) or not abs_path.is_file():
                stats["missing"] += 1
                if remote and not is_video:
                    hosted.append({"type": "image", "src": remote, "remote": True})
                elif post.get("url"):
                    hosted.append(linkout(post, None, "missing"))
                continue

            size = abs_path.stat().st_size
            already = abs_path in key_of

            if is_video and platform == "youtube":
                stats["linkout_youtube"] += 1
                hosted.append(linkout(post, size, "youtube"))
            elif is_video and size > max_video:
                stats["linkout_large"] += 1
                hosted.append(linkout(post, size, "too_large"))
            elif not already and spent + size > budget:
                stats["skipped_budget"] += 1
                if is_video:
                    hosted.append(linkout(post, size, "budget"))
                elif remote:
                    hosted.append({"type": "image", "src": remote, "remote": True})
            else:
                name = alloc_name(abs_path)
                if not already:
                    spent += size
                    uploads.append((abs_path, name, size))
                    stats["bytes"] += size
                    stats["videos" if is_video else "images"] += 1
                src = f"media/{name}"
                hosted.append({"type": "video" if is_video else "image", "src": src})
                if not is_video:
                    post_images.append(src)

        # Give video link-outs a poster if this post uploaded any image.
        for item in hosted:
            if item.get("type") == "linkout" and post_images:
                item["poster"] = post_images[0]

        post["hosted_media"] = hosted

    return uploads, stats


def linkout(post: dict, size: int | None, reason: str) -> dict:
    platform = (post.get("platform") or "source").lower()
    label = f"Watch on {platform}"
    if size:
        label += f" ({size // MB} MB)" if size >= MB else ""
    url = post.get("url") or (post.get("video_urls") or [None])[0] or ""
    return {"type": "linkout", "kind": "video", "url": url, "label": label, "reason": reason}


# ----- R2 client ----------------------------------------------------------------

def make_client(cfg: dict):
    try:
        import boto3
    except ImportError:
        sys.exit(
            "error: boto3 is not installed (needed for uploads).\n"
            "Install it with: pip install boto3\n"
            "Or run with --dry-run to build a local preview without uploading."
        )
    return boto3.client(
        "s3",
        endpoint_url=cfg["R2_ENDPOINT"],
        aws_access_key_id=cfg["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=cfg["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def get_json(client, bucket: str, key: str) -> dict | None:
    try:
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        return json.loads(body)
    except Exception:
        return None


def put_json(client, bucket: str, key: str, payload: dict) -> None:
    client.put_object(
        Bucket=bucket, Key=key,
        Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
        CacheControl="no-cache",
    )


def delete_prefix(client, bucket: str, prefix: str) -> int:
    deleted = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if keys:
            client.delete_objects(Bucket=bucket, Delete={"Objects": keys})
            deleted += len(keys)
    return deleted


# ----- Main ----------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Publish one curated Focus Lab job to R2.")
    p.add_argument("--workspace", default=None,
                   help="workspace root (default: auto-detect from CWD by walking up)")
    p.add_argument("--job", default=None,
                   help="job to publish as 'YYYY-MM-DD/job_HHMMSS' (default: latest curated)")
    p.add_argument("--env", default=None,
                   help="path to publish.env (default: <workspace>/publish.env)")
    p.add_argument("--dry-run", action="store_true",
                   help="build <workspace>/publish_preview/ locally, upload nothing")
    p.add_argument("--max-video-mb", type=int, default=None)
    p.add_argument("--budget-mb", type=int, default=None)
    p.add_argument("--retention-days", type=int, default=None)
    args = p.parse_args()

    workspace = resolve_workspace(args.workspace)
    data_dir = workspace / "data"
    job_dir = job_from_arg(data_dir, args.job) if args.job else latest_curated_job(data_dir)
    day = job_dir.parent.name
    job_label = f"{day}/{job_dir.name}"

    env_path = Path(args.env).expanduser() if args.env else workspace / "publish.env"
    cfg = load_env_file(env_path)
    if not args.dry_run:
        missing = [k for k in REQUIRED_ENV if not cfg.get(k)]
        if missing:
            sys.exit(
                f"error: {env_path} is missing: {', '.join(missing)}\n"
                "Create it with your R2 credentials (see publish.py docstring),\n"
                "or run with --dry-run to preview locally without credentials."
            )

    max_video_mb = args.max_video_mb or env_int(cfg, "MAX_VIDEO_MB", DEFAULT_MAX_VIDEO_MB)
    budget_mb = args.budget_mb or env_int(cfg, "DAILY_BUDGET_MB", DEFAULT_DAILY_BUDGET_MB)
    retention_days = args.retention_days or env_int(cfg, "RETENTION_DAYS", DEFAULT_RETENTION_DAYS)

    if not VIEWER_TEMPLATE.is_file():
        sys.exit(f"error: viewer template missing at {VIEWER_TEMPLATE}")

    filtered = json.loads((job_dir / "posts.filtered.json").read_text())
    posts = filtered.get("posts") or []
    log(f"publishing {job_label}: {len(posts)} curated posts")

    uploads, stats = plan_media(posts, data_dir, max_video_mb, budget_mb)
    log(
        f"media plan: {stats['images']} images + {stats['videos']} videos "
        f"({stats['bytes'] // MB} MB) · link-outs: {stats['linkout_large']} too-large, "
        f"{stats['linkout_youtube']} youtube · {stats['skipped_budget']} over budget · "
        f"{stats['missing']} missing"
    )

    payload = {
        "publish_metadata": {
            "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "job": job_label,
            "day": day,
            "max_video_mb": max_video_mb,
            "budget_mb": budget_mb,
            "media_files": len(uploads),
            "media_mb": round(stats["bytes"] / MB, 1),
        },
        "filter_metadata": filtered.get("filter_metadata") or {},
        "posts": posts,
    }
    day_entry = {
        "day": day,
        "job": job_label,
        "posts": len(posts),
        "media_files": len(uploads),
        "media_mb": round(stats["bytes"] / MB, 1),
        "published_at": payload["publish_metadata"]["published_at"],
    }

    if args.dry_run:
        preview = workspace / "publish_preview"
        feed_dir = preview / "feed" / day
        media_dir = feed_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(VIEWER_TEMPLATE, preview / "index.html")
        (feed_dir / "posts.json").write_text(json.dumps(payload, ensure_ascii=False))
        for i, (src, name, _size) in enumerate(uploads, 1):
            dest = media_dir / name
            if not dest.exists():
                try:
                    dest.symlink_to(src)  # avoid copying hundreds of MB
                except OSError:
                    shutil.copyfile(src, dest)
            if i % 25 == 0 or i == len(uploads):
                log(f"  staged media {i}/{len(uploads)}")
        index = get_local_index(preview)
        upsert_day(index, day_entry)
        (preview / "feed" / "index.json").write_text(json.dumps(index, ensure_ascii=False))
        log(f"dry run complete → {preview}")
        print(
            f"Preview built at {preview}\n"
            f"Test it:  python3 -m http.server 8899 -d '{preview}'\n"
            f"then open http://localhost:8899/index.html"
        )
        return 0

    client = make_client(cfg)
    bucket = cfg["R2_BUCKET"]

    # Media first — if the run dies midway, posts.json/index.json haven't
    # flipped yet and the previous publish stays intact.
    uploaded = skipped = 0
    for i, (src, name, size) in enumerate(uploads, 1):
        key = f"feed/{day}/media/{name}"
        if object_exists(client, bucket, key):
            skipped += 1
        else:
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            client.upload_file(
                str(src), bucket, key,
                ExtraArgs={"ContentType": ctype,
                           "CacheControl": "public, max-age=31536000, immutable"},
            )
            uploaded += 1
        if i % 10 == 0 or i == len(uploads):
            log(f"  media {i}/{len(uploads)} (new: {uploaded}, already there: {skipped})")

    put_json(client, bucket, f"feed/{day}/posts.json", payload)
    client.upload_file(
        str(VIEWER_TEMPLATE), bucket, "index.html",
        ExtraArgs={"ContentType": "text/html; charset=utf-8", "CacheControl": "no-cache"},
    )

    index = get_json(client, bucket, "feed/index.json") or {"days": []}
    upsert_day(index, day_entry)

    # Retention: drop days older than the cutoff from bucket + index.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    stale = [d for d in index["days"] if d["day"] < cutoff]
    for entry in stale:
        n = delete_prefix(client, bucket, f"feed/{entry['day']}/")
        log(f"  pruned {entry['day']} ({n} objects)")
    index["days"] = [d for d in index["days"] if d["day"] >= cutoff]
    index["updated_at"] = payload["publish_metadata"]["published_at"]
    put_json(client, bucket, "feed/index.json", index)

    url = cfg["PUBLIC_BASE_URL"].rstrip("/") + "/index.html"
    log(f"done — {uploaded} media uploaded, {skipped} already present, {len(stale)} days pruned")
    print(
        f"Published {job_label} — {len(posts)} posts, "
        f"{len(uploads)} media files ({payload['publish_metadata']['media_mb']} MB)\n"
        f"Feed: {url}"
    )
    return 0


def get_local_index(preview: Path) -> dict:
    path = preview / "feed" / "index.json"
    if path.is_file():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return {"days": []}


def upsert_day(index: dict, entry: dict) -> None:
    index["days"] = [d for d in index.get("days", []) if d.get("day") != entry["day"]]
    index["days"].append(entry)
    index["days"].sort(key=lambda d: d["day"], reverse=True)


if __name__ == "__main__":
    sys.exit(main())
