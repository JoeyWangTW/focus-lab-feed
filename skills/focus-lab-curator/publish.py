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
free tier). Four guards keep the bucket small:

    MAX_VIDEO_MB    (default 50)  — bigger videos become tap-through links
    DAILY_BUDGET_MB (default 500) — media included in score order until spent
    RETENTION_DAYS  (default 14)  — older days deleted from the bucket
    BUCKET_LIMIT_GB (default 10)  — when the bucket nears this, drop the oldest
                                    days (never today's) until back under 80%

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
    # BUCKET_LIMIT_GB=10

Typical use, from the workspace root:

    python3 skills/focus-lab-curator/publish.py              # latest curated job
    python3 skills/focus-lab-curator/publish.py --dry-run    # build publish_preview/ only
    python3 skills/focus-lab-curator/publish.py --job 2026-07-12/job_132135

Requirements: Python 3.9+ only — no third-party packages. Uploads use a
built-in SigV4-signed S3 client (R2 is S3-compatible). `--dry-run` needs no
publish.env either.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

MB = 1024 * 1024
GB = 1024 * MB

DEFAULT_MAX_VIDEO_MB = 50
DEFAULT_DAILY_BUDGET_MB = 500
DEFAULT_RETENTION_DAYS = 14
# R2's free tier is 10 GB. When the bucket gets close to this, drop the oldest
# days (beyond the date-based retention) so a publish never fails or spills into
# paid storage. Trigger at 95% full, prune back down to 80%.
DEFAULT_BUCKET_LIMIT_GB = 10
BUCKET_HIGH_WATER = 0.95
BUCKET_LOW_WATER = 0.80

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


# ----- R2 client (stdlib-only S3 SigV4) -------------------------------------------
#
# The skill must run without installing anything, so no boto3. R2 speaks the
# S3 API, and the five calls we need (PUT/GET/HEAD/DELETE/LIST) fit in a small
# SigV4-signed urllib client.

def _uri_encode(s: str, safe: str = "") -> str:
    # SigV4 canonical encoding: RFC 3986, space as %20 (never '+').
    return urllib.parse.quote(s, safe="-_.~" + safe)


class R2Client:
    def __init__(self, cfg: dict):
        endpoint = cfg["R2_ENDPOINT"].rstrip("/")
        parsed = urllib.parse.urlparse(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            sys.exit(f"error: R2_ENDPOINT doesn't look like a URL: {endpoint!r}")
        self.scheme = parsed.scheme
        self.host = parsed.netloc
        self.bucket = cfg["R2_BUCKET"]
        self.access_key = cfg["R2_ACCESS_KEY_ID"]
        self.secret_key = cfg["R2_SECRET_ACCESS_KEY"]
        self.region = "auto"

    def _authorization(self, method: str, path: str, canonical_query: str,
                       headers: dict, payload_hash: str, amz_date: str) -> str:
        datestamp = amz_date[:8]
        lower = {k.lower(): str(v).strip() for k, v in headers.items()}
        signed_headers = ";".join(sorted(lower))
        canonical_headers = "".join(f"{k}:{lower[k]}\n" for k in sorted(lower))
        canonical_request = "\n".join(
            [method, path, canonical_query, canonical_headers, signed_headers, payload_hash]
        )
        scope = f"{datestamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256", amz_date, scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])
        key = f"AWS4{self.secret_key}".encode()
        for part in (datestamp, self.region, "s3", "aws4_request"):
            key = hmac.new(key, part.encode(), hashlib.sha256).digest()
        signature = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()
        return (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

    def _request(self, method: str, key: str = "", query: dict | None = None,
                 body: bytes = b"", extra_headers: dict | None = None,
                 retries: int = 3) -> tuple[int, bytes]:
        """Signed request. Returns (status, body); 404 comes back as a status,
        transport errors and 5xx are retried then raised."""
        path = "/" + _uri_encode(self.bucket, safe="/") + (
            "/" + _uri_encode(key, safe="/") if key else ""
        )
        canonical_query = "&".join(
            f"{_uri_encode(k)}={_uri_encode(v)}" for k, v in sorted((query or {}).items())
        )
        payload_hash = hashlib.sha256(body).hexdigest()
        url = f"{self.scheme}://{self.host}{path}"
        if canonical_query:
            url += "?" + canonical_query

        last_err: Exception | None = None
        for attempt in range(retries):
            amz_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            headers = {
                "host": self.host,
                "x-amz-date": amz_date,
                "x-amz-content-sha256": payload_hash,
                **(extra_headers or {}),
            }
            headers["Authorization"] = self._authorization(
                method, path, canonical_query,
                {k: v for k, v in headers.items() if k.lower() != "authorization"},
                payload_hash, amz_date,
            )
            req = urllib.request.Request(url, data=body if body else None,
                                         method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return resp.status, resp.read()
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    return e.code, e.read()
                last_err = e
            except urllib.error.URLError as e:
                last_err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
        raise RuntimeError(f"R2 {method} {path} failed after {retries} tries: {last_err}")

    def put(self, key: str, body: bytes, content_type: str, cache_control: str) -> None:
        status, out = self._request("PUT", key, body=body, extra_headers={
            "content-type": content_type, "cache-control": cache_control,
        })
        if status not in (200, 201):
            raise RuntimeError(f"PUT {key} → HTTP {status}: {out[:300]!r}")

    def get(self, key: str) -> bytes | None:
        status, out = self._request("GET", key)
        return out if status == 200 else None

    def head(self, key: str) -> bool:
        status, _ = self._request("HEAD", key)
        return status == 200

    def delete(self, key: str) -> None:
        self._request("DELETE", key)  # 204 on success, 404 is fine too

    def list_objects(self, prefix: str) -> list[tuple[str, int]]:
        """List (key, size_bytes) under a prefix, following pagination."""
        objs: list[tuple[str, int]] = []
        token: str | None = None
        while True:
            query = {"list-type": "2", "prefix": prefix}
            if token:
                query["continuation-token"] = token
            status, out = self._request("GET", "", query=query)
            if status != 200:
                raise RuntimeError(f"LIST {prefix} → HTTP {status}: {out[:300]!r}")
            root = ET.fromstring(out)
            ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
            for el in root.findall(f"{ns}Contents"):
                key = el.findtext(f"{ns}Key") or ""
                try:
                    size = int(el.findtext(f"{ns}Size") or 0)
                except ValueError:
                    size = 0
                objs.append((key, size))
            if (root.findtext(f"{ns}IsTruncated") or "").lower() != "true":
                return objs
            token = root.findtext(f"{ns}NextContinuationToken")
            if not token:
                return objs

    def list_keys(self, prefix: str) -> list[str]:
        return [k for k, _ in self.list_objects(prefix)]


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
    p.add_argument("--bucket-limit-gb", type=int, default=None,
                   help="drop oldest days when the bucket nears this size (default 10 = R2 free tier)")
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
    bucket_limit_gb = args.bucket_limit_gb or env_int(cfg, "BUCKET_LIMIT_GB", DEFAULT_BUCKET_LIMIT_GB)

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

    client = R2Client(cfg)

    # Media first — if the run dies midway, posts.json/index.json haven't
    # flipped yet and the previous publish stays intact.
    uploaded = skipped = 0
    for i, (src, name, size) in enumerate(uploads, 1):
        key = f"feed/{day}/media/{name}"
        if client.head(key):
            skipped += 1
        else:
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            client.put(key, src.read_bytes(), ctype,
                       "public, max-age=31536000, immutable")
            uploaded += 1
        if i % 10 == 0 or i == len(uploads):
            log(f"  media {i}/{len(uploads)} (new: {uploaded}, already there: {skipped})")

    client.put(f"feed/{day}/posts.json",
               json.dumps(payload, ensure_ascii=False).encode("utf-8"),
               "application/json", "no-cache")
    client.put("index.html", VIEWER_TEMPLATE.read_bytes(),
               "text/html; charset=utf-8", "no-cache")

    raw_index = client.get("feed/index.json")
    index = json.loads(raw_index) if raw_index else {"days": []}
    upsert_day(index, day_entry)

    def drop_day(dday: str) -> int:
        n = 0
        for k in client.list_keys(f"feed/{dday}/"):
            client.delete(k)
            n += 1
        return n

    # Retention 1 — age: drop days older than the cutoff.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    stale = [d for d in index["days"] if d["day"] < cutoff]
    for entry in stale:
        n = drop_day(entry["day"])
        log(f"  pruned {entry['day']} — age ({n} objects)")
    index["days"] = [d for d in index["days"] if d["day"] >= cutoff]

    # Retention 2 — size: if the bucket is near the limit, drop oldest days
    # (never today's) until we're back under the low-water mark. This is the
    # backstop that keeps us inside R2's free tier no matter how heavy a day is.
    limit = bucket_limit_gb * GB
    total = 0
    per_day: dict[str, int] = {}
    for key, size in client.list_objects("feed/"):
        total += size
        m = re.match(r"feed/(\d{4}-\d{2}-\d{2})/", key)
        if m:
            per_day[m.group(1)] = per_day.get(m.group(1), 0) + size
    log(f"bucket usage: {total / GB:.2f} / {bucket_limit_gb} GB")

    space_pruned: list[str] = []
    if total > limit * BUCKET_HIGH_WATER:
        # Oldest first, but never delete the day we just published.
        candidates = sorted(d["day"] for d in index["days"] if d["day"] != day)
        for dday in candidates:
            if total <= limit * BUCKET_LOW_WATER:
                break
            freed = per_day.get(dday, 0)
            n = drop_day(dday)
            total -= freed
            space_pruned.append(dday)
            log(f"  pruned {dday} — space ({n} objects, ~{freed // MB} MB freed)")
        index["days"] = [d for d in index["days"] if d["day"] not in space_pruned]
        if total > limit * BUCKET_LOW_WATER:
            log(f"warning: bucket still {total / GB:.2f} GB after pruning — "
                "only today's feed remains; consider a smaller DAILY_BUDGET_MB.")

    index["updated_at"] = payload["publish_metadata"]["published_at"]
    client.put("feed/index.json",
               json.dumps(index, ensure_ascii=False).encode("utf-8"),
               "application/json", "no-cache")

    pruned_total = len(stale) + len(space_pruned)
    url = cfg["PUBLIC_BASE_URL"].rstrip("/") + "/index.html"
    log(f"done — {uploaded} media uploaded, {skipped} already present, {pruned_total} days pruned")
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
