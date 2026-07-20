from __future__ import annotations

import logging
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone as _tz
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db_models import ContributorStat, Member, Repository, SyncJob, User
from ..deps import get_current_user, get_db

logger = logging.getLogger("hlb-git-pm.api.repos")

router = APIRouter(prefix="/repos", tags=["repos"])

_app_config = None

# Sync job state: repo full_name -> {status, error, started_at, finished_at}
_sync_jobs: dict[str, dict] = {}
_sync_lock = threading.Lock()


def set_app_config(config):
    global _app_config
    _app_config = config


def _convert_https_to_ssh(https_url: str) -> str:
    """Convert GitHub HTTPS URL to SSH URL for faster cloning.

    Example: https://github.com/WeFi-HLB/ai-ocr.git -> git@github.com:WeFi-HLB/ai-ocr.git
    """
    if https_url.startswith("https://github.com/"):
        # Extract path after domain
        path = https_url[len("https://github.com/"):]
        return f"git@github.com:{path}"
    return https_url


# ---------------------------------------------------------------------------
# Local git helpers (kept for _seed / _update_repo_after_sync)
# ---------------------------------------------------------------------------

def _local_contributors(repo_dir: Path) -> tuple[list[dict], int]:
    """Run git log on a bare/mirror repo and aggregate per-author stats.

    Uses --all to cover every branch/tag, and deduplicates by commit SHA so a
    commit reachable from multiple refs is only counted once.

    Returns (contributors_sorted_by_commit_count, total_unique_commits).
    """
    try:
        out = subprocess.run(
            [
                "git", "log", "--all",
                "--format=%H\x1f%ae\x1f%an\x1f%aI",
            ],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,  # Increased timeout for large repos
        )
        if out.returncode != 0:
            logger.warning("git log 失败 %s (code %d): %s", repo_dir, out.returncode, out.stderr[:200])
            return [], 0

        seen_shas: set[str] = set()
        stats: dict[str, dict] = {}
        for line in out.stdout.splitlines():
            parts = line.split("\x1f", 3)
            if len(parts) != 4:
                continue
            sha, email, name, date = parts
            sha = sha.strip()
            if sha in seen_shas:          # deduplicate cross-branch commits
                continue
            seen_shas.add(sha)
            email = email.strip().lower()
            name = name.strip()
            date = date.strip()
            if not email:
                continue
            if email not in stats:
                stats[email] = {
                    "git_email": email,
                    "git_name": name,
                    "commit_count": 0,
                    "first_commit_at": date,
                    "last_commit_at": date,
                }
            entry = stats[email]
            entry["commit_count"] += 1
            if date < entry["first_commit_at"]:
                entry["first_commit_at"] = date
            if date > entry["last_commit_at"]:
                entry["last_commit_at"] = date

        total_commits = len(seen_shas)
        logger.debug("统计提交数 %s: %d 提交, %d 贡献者", repo_dir, total_commits, len(stats))
        return sorted(stats.values(), key=lambda x: x["commit_count"], reverse=True), total_commits
    except subprocess.TimeoutExpired:
        logger.warning("git log 超时 %s", repo_dir)
        return [], 0
    except Exception as e:
        logger.warning("git log 失败 %s: %s", repo_dir, e)
        return [], 0


def _local_repo_stats(repo_dir: Path) -> dict:
    """Return branch count for a mirror repo."""
    try:
        branch_out = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname)", "refs/heads/"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if branch_out.returncode != 0:
            logger.warning("git for-each-ref 失败 %s (code %d)", repo_dir, branch_out.returncode)
            branch_count = 0
        else:
            branch_count = len([l for l in branch_out.stdout.splitlines() if l.strip()])
    except subprocess.TimeoutExpired:
        logger.warning("git for-each-ref 超时 %s", repo_dir)
        branch_count = 0
    except Exception as e:
        logger.warning("git for-each-ref 异常 %s: %s", repo_dir, e)
        branch_count = 0

    logger.debug("统计分支数 %s: %d 个分支", repo_dir, branch_count)
    return {"branch_count": branch_count}


def _repo_local_dir(clone_url: str, workspace: Path) -> Path | None:
    """Derive the local mirror path from the clone URL (matches git_service logic).

    Supports both HTTPS and SSH URLs:
    - HTTPS: https://github.com/WeFi-HLB/ai-ocr.git -> workspace/WeFi-HLB/ai-ocr
    - SSH:   git@github.com:WeFi-HLB/ai-ocr.git      -> workspace/WeFi-HLB/ai-ocr
    """
    import re
    from urllib.parse import urlparse

    # Handle SSH URL: git@github.com:WeFi-HLB/ai-ocr.git
    if clone_url.startswith("git@"):
        # Extract path after the colon
        match = re.match(r"git@[^:]+:(.+?)(?:\.git)?/?$", clone_url)
        if match:
            path = match.group(1)
            parts = path.split("/")
            if len(parts) >= 2:
                org_slug = parts[0]
                repo_slug = parts[1]
                candidate = workspace / org_slug / repo_slug
                if (candidate / "HEAD").exists() or (candidate / ".git").exists():
                    return candidate

    # Handle HTTPS URL: https://github.com/WeFi-HLB/ai-ocr.git
    parsed = urlparse(clone_url)
    path_parts = Path(parsed.path.rstrip("/")).parts  # ('/', 'WeFi-HLB', 'ai-ocr')
    if len(path_parts) >= 3:
        org_slug = path_parts[-2]
        repo_slug = Path(path_parts[-1]).stem
        candidate = workspace / org_slug / repo_slug
        if (candidate / "HEAD").exists() or (candidate / ".git").exists():
            return candidate

    # Fallback: flat layout (legacy)
    slug = Path(parsed.path.rstrip("/")).stem
    if not slug:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "-", clone_url)
    candidate = workspace / slug
    if (candidate / "HEAD").exists() or (candidate / ".git").exists():
        return candidate
    return None


# ---------------------------------------------------------------------------
# DB seeding / update helpers
# ---------------------------------------------------------------------------

def _seed_repos_from_local(db: Session) -> None:
    """One-time migration: scan workspace for bare/mirror repos and create Repository rows.

    Only runs when the repositories table is empty.
    """
    if db.query(Repository).count() > 0:
        return

    workspace = Path(_app_config.workspace).expanduser().resolve()
    if not workspace.exists():
        return

    now = datetime.now(_tz.utc).isoformat()
    count = 0

    for org_dir in sorted(workspace.iterdir()):
        if not org_dir.is_dir():
            continue
        org_name = org_dir.name
        # Skip if it's a bare repo itself (legacy flat layout — has HEAD at root)
        if (org_dir / "HEAD").exists():
            continue

        for repo_dir in sorted(org_dir.iterdir()):
            if not repo_dir.is_dir() or not (repo_dir / "HEAD").exists():
                continue

            full_name = f"{org_name}/{repo_dir.name}"

            # Try to get clone URL from git config
            try:
                cfg_out = subprocess.run(
                    ["git", "config", "--get", "remote.origin.url"],
                    cwd=repo_dir, capture_output=True, text=True, timeout=5,
                )
                clone_url = cfg_out.stdout.strip() or ""
            except Exception:
                clone_url = ""

            branch_count = _local_repo_stats(repo_dir)["branch_count"]
            _, total_commits = _local_contributors(repo_dir)

            db.add(Repository(
                org_name=org_name,
                full_name=full_name,
                clone_url=clone_url,
                is_cloned=True,
                branch_count=branch_count,
                total_commits=total_commits,
                synced_at=now,
            ))
            count += 1

    if count:
        db.commit()
        logger.info("从本地 clone 初始化 repositories 表: %d 个仓库", count)


def _update_repo_after_sync(full_name: str, local_dir: Path) -> None:
    """Update Repository row after a successful git sync.

    Updates is_cloned, branch_count, total_commits, synced_at.
    Creates the row if it doesn't exist (edge case: sync before refresh).
    """
    from web.database import get_session

    session = get_session()
    try:
        branch_count = _local_repo_stats(local_dir)["branch_count"]
        _, total_commits = _local_contributors(local_dir)
        now = datetime.now(_tz.utc).isoformat()

        repo = session.query(Repository).filter(Repository.full_name == full_name).first()
        if repo:
            repo.is_cloned = True
            repo.branch_count = branch_count
            repo.total_commits = total_commits
            repo.synced_at = now
        else:
            org_name = full_name.split("/")[0] if "/" in full_name else ""
            # Try to get clone URL from git config
            try:
                cfg_out = subprocess.run(
                    ["git", "config", "--get", "remote.origin.url"],
                    cwd=local_dir, capture_output=True, text=True, timeout=5,
                )
                clone_url = cfg_out.stdout.strip() or ""
            except Exception:
                clone_url = ""
            session.add(Repository(
                org_name=org_name,
                full_name=full_name,
                clone_url=clone_url,
                is_cloned=True,
                branch_count=branch_count,
                total_commits=total_commits,
                synced_at=now,
            ))
        session.commit()
    except Exception as e:
        session.rollback()
        logger.warning("Repository 更新失败 %s: %s", full_name, e)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

def _get_activity_level(repo: Repository) -> dict:
    """Calculate activity level aligned with report cadences (daily/weekly/monthly).

    Returns: {
        "level": "today" | "this_week" | "this_month" | "pending" | "unknown",
        "label": "今天活跃" | "本周活跃" | "本月活跃" | "待同步" | "未知",
        "days": days_since_push,
        "color": "success" | "warning" | "danger" | "info",
    }
    """
    # Check sync status first
    if not repo.is_cloned or (repo.branch_count == 0 and repo.total_commits == 0):
        return {
            "level": "pending",
            "label": "待同步",
            "days": None,
            "color": "danger",
        }

    if not repo.pushed_at:
        return {
            "level": "unknown",
            "label": "未知",
            "days": None,
            "color": "info",
        }

    try:
        pushed_dt = datetime.fromisoformat(repo.pushed_at.replace('Z', '+00:00'))
        now = datetime.now(_tz.utc)
        delta = now - pushed_dt
        days = delta.days

        if days < 1:
            return {"level": "today", "label": "今天活跃", "days": days, "color": "success"}
        elif days < 7:
            return {"level": "this_week", "label": "本周活跃", "days": days, "color": "success"}
        elif days < 30:
            return {"level": "this_month", "label": "本月活跃", "days": days, "color": "warning"}
        else:
            # Anything older than a month is "待同步"
            return {"level": "pending", "label": "待同步", "days": days, "color": "danger"}
    except (ValueError, AttributeError):
        return {
            "level": "unknown",
            "label": "未知",
            "days": None,
            "color": "info",
        }


def _build_repo_list(db: Session) -> list[dict]:
    """Build the repo list response from DB tables (zero subprocess calls)."""
    repos = db.query(Repository).filter(Repository.is_deleted == False).all()
    contributors = db.query(ContributorStat).all()
    members = db.query(Member).all()

    # Debug: log synced_at field for verification
    logger.debug("构建仓库列表，已克隆仓库同步时间: %s",
                [(r.full_name, r.synced_at) for r in repos if r.is_cloned])

    # Build member lookup
    email_to_member: dict[str, Member] = {m.git_email.lower(): m for m in members if m.git_email}
    name_to_member: dict[str, Member] = {m.git_name: m for m in members if m.git_name}

    # Group contributors by repo_name
    repo_contributors: dict[str, list[dict]] = {}
    for c in contributors:
        m = email_to_member.get(c.git_email) or name_to_member.get(c.git_name)
        entry = {
            "git_email": c.git_email,
            "git_name": c.git_name,
            "real_name": m.real_name if m else "",
            "department": m.department if m else "",
            "commit_count": c.commit_count,
            "first_commit_at": c.first_commit_at[:10] if c.first_commit_at else "",
            "last_commit_at": c.last_commit_at[:10] if c.last_commit_at else "",
        }
        repo_contributors.setdefault(c.repo_name, []).append(entry)

    # Sort contributors within each repo by commit count desc
    for contribs in repo_contributors.values():
        contribs.sort(key=lambda x: x["commit_count"], reverse=True)

    result = []
    for r in repos:
        activity = _get_activity_level(r)

        result.append({
            "org_name": r.org_name,
            "full_name": r.full_name,
            "description": r.description,
            "language": r.language,
            "default_branch": r.default_branch,
            "pushed_at": r.pushed_at,
            "stars": r.stars,
            "is_archived": r.is_archived,
            "is_fork": r.is_fork,
            "clone_url": r.clone_url,
            "is_cloned": r.is_cloned,
            "synced_at": r.synced_at,  # Last successful sync time
            "is_active": activity["level"] in ("today", "this_week", "this_month"),
            "activity": activity,
            "branch_count": r.branch_count,
            "total_commits": r.total_commits,
            "contributors": repo_contributors.get(r.full_name, []),
        })

    # Sort: by activity level, then by cloned status, then by pushed_at desc
    activity_order = {"today": 0, "this_week": 1, "this_month": 2, "pending": 3, "unknown": 4}
    result.sort(key=lambda r: r["pushed_at"], reverse=True)
    result.sort(key=lambda r: not r["is_cloned"])
    result.sort(key=lambda r: activity_order.get(r["activity"]["level"], 999))

    return result


@router.get("")
def list_repos(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if _app_config is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="配置未加载")

    # Seed from local clones on first access if DB is empty
    _seed_repos_from_local(db)

    return _build_repo_list(db)


@router.post("/refresh")
def refresh_repos(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Refresh repository metadata from GitHub API and persist to DB.

    Logic:
    1. Fetch all repos from GitHub
    2. For repos no longer in GitHub: mark as is_deleted=True
    3. For new repos from GitHub: create with is_cloned=False, branch_count=0, total_commits=0
    4. For existing repos: update GitHub metadata and check local clone status
    """
    if _app_config is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="配置未加载")

    gh_cfg = _app_config.github
    if gh_cfg is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未配置 GitHub App")

    from app.github_app import list_repositories_with_meta
    try:
        repos_meta = list_repositories_with_meta(gh_cfg)
    except Exception as e:
        logger.warning("GitHub API 失败 [%s]: %s", gh_cfg.organization, e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"GitHub API 失败: {e}")

    workspace = Path(_app_config.workspace).expanduser().resolve()
    now = datetime.now(_tz.utc).isoformat()

    # Collect full_name set from GitHub
    github_full_names = {meta.full_name for meta in repos_meta}

    # Mark repos deleted in GitHub as is_deleted=True
    deleted_repos = db.query(Repository).filter(Repository.full_name.notin_(github_full_names)).all()
    for repo in deleted_repos:
        if not repo.is_deleted:
            repo.is_deleted = True
            logger.info("标记为已删除: %s", repo.full_name)

    # Create or update repos from GitHub
    for meta in repos_meta:
        org_name = meta.full_name.split("/")[0] if "/" in meta.full_name else ""
        # Keep HTTPS URLs so GitHub App installation tokens can authenticate via GIT_ASKPASS.
        clone_url = meta.clone_url
        local_dir = _repo_local_dir(clone_url, workspace)
        is_cloned = local_dir is not None

        repo = db.query(Repository).filter(Repository.full_name == meta.full_name).first()
        if repo:
            # Existing repo: update metadata and local clone status
            repo.org_name = org_name
            repo.description = meta.description
            repo.language = meta.language
            repo.default_branch = meta.default_branch
            repo.pushed_at = meta.pushed_at
            repo.stars = meta.stars
            repo.is_archived = meta.is_archived
            repo.is_fork = meta.is_fork
            repo.clone_url = clone_url
            # Recheck if locally cloned (might have been cloned since last refresh)
            repo.is_cloned = is_cloned
            repo.is_deleted = False  # restore if was marked deleted before
            repo.meta_updated_at = now
        else:
            # New repo: create with default values for clone-related fields
            db.add(Repository(
                org_name=org_name,
                full_name=meta.full_name,
                description=meta.description,
                language=meta.language,
                default_branch=meta.default_branch,
                pushed_at=meta.pushed_at,
                stars=meta.stars,
                is_archived=meta.is_archived,
                is_fork=meta.is_fork,
                clone_url=clone_url,
                is_cloned=is_cloned,  # check if already cloned locally
                is_deleted=False,
                branch_count=0,        # will be filled on sync
                total_commits=0,       # will be filled on sync
                meta_updated_at=now,
            ))
            logger.info("新增仓库: %s", meta.full_name)

    db.commit()
    return _build_repo_list(db)


# ---------------------------------------------------------------------------
# Sync helpers
# ---------------------------------------------------------------------------

def _persist_contributors(full_name: str, local_dir: Path) -> None:
    """Write contributor stats for one repo into the database after a successful sync."""
    from web.database import get_session

    contributors, _ = _local_contributors(local_dir)
    if not contributors:
        return

    org_name = full_name.split("/")[0] if "/" in full_name else ""
    synced_at = datetime.now(_tz.utc).isoformat()
    session = get_session()
    try:
        session.query(ContributorStat).filter(ContributorStat.repo_name == full_name).delete()
        for c in contributors:
            session.add(ContributorStat(
                org_name=org_name,
                repo_name=full_name,
                git_email=c["git_email"],
                git_name=c["git_name"],
                commit_count=c["commit_count"],
                first_commit_at=c["first_commit_at"][:10] if c["first_commit_at"] else "",
                last_commit_at=c["last_commit_at"][:10] if c["last_commit_at"] else "",
                synced_at=synced_at,
            ))
        session.commit()
        logger.info("贡献者统计已入库: %s (%d 人)", full_name, len(contributors))
    except Exception as e:
        session.rollback()
        logger.warning("贡献者统计入库失败 %s: %s", full_name, e)
    finally:
        session.close()


def _do_sync(repos_to_sync: list[dict]) -> None:
    """Clone or fetch repos concurrently using a thread pool."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from app.github_app import create_installation_token
    from app.git_service import ensure_repository
    from app.config import RepositoryConfig
    from web.database import get_session
    from web.db_models import ProxyConfig

    gh_cfg = _app_config.github
    token = ""
    if gh_cfg:
        try:
            token = create_installation_token(gh_cfg)
        except Exception as e:
            logger.warning("获取 token 失败: %s", e)

    workspace = Path(_app_config.workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    # Get proxy configuration
    proxy_config = None
    try:
        db = get_session()
        proxy = db.query(ProxyConfig).first()
        if proxy:
            proxy_config = {
                "http_proxy": proxy.http_proxy,
                "https_proxy": proxy.https_proxy,
                "no_proxy": proxy.no_proxy,
                "enabled": proxy.enabled,
            }
            logger.info("代理配置已加载: enabled=%s, http_proxy=%s", proxy.enabled, proxy.http_proxy if proxy.enabled else "N/A")
        else:
            logger.info("未找到代理配置")
        db.close()
    except Exception as e:
        logger.warning("获取代理配置失败: %s", e)

    def _needs_sync(row: Repository | None, repo: dict) -> bool:
        """Fetch only when the local mirror cannot be trusted as current."""
        local_dir = _repo_local_dir(repo["clone_url"], workspace)
        if local_dir is None or row is None or not row.is_cloned or not row.synced_at:
            return True
        pushed_at = str(repo.get("pushed_at") or row.pushed_at or "")
        if not pushed_at:
            return True
        try:
            pushed_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            synced_dt = datetime.fromisoformat(str(row.synced_at).replace("Z", "+00:00"))
            if pushed_dt.tzinfo is None:
                pushed_dt = pushed_dt.replace(tzinfo=_tz.utc)
            if synced_dt.tzinfo is None:
                synced_dt = synced_dt.replace(tzinfo=_tz.utc)
            return pushed_dt > synced_dt
        except (TypeError, ValueError):
            logger.warning("无法解析仓库时间戳，强制同步: %s pushed_at=%r synced_at=%r", repo["full_name"], pushed_at, row.synced_at)
            return True

    def _sync_one(r: dict) -> None:
        full_name = r["full_name"]
        session = get_session()
        try:
            # Update DB: mark as syncing
            with _sync_lock:
                _sync_jobs[full_name]["status"] = "syncing"

            job = session.query(SyncJob).filter(SyncJob.repo_name == full_name).first()
            if job:
                job.status = "syncing"
            else:
                job = SyncJob(repo_name=full_name, status="syncing", started_at=datetime.now(_tz.utc).isoformat())
                session.add(job)
            session.commit()

            repo_row = session.query(Repository).filter(Repository.full_name == full_name).first()
            should_sync = _needs_sync(repo_row, r)
            if not should_sync:
                with _sync_lock:
                    _sync_jobs[full_name] = {
                        "status": "done",
                        "error": None,
                        "cached": True,
                        "finished_at": time.time(),
                    }
                job.status = "done"
                job.error = ""
                job.finished_at = datetime.now(_tz.utc).isoformat()
                session.commit()
                logger.info("同步命中缓存，跳过 fetch: %s", full_name)
                return

            cfg = RepositoryConfig(
                name=full_name,
                url=r["clone_url"],
                branch="",
                fetch=True,
                auth_token=token,
            )
            # Pass proxy_config explicitly (it's captured from outer scope but be explicit for clarity)
            logger.info("同步开始: %s, 代理配置: %s", full_name, proxy_config)
            local_dir = ensure_repository(cfg, workspace, proxy_config=proxy_config)
            if local_dir:
                _persist_contributors(full_name, local_dir)
                _update_repo_after_sync(full_name, local_dir)
            else:
                logger.warning("ensure_repository 返回空路径: %s", full_name)

            # Update DB: mark as done
            with _sync_lock:
                _sync_jobs[full_name] = {
                    "status": "done",
                    "error": None,
                    "finished_at": time.time(),
                }

            job = session.query(SyncJob).filter(SyncJob.repo_name == full_name).first()
            if job:
                job.status = "done"
                job.error = ""
                job.finished_at = datetime.now(_tz.utc).isoformat()
            session.commit()
            logger.info("同步完成: %s", full_name)
        except Exception as e:
            error_msg = str(e)[:500]
            with _sync_lock:
                _sync_jobs[full_name] = {
                    "status": "failed",
                    "error": error_msg,
                    "finished_at": time.time(),
                }

            job = session.query(SyncJob).filter(SyncJob.repo_name == full_name).first()
            if job:
                job.status = "failed"
                job.error = error_msg
                job.finished_at = datetime.now(_tz.utc).isoformat()
            session.commit()
            logger.warning("同步失败: %s — %s", full_name, e)
        finally:
            session.close()

    max_workers = min(8, len(repos_to_sync))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_sync_one, r): r["full_name"] for r in repos_to_sync}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                logger.warning("同步线程异常 [%s]: %s", futures[fut], e)


@router.post("/sync")
def sync_repos(
    full_names: list[str] = Body(..., description="要同步的仓库 full_name 列表，空列表表示全量"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Trigger async clone/fetch for one or all repos. Returns immediately."""
    if _app_config is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="配置未加载")
    if _app_config.github is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未配置 GitHub App")

    # Determine which repos to sync
    if full_names:
        repos_to_sync = []
        for name in full_names:
            row = db.query(Repository).filter(Repository.full_name == name).first()
            repos_to_sync.append({
                "full_name": name,
                "clone_url": row.clone_url if row and row.clone_url else _clone_url_from_name(name, db),
                "pushed_at": row.pushed_at if row else "",
            })
    else:
        # Full sync: read from DB first
        db_repos = db.query(Repository).all()
        if db_repos:
            repos_to_sync = [
                {"full_name": r.full_name, "clone_url": r.clone_url, "pushed_at": r.pushed_at, "synced_at": r.synced_at, "is_cloned": r.is_cloned}
                for r in db_repos
            ]
        else:
            # DB empty: fallback to GitHub API
            from app.github_app import list_repositories_with_meta, GitHubAppError
            try:
                metas = list_repositories_with_meta(_app_config.github)
                repos_to_sync = [{"full_name": m.full_name, "clone_url": m.clone_url, "pushed_at": m.pushed_at} for m in metas]
            except GitHubAppError as e:
                logger.warning("GitHub API 失败 [%s]: %s", _app_config.github.organization, e)
                repos_to_sync = []
            if not repos_to_sync:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GitHub API 连接失败，无法获取仓库列表")

    if not repos_to_sync:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可同步的仓库")

    # Mark all as queued
    with _sync_lock:
        for r in repos_to_sync:
            if _sync_jobs.get(r["full_name"], {}).get("status") != "syncing":
                _sync_jobs[r["full_name"]] = {"status": "queued", "error": None, "started_at": time.time()}

    thread = threading.Thread(target=_do_sync, args=(repos_to_sync,), daemon=True)
    thread.start()

    return {"queued": [r["full_name"] for r in repos_to_sync]}


@router.get("/sync/status")
def sync_status(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Return current sync job states from both memory and database."""
    result = {}

    # Get from memory (in-progress jobs)
    with _sync_lock:
        result.update(_sync_jobs)

    # Get from database (persisted jobs)
    jobs = db.query(SyncJob).all()
    for job in jobs:
        result[job.repo_name] = {
            "status": job.status,
            "error": job.error,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }
        if _sync_jobs.get(job.repo_name, {}).get("cached"):
            result[job.repo_name]["cached"] = True

    return result


def _clone_url_from_name(full_name: str, db: Session) -> str:
    """Look up clone URL from the Repository table, fallback to GitHub convention."""
    repo = db.query(Repository).filter(Repository.full_name == full_name).first()
    if repo and repo.clone_url:
        return repo.clone_url
    # Fallback: construct from GitHub convention
    return f"https://github.com/{full_name}.git"
