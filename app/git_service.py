from __future__ import annotations

import logging
import re
import os
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from urllib.parse import urlparse

from .config import RepositoryConfig
from .models import Commit, RepositoryReport


logger = logging.getLogger("git_daily_report.git")


class GitError(RuntimeError):
    pass


@contextmanager
def _git_auth_env(token: str | None):
    if not token:
        yield None
        return
    script_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", prefix="git-askpass-", delete=False, encoding="utf-8") as script:
            script.write(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  *Username*) echo x-access-token ;;\n"
                "  *Password*) echo \"$GITHUB_APP_TOKEN\" ;;\n"
                "  *) echo x-access-token ;;\n"
                "esac\n"
            )
            script_path = script.name
        os.chmod(script_path, 0o700)
        env = os.environ.copy()
        env.update(
            {
                "GIT_ASKPASS": script_path,
                "GIT_TERMINAL_PROMPT": "0",
                "GITHUB_APP_TOKEN": token,
            }
        )
        yield env
    finally:
        if script_path:
            try:
                os.unlink(script_path)
            except FileNotFoundError:
                pass


def _run_git(args: list[str], cwd: Path, *, check: bool = True, env: dict[str, str] | None = None) -> str:
    process = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=False, env=env
    )
    if check and process.returncode:
        detail = process.stderr.strip() or process.stdout.strip()
        raise GitError(f"git {' '.join(args)} 失败: {detail}")
    return process.stdout


def _repo_dir(config: RepositoryConfig, workspace: Path) -> Path:
    if config.path:
        return Path(config.path).expanduser().resolve()

    parsed = urlparse(config.url or "")

    # Handle SSH URL: git@github.com:WeFi-HLB/ai-ocr.git
    if config.url and config.url.startswith("git@"):
        # Extract path after the colon
        match = re.match(r"git@[^:]+:(.+?)(?:\.git)?/?$", config.url)
        if match:
            path = match.group(1)
            parts = path.split("/")
            if len(parts) >= 2:
                org_slug = parts[0]
                repo_slug = parts[1]
                return workspace / org_slug / repo_slug

    # Handle HTTPS URL: https://github.com/WeFi-HLB/ai-ocr.git
    # Extract org and repo slug from URL path, e.g. "/WeFi-HLB/ai-ocr.git" -> ("WeFi-HLB", "ai-ocr")
    path_parts = Path(parsed.path.rstrip("/")).parts  # ('/', 'WeFi-HLB', 'ai-ocr.git')
    if len(path_parts) >= 3:
        org_slug = path_parts[-2]
        repo_slug = Path(path_parts[-1]).stem
        return workspace / org_slug / repo_slug

    # Fallback for non-standard URLs or local paths
    slug = Path(parsed.path.rstrip("/")).stem or re.sub(r"[^a-zA-Z0-9_-]", "-", config.name.lower())
    return workspace / slug


def ensure_repository(config: RepositoryConfig, workspace: Path) -> Path:
    target = _repo_dir(config, workspace)
    if (target / ".git").exists() or (target / "HEAD").exists():
        if config.fetch:
            logger.info("正在获取仓库 %s (%s)", config.name, target)
            with _git_auth_env(config.auth_token) as env:
                _run_git(["fetch", "--all", "--prune"], target, env=env)
        return target
    if not config.url:
        raise GitError(f"仓库 {config.name} 不存在: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    logger.info("正在克隆仓库 %s -> %s", config.url, target)
    with _git_auth_env(config.auth_token) as env:
        _run_git(["clone", "--mirror", config.url, str(target)], workspace, env=env)
    return target


def _parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def scan_repository(config: RepositoryConfig, workspace: Path, target_date: date, timezone: tzinfo, *, end_date: date | None = None) -> RepositoryReport:
    try:
        _end = end_date if end_date is not None else target_date
        logger.info("扫描仓库 %s，日期 %s ~ %s", config.name, target_date, _end)
        repo_dir = ensure_repository(config, workspace)
        branch = config.branch or "all branches"
        scan_refs = [config.branch] if config.branch else ["--all"]
        if config.fetch and config.branch:
            remote_ref = f"origin/{config.branch}"
            if _run_git(["rev-parse", "--verify", remote_ref], repo_dir, check=False).strip():
                scan_refs = [remote_ref]
        start = datetime.combine(target_date, time.min, timezone)
        end = datetime.combine(_end + timedelta(days=1), time.min, timezone)
        raw = _run_git(
            [
                "log",
                *scan_refs,
                f"--since={start.isoformat()}",
                f"--until={end.isoformat()}",
                "--date=iso-strict",
                "--format=%H%x1f%an%x1f%ae%x1f%aI%x1f%s",
            ],
            repo_dir,
        )
        commits: list[Commit] = []
        for line in raw.splitlines():
            fields = line.split("\x1f", 4)
            if len(fields) != 5:
                continue
            sha, author_name, author_email, authored_at, subject = fields
            stats = _run_git(["show", "--format=", "--numstat", sha], repo_dir)
            additions = deletions = files_changed = 0
            for stat_line in stats.splitlines():
                stat = stat_line.split("\t")
                if len(stat) < 3 or not stat[0].isdigit() or not stat[1].isdigit():
                    continue
                additions += int(stat[0])
                deletions += int(stat[1])
                files_changed += 1
            commits.append(
                Commit(
                    repository=config.name,
                    sha=sha,
                    author_name=author_name,
                    author_email=author_email,
                    authored_at=_parse_date(authored_at),
                    subject=subject,
                    files_changed=files_changed,
                    additions=additions,
                    deletions=deletions,
                )
            )
        logger.info("仓库 %s 扫描完成：%d 次提交", config.name, len(commits))
        return RepositoryReport(config.name, branch, commits)
    except (GitError, OSError) as error:
        logger.warning("仓库 %s 扫描失败: %s", config.name, error)
        return RepositoryReport(config.name, config.branch or "HEAD", error=str(error))
