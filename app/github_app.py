from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import GitHubConfig, RepositoryConfig


class GitHubAppError(RuntimeError):
    pass


def _convert_https_to_ssh(https_url: str) -> str:
    """Convert GitHub HTTPS URL to SSH URL for faster cloning.

    Example: https://github.com/WeFi-HLB/ai-ocr.git -> git@github.com:WeFi-HLB/ai-ocr.git
    """
    if https_url.startswith("https://github.com/"):
        # Extract path after domain
        path = https_url[len("https://github.com/"):]
        return f"git@github.com:{path}"
    return https_url


@dataclass
class RepoMeta:
    full_name: str
    description: str
    language: str
    default_branch: str
    pushed_at: str
    stars: int
    is_archived: bool
    is_fork: bool
    clone_url: str


_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _request_json(
    url: str,
    *,
    method: str = "GET",
    token: str,
    body: dict[str, Any] | None = None,
    auth_scheme: str = "Bearer",
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"{auth_scheme} {token}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code in _RETRY_STATUSES and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise GitHubAppError(f"GitHub API {error.code}: {detail}") from error
        except (OSError, json.JSONDecodeError) as error:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise GitHubAppError(f"GitHub API 请求失败: {error}") from error
    # unreachable, but satisfies type checker
    raise GitHubAppError("GitHub API 请求失败：已超过重试次数")


def create_app_jwt(config: GitHubConfig) -> str:
    try:
        import jwt
    except ImportError as error:  # pragma: no cover - environment dependency
        raise GitHubAppError("缺少 PyJWT，请执行 pip install -r requirements.txt") from error
    pem_path = Path(config.private_key_file).expanduser()
    if not pem_path.is_file():
        raise GitHubAppError(f"私钥文件不存在: {pem_path}")
    if pem_path.stat().st_mode & 0o077:
        raise GitHubAppError(
            f"私钥文件 {pem_path} 权限过于宽松，请执行: chmod 600 {pem_path}"
        )
    private_key = pem_path.read_text(encoding="utf-8")
    now = int(time.time())
    return str(
        jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": str(config.app_id)},
            private_key,
            algorithm="RS256",
        )
    )


def create_installation_token(config: GitHubConfig) -> str:
    app_jwt = create_app_jwt(config)
    result = _request_json(
        f"{config.api_base_url}/app/installations/{config.installation_id}/access_tokens",
        method="POST",
        token=app_jwt,
    )
    token = result.get("token")
    if not token:
        raise GitHubAppError("GitHub 没有返回 installation token")
    return str(token)


def discover_repositories(config: GitHubConfig) -> tuple[RepositoryConfig, ...]:
    token = create_installation_token(config)
    repositories: list[RepositoryConfig] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        result = _request_json(
            f"{config.api_base_url}/installation/repositories?{query}",
            token=token,
        )
        items = result.get("repositories", [])
        if not isinstance(items, list):
            raise GitHubAppError("GitHub 返回的 repositories 不是列表")
        for item in items:
            if not isinstance(item, dict):
                continue
            full_name = str(item.get("full_name") or "")
            if not full_name.lower().startswith(f"{config.organization}/".lower()):
                continue
            if item.get("archived", False) and not config.include_archived:
                continue
            if item.get("fork", False) and not config.include_forks:
                continue
            name = full_name or str(item.get("name") or "")
            clone_url = str(item.get("clone_url") or "")
            if not name or not clone_url:
                continue
            repositories.append(
                RepositoryConfig(
                    name=name,
                    url=clone_url,
                    branch="",
                    fetch=True,
                    auth_token=token,
                )
            )
        if len(items) < 100:
            break
        page += 1
    return tuple(repositories)


def list_repositories_with_meta(config: GitHubConfig) -> tuple[RepoMeta, ...]:
    """Return full metadata for every accessible repo under the org."""
    token = create_installation_token(config)
    result: list[RepoMeta] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        data = _request_json(
            f"{config.api_base_url}/installation/repositories?{query}",
            token=token,
        )
        items = data.get("repositories", [])
        if not isinstance(items, list):
            raise GitHubAppError("GitHub 返回的 repositories 不是列表")
        for item in items:
            if not isinstance(item, dict):
                continue
            full_name = str(item.get("full_name") or "")
            if not full_name.lower().startswith(f"{config.organization}/".lower()):
                continue
            clone_url = str(item.get("clone_url") or "")
            if not full_name or not clone_url:
                continue
            result.append(RepoMeta(
                full_name=full_name,
                description=str(item.get("description") or ""),
                language=str(item.get("language") or ""),
                default_branch=str(item.get("default_branch") or "main"),
                pushed_at=str(item.get("pushed_at") or ""),
                stars=int(item.get("stargazers_count") or 0),
                is_archived=bool(item.get("archived", False)),
                is_fork=bool(item.get("fork", False)),
                clone_url=clone_url,
            ))
        if len(items) < 100:
            break
        page += 1
    return tuple(result)
