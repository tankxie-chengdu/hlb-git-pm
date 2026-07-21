from __future__ import annotations

import logging
import re
import os
import shlex
import subprocess
import tempfile
import time as time_module
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from urllib.parse import urlparse

from .config import RepositoryConfig
from .models import Commit, RepositoryReport


logger = logging.getLogger("git_daily_report.git")


def _redact_command(command: str) -> str:
    """Hide credentials that may be embedded in proxy URLs."""
    return re.sub(r"(https?://[^\s:/@]+):[^\s/@]+@", r"\1:***@", command)


def _truncate_output(value: str, limit: int = 4000) -> str:
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[输出已截断]..."


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


def _run_git(
    args: list[str],
    cwd: Path,
    *,
    check: bool = True,
    env: dict[str, str] | None = None,
    proxy_config: dict[str, str] | None = None,
    command_log: list[dict] | None = None,
) -> str:
    """Run a git command with optional proxy configuration.

    Args:
        args: Git command arguments (without 'git' prefix)
        cwd: Working directory
        check: Whether to raise on non-zero exit code
        env: Environment variables
        proxy_config: Dict with 'http_proxy' and 'https_proxy' keys
    """
    cmd = ["git"]

    # Add proxy configuration as git -c options if enabled
    if proxy_config and proxy_config.get("enabled"):
        if proxy_config.get("http_proxy"):
            cmd.extend(["-c", f"http.proxy={proxy_config['http_proxy']}"])
            logger.debug("使用 HTTP 代理: %s", proxy_config['http_proxy'])
        if proxy_config.get("https_proxy"):
            cmd.extend(["-c", f"https.proxy={proxy_config['https_proxy']}"])
            logger.debug("使用 HTTPS 代理: %s", proxy_config['https_proxy'])
    elif proxy_config:
        logger.debug("代理配置已禁用")

    # Add performance and stability configurations for large repositories
    # These help with network issues and large file transfers
    cmd.extend([
        "-c", "core.compression=0",           # Disable compression for speed
        "-c", "http.postBuffer=524288000",    # 500MB buffer for large pushes
        "-c", "http.lowSpeedLimit=0",         # No speed limit during large transfers
        "-c", "http.lowSpeedTime=999999",     # High timeout for large transfers
    ])

    cmd.extend(args)

    command_entry = None
    if command_log is not None:
        command_entry = {
            "command": _redact_command(shlex.join(cmd)),
            "cwd": str(cwd),
            "status": "running",
            "started_at": time_module.time(),
        }
        command_log.append(command_entry)

    started = time_module.monotonic()
    try:
        process = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=False, env=env
        )
    except Exception as error:
        if command_entry is not None:
            command_entry.update(
                {
                    "status": "failed",
                    "duration_ms": int((time_module.monotonic() - started) * 1000),
                    "error": str(error),
                }
            )
        raise
    if command_entry is not None:
        command_entry.update(
            {
                "status": "success" if process.returncode == 0 else "failed",
                "returncode": process.returncode,
                "duration_ms": int((time_module.monotonic() - started) * 1000),
                "stdout": _truncate_output(process.stdout),
                "stderr": _truncate_output(process.stderr),
            }
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
    if config.url and config.url.startswith("ssh://git@github.com/"):
        path = config.url.removeprefix("ssh://git@github.com/").removesuffix("/")
        parts = path.removesuffix(".git").split("/")
        if len(parts) >= 2:
            return workspace / parts[0] / parts[1]

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


def _https_url_for_token(url: str, token: str | None) -> str:
    """GitHub App tokens work over HTTPS; normalize GitHub SSH URLs when present."""
    if token and url.startswith("git@github.com:"):
        return "https://github.com/" + url.removeprefix("git@github.com:")
    if token and url.startswith("ssh://git@github.com/"):
        return "https://github.com/" + url.removeprefix("ssh://git@github.com/")
    return url


def _https_to_ssh(https_url: str) -> str:
    """Convert HTTPS URL to SSH format for better network stability.

    Example: https://github.com/WeFi-HLB/ai-ocr.git -> git@github.com:WeFi-HLB/ai-ocr.git
    """
    if https_url.startswith("https://github.com/"):
        path = https_url[len("https://github.com/"):]
        return f"git@github.com:{path}"
    return https_url


def ensure_repository(
    config: RepositoryConfig,
    workspace: Path,
    *,
    allow_clone: bool = True,
    proxy_config: dict[str, str] | None = None,
    command_log: list[dict] | None = None,
) -> Path:
    target = _repo_dir(config, workspace)
    remote_url = _https_url_for_token(config.url or "", config.auth_token)
    if (target / ".git").exists() or (target / "HEAD").exists():
        if remote_url:
            current_url = _run_git(["remote", "get-url", "origin"], target, check=False, proxy_config=proxy_config, command_log=command_log).strip()
            if current_url and current_url != remote_url:
                _run_git(["remote", "set-url", "origin", remote_url], target, proxy_config=proxy_config, command_log=command_log)
        if config.fetch:
            logger.info("正在获取仓库 %s (%s)", config.name, target)
            with _git_auth_env(config.auth_token) as env:
                _run_git(["fetch", "--all", "--prune"], target, env=env, proxy_config=proxy_config, command_log=command_log)
        return target
    if not config.url:
        raise GitError(f"仓库 {config.name} 不存在: {target}")
    if not allow_clone:
        raise GitError(f"仓库 {config.name} 尚未同步本地 mirror: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    # Strategy: Try SSH first (more stable), fallback to HTTPS with token
    clone_url = remote_url
    ssh_url = _https_to_ssh(config.url or "")

    if ssh_url != remote_url:
        # HTTPS URL exists, try SSH first
        logger.info("正在克隆仓库 %s -> %s (SSH 优先)", config.url, target)
        try:
            _run_git(["clone", "--mirror", ssh_url, str(target)], workspace, proxy_config=proxy_config, command_log=command_log)
            return target
        except GitError as e:
            logger.warning("SSH 克隆失败，降级到 HTTPS: %s", e)
            clone_url = remote_url

    # SSH failed or not applicable, use HTTPS with token
    logger.info("正在克隆仓库 %s -> %s (HTTPS)", config.url, target)
    with _git_auth_env(config.auth_token) as env:
        _run_git(["clone", "--mirror", clone_url, str(target)], workspace, env=env, proxy_config=proxy_config, command_log=command_log)
    return target


def _parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def scan_repository(
    config: RepositoryConfig,
    workspace: Path,
    target_date: date,
    timezone: tzinfo,
    *,
    end_date: date | None = None,
    allow_clone: bool = True,
    proxy_config: dict[str, str] | None = None,
) -> RepositoryReport:
    try:
        _end = end_date if end_date is not None else target_date
        logger.info("扫描仓库 %s，日期 %s ~ %s", config.name, target_date, _end)
        repo_dir = ensure_repository(config, workspace, allow_clone=allow_clone, proxy_config=proxy_config)
        branch = config.branch or "all branches"
        scan_refs = [config.branch] if config.branch else ["--all"]
        if config.fetch and config.branch:
            remote_ref = f"origin/{config.branch}"
            if _run_git(["rev-parse", "--verify", remote_ref], repo_dir, check=False, proxy_config=proxy_config).strip():
                scan_refs = [remote_ref]
        start = datetime.combine(target_date, time.min, timezone)
        end = datetime.combine(_end + timedelta(days=1), time.min, timezone)
        raw = _run_git(
            [
                "log",
                *scan_refs,
                "--numstat",
                f"--since={start.isoformat()}",
                f"--until={end.isoformat()}",
                "--date=iso-strict",
                "--format=%x1e%H%x1f%an%x1f%ae%x1f%aI%x1f%cI%x1f%s",
            ],
            repo_dir,
            proxy_config=proxy_config,
        )
        commits: list[Commit] = []
        for block in raw.split("\x1e"):
            lines = [line for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            fields = lines[0].split("\x1f", 5)
            if len(fields) != 6:
                continue
            sha, author_name, author_email, authored_at, committed_at, subject = fields
            additions = deletions = files_changed = 0
            for stat_line in lines[1:]:
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
                    committed_at=_parse_date(committed_at).astimezone(timezone),
                )
            )
        logger.info("仓库 %s 扫描完成：%d 次提交", config.name, len(commits))
        return RepositoryReport(config.name, branch, commits)
    except (GitError, OSError) as error:
        logger.warning("仓库 %s 扫描失败: %s", config.name, error)
        return RepositoryReport(config.name, config.branch or "HEAD", error=str(error))
