#!/usr/bin/env python3
"""
Resync repositories with zero branch/commit counts
"""
import sqlite3
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.database import get_session
from web.db_models import Repository, SyncJob
import threading
import time

def get_zero_repos():
    """Get repos with zero branch or commit counts."""
    session = get_session()
    try:
        repos = session.query(Repository).filter(
            (Repository.branch_count == 0) | (Repository.total_commits == 0),
            Repository.is_cloned == True
        ).all()
        return [(r.full_name, r.clone_url) for r in repos]
    finally:
        session.close()

def sync_directly(repos_to_sync):
    """Directly trigger sync by creating jobs."""
    from app.config import load_config
    from web.api.repos import _do_sync

    config = load_config("config.toml")

    # Create sync jobs
    session = get_session()
    try:
        for full_name, clone_url in repos_to_sync:
            job = session.query(SyncJob).filter(SyncJob.repo_name == full_name).first()
            if not job:
                job = SyncJob(
                    repo_name=full_name,
                    status="queued",
                    started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ")
                )
                session.add(job)
        session.commit()
    finally:
        session.close()

    # Start sync thread
    repo_dicts = [{"full_name": name, "clone_url": url} for name, url in repos_to_sync]

    # Import here to avoid circular dependency
    from web.api import repos as repos_api
    repos_api.set_app_config(config)

    thread = threading.Thread(target=_do_sync, args=(repo_dicts,), daemon=False)
    thread.start()

    return len(repo_dicts)

def main():
    # Initialize database first
    from web.database import init_db
    from app.config import load_config

    config = load_config("config.toml")
    init_db(config.db_path)

    print("获取数据为 0 的仓库...")
    repos = get_zero_repos()

    if not repos:
        print("没有需要同步的仓库")
        return

    print(f"找到 {len(repos)} 个仓库:")
    for full_name, _ in repos:
        print(f"  - {full_name}")

    print()
    print("正在启动同步...")
    count = sync_directly(repos)
    print(f"✓ 已提交 {count} 个仓库同步")
    print("同步在后台运行中...")

if __name__ == "__main__":
    main()

