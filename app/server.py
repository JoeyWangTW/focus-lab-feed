"""FastAPI app factory with static file mounts and CORS."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import auth, collection, config, curated, data, export, setup, workspace
from app.paths import FEED_DATA_DIR, IS_BUNDLED, STATIC_DIR
from src.storage import migrate_legacy_runs


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Dev-only: tell WebKit not to cache anything, so Cmd+R in pywebview
    shows current JS/CSS/HTML without a full app restart. Disabled in
    bundled mode so the shipped .app benefits from normal HTTP caching."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


def create_app() -> FastAPI:
    app = FastAPI(title="Focus Lab Feed Collector")

    # Migrate old flat run directories to new date/job/platform hierarchy
    migrate_legacy_runs(str(FEED_DATA_DIR))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if not IS_BUNDLED:
        app.add_middleware(NoCacheMiddleware)

    # API routers
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(collection.router, prefix="/api/collection", tags=["collection"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(data.router, prefix="/api/data", tags=["data"])
    app.include_router(export.router, prefix="/api/export", tags=["export"])
    app.include_router(setup.router, prefix="/api/setup", tags=["setup"])
    app.include_router(workspace.router, prefix="/api/workspace", tags=["workspace"])
    app.include_router(curated.router, prefix="/api/curated", tags=["curated"])

    # Serve collected data (media files, JSON)
    FEED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/feed_data", StaticFiles(directory=str(FEED_DATA_DIR)), name="feed_data")

    # Serve frontend SPA (must be last — catches all remaining paths)
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app
