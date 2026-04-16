"""Workspace bootstrap — the user's curation folder.

One user-picked folder holds everything: the curator skill, default goals.md,
the `exports/` subfolder where packs land, and the Claude Code / agent
auto-discovery glue (`.claude/skills/` symlink, CLAUDE.md, AGENTS.md).

Bootstrapping is ONLY done on explicit user setup — not at app start. This
way a first-time user isn't surprised by a folder appearing in their home dir.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from app.paths import CONFIG_PATH, get_workspace_dir, skill_source_dir

SKILL_NAME = "focus-lab-curator"


CLAUDE_MD = """# Focus Lab Feed workspace

You are working in a Focus Lab Feed workspace. Exports land in `./exports/`,
the curator skill lives at `./skills/focus-lab-curator/`, and the user's
content preferences live in `./goals.md`.

## Curator skill

When the user asks to curate a feed, follow the instructions in
`skills/focus-lab-curator/SKILL.md` (also available via `.claude/skills/focus-lab-curator/SKILL.md`).

It handles: interactive content-preferences bootstrap (writes `goals.md`),
scoring posts 0–100 against those preferences, and producing
`posts.filtered.json` with a strict schema.

## Typical workflow

1. The user imports a pack — `cd ./exports/focus-lab-pack-YYYY-MM-DD_HHMMSS/`.
2. The user says "curate this feed" (or similar).
3. You use the curator skill to produce `posts.filtered.json` in that pack folder.
4. The user re-zips the pack and AirDrops it to their phone.

## Goals resolution

The curator skill prefers a pack-local `goals.md` (in the pack folder) over
the workspace-level `./goals.md`. If neither exists, the skill runs its
bootstrap flow to interview the user.
"""


AGENTS_MD = """# Focus Lab Feed workspace

Collected-and-exported packs live in `./exports/`. Each pack contains
`posts.json` and a `media/` folder.

To curate a pack for the Focus Lab Feed viewer, read
`skills/focus-lab-curator/SKILL.md` and follow its instructions. The skill
detects `goals.md` (pack-local preferred, falls back to workspace-level),
interviews the user if absent, then produces `posts.filtered.json`.

Default goals: `./goals.md` in this directory.
"""


README_MD = """# Focus Lab Feed — Workspace

Everything Focus Lab Feed needs lives here.

- `exports/` — packs land here when you Export from the app.
- `skills/focus-lab-curator/` — the curator skill for Claude Code / Cursor / Codex.
- `.claude/skills/focus-lab-curator/` — Claude Code auto-discovery (symlink).
- `goals.md` — your default content preferences.
- `CLAUDE.md` / `AGENTS.md` — instructions that point agents at the skill.

## Flow

1. **Collect** — open the Focus Lab Feed app, run a collection.
2. **Export** — click *Export for curation* in the app. A pack folder lands in `./exports/`.
3. **Curate** — cd into the pack, run an agent:

       cd exports/focus-lab-pack-YYYY-MM-DD_HHMMSS
       claude                         # then say: "curate this feed"

   The skill produces `posts.filtered.json` in the pack folder.
4. **View** — right-click the pack folder in Finder → Compress. AirDrop the
   zip to your phone, open the Focus Lab Feed viewer, import the zip.

## Goals

`goals.md` is your default content preferences — you can edit it by hand,
or leave it blank and let the curator skill interview you the first time
you run it in a pack.
"""


def _relative_path(target: Path, start: Path) -> Path:
    """Best-effort relative path for symlinks. Falls back to absolute."""
    try:
        return Path(target.resolve().relative_to(start.resolve(), walk_up=True))
    except (ValueError, TypeError):
        return target.resolve()


def bootstrap_workspace(workspace: Path) -> dict:
    """Populate `workspace` with the curation structure. Idempotent.

    Never overwrites existing files. Creates `exports/`, the curator skill, the
    `.claude/skills/focus-lab-curator` symlink, a starter `goals.md`, plus
    `CLAUDE.md` / `AGENTS.md` / `README.md` if they're absent.
    """
    ws = Path(workspace).expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    exports = ws / "exports"
    if not exports.exists():
        exports.mkdir()
        created.append("exports/")

    # Copy the curator skill if the workspace doesn't already have its own.
    src = skill_source_dir()
    dst = ws / "skills" / SKILL_NAME
    if not dst.exists() and src.exists() and src.resolve() != dst.resolve():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        created.append(f"skills/{SKILL_NAME}/")

    # .claude/skills symlink — makes the skill auto-discoverable whether the
    # user runs `claude` in the workspace root or a pack subdirectory.
    claude_skill_link = ws / ".claude" / "skills" / SKILL_NAME
    skill_for_link = dst if dst.exists() else src
    if skill_for_link.exists() and not claude_skill_link.exists() and not claude_skill_link.is_symlink():
        claude_skill_link.parent.mkdir(parents=True, exist_ok=True)
        try:
            rel = _relative_path(skill_for_link, claude_skill_link.parent)
            claude_skill_link.symlink_to(rel)
            created.append(".claude/skills/focus-lab-curator (symlink)")
        except OSError:
            shutil.copytree(skill_for_link, claude_skill_link)
            created.append(".claude/skills/focus-lab-curator (copy)")

    # Seed goals.md from the template.
    goals_dst = ws / "goals.md"
    if not goals_dst.exists():
        template = skill_for_link / "templates" / "goals.md"
        if template.exists():
            shutil.copy2(template, goals_dst)
            created.append("goals.md")

    # Docs — only if missing (never clobber).
    for rel, content in (("CLAUDE.md", CLAUDE_MD), ("AGENTS.md", AGENTS_MD), ("README.md", README_MD)):
        target = ws / rel
        if not target.exists():
            target.write_text(content)
            created.append(rel)

    return {"workspace": str(ws), "created": created}


def save_workspace_dir(workspace: Path) -> None:
    """Persist the chosen workspace path into config.json."""
    cfg: dict = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            cfg = {}
    cfg["workspace_dir"] = str(Path(workspace).expanduser().resolve())
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def reveal_in_finder(path: Path) -> bool:
    """Open a path in the OS file manager."""
    target = Path(path)
    if not target.exists():
        return False
    if sys.platform == "darwin":
        subprocess.run(["open", str(target)], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", str(target)], check=False)
    else:
        subprocess.run(["xdg-open", str(target)], check=False)
    return True
