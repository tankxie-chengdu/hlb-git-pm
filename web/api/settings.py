from __future__ import annotations

from datetime import datetime, timezone as _tz
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db_models import User, ProxyConfig
from ..deps import get_current_user, get_db
from ..schemas import SettingsOut, SettingsUpdate, ProxyConfigOut, ProxyConfigUpdate

router = APIRouter(prefix="/settings", tags=["settings"])

# Reference to AppConfig; set by web.app at startup
_app_config = None


def set_app_config(config):
    global _app_config
    _app_config = config


@router.get("", response_model=SettingsOut)
def get_settings(_user: User = Depends(get_current_user)):
    if _app_config is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="配置未加载")
    return SettingsOut(
        timezone=_app_config.timezone,
        workspace=_app_config.workspace,
        subject_prefix=_app_config.subject_prefix,
        ai_enabled=_app_config.ai.enabled,
        ai_model=_app_config.ai.model,
    )


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, _user: User = Depends(get_current_user)):
    if _app_config is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="配置未加载")
    # Settings from config.toml are frozen dataclasses — read-only view.
    # This endpoint currently returns the current state; to change infrastructure
    # settings, edit config.toml and restart.
    return SettingsOut(
        timezone=body.timezone or _app_config.timezone,
        workspace=body.workspace or _app_config.workspace,
        subject_prefix=body.subject_prefix or _app_config.subject_prefix,
        ai_enabled=_app_config.ai.enabled,
        ai_model=_app_config.ai.model,
    )


def _ensure_proxy_config_exists(db: Session) -> ProxyConfig:
    """Ensure there's at least one proxy config record."""
    existing = db.query(ProxyConfig).first()
    if existing:
        return existing

    now = datetime.now(_tz.utc).isoformat()
    config = ProxyConfig(
        http_proxy="",
        https_proxy="",
        no_proxy="",
        enabled=False,
        updated_at=now,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.get("/proxy", response_model=ProxyConfigOut)
def get_proxy_config(_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get current proxy configuration."""
    config = _ensure_proxy_config_exists(db)
    return ProxyConfigOut(
        http_proxy=config.http_proxy,
        https_proxy=config.https_proxy,
        no_proxy=config.no_proxy,
        enabled=config.enabled,
        updated_at=config.updated_at,
    )


@router.put("/proxy", response_model=ProxyConfigOut)
def update_proxy_config(body: ProxyConfigUpdate, _user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Update proxy configuration."""
    config = _ensure_proxy_config_exists(db)

    if body.http_proxy is not None:
        config.http_proxy = body.http_proxy
    if body.https_proxy is not None:
        config.https_proxy = body.https_proxy
    if body.no_proxy is not None:
        config.no_proxy = body.no_proxy
    if body.enabled is not None:
        config.enabled = body.enabled

    config.updated_at = datetime.now(_tz.utc).isoformat()
    db.commit()

    return ProxyConfigOut(
        http_proxy=config.http_proxy,
        https_proxy=config.https_proxy,
        no_proxy=config.no_proxy,
        enabled=config.enabled,
        updated_at=config.updated_at,
    )
