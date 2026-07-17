"""Unified entry point: FastAPI + APScheduler.

Usage:
    python run.py                        # default: config.toml
    python run.py --config path.toml     # custom config
    python run.py --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import argparse
import logging

import uvicorn

from app.config import load_config
from scheduler.engine import init_scheduler, shutdown_scheduler
from web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="hlb-git-pm Web + Scheduler")
    parser.add_argument("--config", default="config.toml", help="TOML 配置文件路径")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    # Configure logging to show all module logs
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Ensure repos API logs are visible
    logging.getLogger("hlb-git-pm.api.repos").setLevel(logging.INFO)
    logging.getLogger("hlb-git-pm").setLevel(logging.INFO if not args.verbose else logging.DEBUG)

    config = load_config(args.config)
    app = create_app(config=config)

    # Start APScheduler
    init_scheduler(config)

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        shutdown_scheduler()


if __name__ == "__main__":
    main()
