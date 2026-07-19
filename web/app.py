from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import auth, dashboard, members, recipients, reports, repos, schedules, settings
from .database import init_db

logger = logging.getLogger("hlb-git-pm.web")


def create_app(config=None, config_path: str = "config.toml") -> FastAPI:
    app = FastAPI(title="hlb-git-pm", version="2.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Load config if not provided
    if config is None:
        from app.config import load_config
        config = load_config(config_path)

    # Initialize database
    init_db(config.db_path)

    # Set config references for API modules that need it
    reports.set_app_config(config)
    settings.set_app_config(config)
    repos.set_app_config(config)

    # Store config on app state
    app.state.config = config

    # Mount API routers — these must be mounted first so they have priority
    app.include_router(auth.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(members.router, prefix="/api")
    app.include_router(recipients.router, prefix="/api")
    app.include_router(schedules.router, prefix="/api")
    app.include_router(reports.router, prefix="/api")
    app.include_router(repos.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")

    # Serve frontend static files if dist/ exists
    dist_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if dist_dir.is_dir():
        # Mount static assets (js/css/images) under /assets
        assets_dir = dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        # SPA fallback for all remaining non-API routes
        # Serve index.html to let Vue Router handle client-side routing
        index_file = dist_dir / "index.html"

        # Create a custom route handler that only triggers for specific non-API paths
        @app.get("/{full_path:path}", name="spa", include_in_schema=False)
        async def spa_index(full_path: str):
            # Allow everything that's not an API route (API routes have already been matched above)
            return FileResponse(str(index_file))

        logger.info("前端静态文件挂载: %s", dist_dir)

    return app
