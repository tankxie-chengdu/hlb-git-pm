from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..db_models import User
from ..deps import get_current_user
from ..schemas import SettingsOut, SettingsUpdate

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
