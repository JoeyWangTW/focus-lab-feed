"""Workspace API — status, setup, reveal.

There is no default workspace. The user explicitly sets one up via
`POST /api/workspace/setup`, which creates the folder (if missing) and
bootstraps the curation structure into it.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.paths import get_workspace_dir, suggested_workspace_dir
from app.workspace import bootstrap_workspace, reveal_in_finder, save_workspace_dir

router = APIRouter()


@router.get("")
async def get_workspace():
    """Return workspace status. `is_setup` is false until the user picks a folder."""
    ws = get_workspace_dir()
    if ws is None:
        return {
            "is_setup": False,
            "path": None,
            "suggested_path": str(suggested_workspace_dir()),
        }

    exports = ws / "exports"
    pack_count = 0
    recent = []
    if exports.exists():
        items = sorted(
            [p for p in exports.iterdir() if p.is_dir() or p.suffix == ".zip"],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        pack_count = len(items)
        for item in items[:5]:
            size_b = sum(f.stat().st_size for f in item.rglob("*") if f.is_file()) if item.is_dir() else item.stat().st_size
            recent.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size_mb": round(size_b / 1024 / 1024, 1),
                "modified": item.stat().st_mtime,
            })

    return {
        "is_setup": True,
        "path": str(ws),
        "exports_dir": str(exports),
        "pack_count": pack_count,
        "recent_packs": recent,
        "goals_exists": (ws / "goals.md").exists(),
        "skill_exists": (ws / "skills" / "focus-lab-curator" / "SKILL.md").exists(),
    }


class SetupRequest(BaseModel):
    path: str


@router.post("/setup")
async def setup(request: SetupRequest):
    """Create (if missing) and bootstrap the user's chosen workspace folder."""
    raw = request.path.strip() if request.path else ""
    if not raw:
        raise HTTPException(400, "A folder path is required.")

    target = Path(raw).expanduser().resolve()

    # Sanity: refuse obvious nonsense like root, home dir, or a file path.
    if target == Path("/") or target == Path.home():
        raise HTTPException(400, "Pick a specific folder, not the home or root directory.")
    if target.exists() and not target.is_dir():
        raise HTTPException(400, f"{target} exists and is not a directory.")

    target.mkdir(parents=True, exist_ok=True)
    result = bootstrap_workspace(target)
    save_workspace_dir(target)
    return {"success": True, **result}


@router.get("/goals")
async def get_goals():
    ws = get_workspace_dir()
    if ws is None:
        raise HTTPException(412, "Workspace not set up yet.")
    goals = ws / "goals.md"
    if not goals.exists():
        return {"content": "", "path": str(goals), "exists": False}
    return {"content": goals.read_text(), "path": str(goals), "exists": True}


class SaveGoalsRequest(BaseModel):
    content: str


@router.post("/goals")
async def save_goals(request: SaveGoalsRequest):
    ws = get_workspace_dir()
    if ws is None:
        raise HTTPException(412, "Workspace not set up yet.")
    goals = ws / "goals.md"
    goals.write_text(request.content)
    return {"success": True, "path": str(goals), "size": len(request.content)}


@router.post("/reveal")
async def reveal(body: dict | None = None):
    """Open the workspace (or a specific sub-path) in the OS file manager."""
    ws = get_workspace_dir()
    if ws is None:
        raise HTTPException(412, "Workspace not set up yet.")

    sub_path = (body or {}).get("path")
    target = Path(sub_path).expanduser().resolve() if sub_path else ws
    # Keep reveals inside the workspace.
    try:
        target.resolve().relative_to(ws.resolve())
    except ValueError:
        if target.resolve() != ws.resolve():
            raise HTTPException(400, "Path is outside the workspace")
    if not reveal_in_finder(target):
        raise HTTPException(404, f"Path not found: {target}")
    return {"ok": True, "revealed": str(target)}
