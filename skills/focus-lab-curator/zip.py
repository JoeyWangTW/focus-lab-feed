#!/usr/bin/env python3
"""Zip only the curated, viewer-facing bits of a pack for AirDrop / sharing.

From inside a pack directory:

    python3 zip.py                    # → ../<pack-name>.zip
    python3 zip.py --out PATH         # custom output path
    python3 zip.py --include-raw      # also include the original posts.json
    python3 zip.py --include-goals    # also include your goals.md (private!)
    python3 zip.py --include-scripts  # also include curate.py / zip.py

Default contents (viewer-only):
    posts.filtered.json    (falls back to posts.json if no curation ran)
    media/                 (only what's there — run curate.py first to trim)
    viewer.html            (if present)
    focuslab-logo.svg      (if present)
    README.md              (if present)

Default exclusions (so a shared zip stays lean and private):
    posts.json             (raw — superseded by posts.filtered.json)
    goals.md               (your content preferences — keep off shared zips)
    curate.py, zip.py      (dev tooling; not needed to view)
    .DS_Store, *.pyc       (junk)
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


IGNORE_NAMES = {".DS_Store", "Thumbs.db"}
IGNORE_SUFFIXES = {".pyc"}
SCRIPT_NAMES = {"curate.py", "zip.py"}


def main() -> int:
    p = argparse.ArgumentParser(description="Zip viewer-facing pack contents for AirDrop.")
    p.add_argument("pack", nargs="?", default=".", help="pack directory (default: cwd)")
    p.add_argument("--out", default=None, help="output zip path (default: ../<pack-name>.zip)")
    p.add_argument("--include-raw", action="store_true",
                   help="also include the original (unfiltered) posts.json")
    p.add_argument("--include-goals", action="store_true",
                   help="also include goals.md (treat with care — your preferences)")
    p.add_argument("--include-scripts", action="store_true",
                   help="also include curate.py and zip.py")
    args = p.parse_args()

    pack = Path(args.pack).resolve()
    if not pack.is_dir():
        sys.exit(f"error: not a directory: {pack}")

    has_filtered = (pack / "posts.filtered.json").exists()
    has_raw = (pack / "posts.json").exists()
    if not has_filtered and not has_raw:
        sys.exit(f"error: no posts.json or posts.filtered.json in {pack}")

    out = Path(args.out).resolve() if args.out else pack.parent / f"{pack.name}.zip"

    includes: list[Path] = []

    # Posts file(s) — prefer filtered, optionally include raw as a sidecar.
    if has_filtered:
        includes.append(pack / "posts.filtered.json")
        if args.include_raw and has_raw:
            includes.append(pack / "posts.json")
    else:
        includes.append(pack / "posts.json")

    # Standard viewer accessories — include if present.
    for name in ("viewer.html", "focuslab-logo.svg", "README.md"):
        f = pack / name
        if f.exists():
            includes.append(f)

    if args.include_goals and (pack / "goals.md").exists():
        includes.append(pack / "goals.md")

    if args.include_scripts:
        for name in SCRIPT_NAMES:
            f = pack / name
            if f.exists():
                includes.append(f)

    # All media files (post-curation trim already removed orphans if curate.py ran).
    media_dir = pack / "media"
    if media_dir.exists():
        for f in sorted(media_dir.rglob("*")):
            if not f.is_file():
                continue
            if f.name in IGNORE_NAMES or f.suffix in IGNORE_SUFFIXES:
                continue
            includes.append(f)

    if not includes:
        sys.exit("error: nothing to include")

    # Write the zip — paths are pack-name-rooted so `Compress on phone →
    # Uncompress` gives you a sensibly-named folder.
    print(f"Zipping {len(includes)} file(s) → {out}...", file=sys.stderr)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in includes:
            rel = f.relative_to(pack)
            zf.write(f, f"{pack.name}/{rel}")

    size_mb = out.stat().st_size / 1024 / 1024
    print(f"Done — {out} ({size_mb:.1f} MB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
