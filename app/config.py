from __future__ import annotations

import logging
import os
import re
try:  # Python 3.11+ ships tomllib; tomli keeps the service usable on 3.10.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - depends on interpreter version
    import tomli as tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")
_cfg_logger = logging.getLogger("git_daily_report.config")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        def _sub(match: re.Match) -> str:
            key = match.group(1)
            val = os.getenv(key)
            if val is None:
                _cfg_logger.warning("配置中引用的环境变量 %s 未设置，已替换为空字符串", key)
                return ""
            return val
        return _ENV_PATTERN.sub(_sub, value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


@dataclass(frozen=True, repr=False)
class RepositoryConfig:
    name: str
    path: str | None = None
    url: str | None = None
    branch: str = ""
    fetch: bool = True
    auth_token: str | None = None

    def __repr__(self) -> str:
        token_hint = "<set>" if self.auth_token else "<none>"
        return (
            f"RepositoryConfig(name={self.name!r}, branch={self.branch!r}, "
            f"auth_token={token_hint})"
        )


@dataclass(frozen=True)
class GitHubConfig:
    organization: str
    app_id: int
    installation_id: int
    private_key_file: str
    api_base_url: str = "https://api.github.com"
    include_archived: bool = False
    include_forks: bool = False


@dataclass(frozen=True)
class EmailConfig:
    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    sender: str = ""
    recipients: tuple[str, ...] = ()
    use_tls: bool = True
    use_ssl: bool = False


@dataclass(frozen=True)
class AiConfig:
    enabled: bool = True
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    timeout_seconds: int = 60
    max_commits: int = 80
    thinking_enabled: bool | None = None


@dataclass(frozen=True)
class AppConfig:
    repositories: tuple[RepositoryConfig, ...]
    email: EmailConfig
    github: GitHubConfig | None = None
    ai: AiConfig = field(default_factory=AiConfig)
    workspace: str = ".data/repos"
    timezone: str = "Asia/Shanghai"
    run_at: str = "18:30"
    subject_prefix: str = "Git 每日提交日报"
    db_path: str = ".data/hlb-git-pm.db"


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("rb") as file:
        raw = _expand_env(tomllib.load(file))

    repositories = tuple(
        RepositoryConfig(
            name=str(item["name"]),
            path=item.get("path"),
            url=item.get("url"),
            branch=str(item.get("branch", "")),
            fetch=bool(item.get("fetch", True)),
        )
        for item in raw.get("repositories", [])
    )
    github_raw = raw.get("github")
    github = None
    if github_raw:
        required = ("organization", "app_id", "installation_id", "private_key_file")
        missing = [key for key in required if not github_raw.get(key)]
        if missing:
            raise ValueError(f"github 配置缺少: {', '.join(missing)}")
        _gh_api_base = str(github_raw.get("api_base_url", "https://api.github.com")).rstrip("/")
        if github_raw.get("api_base_url") and not _gh_api_base.startswith("https://"):
            raise ValueError(f"github.api_base_url 必须使用 HTTPS，当前值: {_gh_api_base!r}")
        github = GitHubConfig(
            organization=str(github_raw["organization"]),
            app_id=int(github_raw["app_id"]),
            installation_id=int(github_raw["installation_id"]),
            private_key_file=str(github_raw["private_key_file"]),
            api_base_url=_gh_api_base,
            include_archived=bool(github_raw.get("include_archived", False)),
            include_forks=bool(github_raw.get("include_forks", False)),
        )

    if not repositories and github is None:
        raise ValueError("至少配置一个 [[repositories]] 仓库，或配置 [github]")

    _run_at = str(raw.get("run_at", "18:30"))
    try:
        _h, _m = _run_at.split(":", 1)
        if not (0 <= int(_h) < 24 and 0 <= int(_m) < 60):
            raise ValueError
    except (ValueError, AttributeError):
        raise ValueError(f"run_at 格式无效: {_run_at!r}，应为 HH:MM（如 18:30）")

    email_raw = raw.get("email", {})
    recipients = tuple(str(item).strip() for item in email_raw.get("recipients", []) if str(item).strip())
    if not email_raw.get("host") or not email_raw.get("sender"):
        raise ValueError("email.host、email.sender 必须配置")

    ai_raw = raw.get("ai", {})
    _ai_base = str(ai_raw.get("base_url", "https://api.openai.com/v1")).rstrip("/")
    if ai_raw.get("base_url") and not _ai_base.startswith("https://"):
        raise ValueError(f"ai.base_url 必须使用 HTTPS，当前值: {_ai_base!r}")
    return AppConfig(
        repositories=repositories,
        email=EmailConfig(
            host=str(email_raw["host"]),
            port=int(email_raw.get("port", 587)),
            username=str(email_raw.get("username", "")),
            password=str(email_raw.get("password", "")),
            sender=str(email_raw["sender"]),
            recipients=recipients,
            use_tls=bool(email_raw.get("use_tls", True)),
            use_ssl=bool(email_raw.get("use_ssl", False)),
        ),
        github=github,
        ai=AiConfig(
            enabled=bool(ai_raw.get("enabled", True)),
            base_url=_ai_base,
            api_key=str(ai_raw.get("api_key", "")),
            model=str(ai_raw.get("model", "gpt-4o-mini")),
            timeout_seconds=int(ai_raw.get("timeout_seconds", 60)),
            max_commits=int(ai_raw.get("max_commits", 80)),
            thinking_enabled=(
                bool(ai_raw["thinking_enabled"]) if "thinking_enabled" in ai_raw else None
            ),
        ),
        workspace=str(raw.get("workspace", ".data/repos")),
        timezone=str(raw.get("timezone", "Asia/Shanghai")),
        run_at=_run_at,
        subject_prefix=str(raw.get("subject_prefix", "Git 每日提交日报")),
        db_path=str(raw.get("db_path", ".data/hlb-git-pm.db")),
    )
