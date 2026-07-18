from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --- Auth ---
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    is_active: bool


# --- Members ---
class MemberCreate(BaseModel):
    git_email: str = ""
    git_name: str = ""
    real_name: str = ""
    department: str = ""


class MemberUpdate(BaseModel):
    git_email: Optional[str] = None
    git_name: Optional[str] = None
    real_name: Optional[str] = None
    department: Optional[str] = None


class MemberOut(BaseModel):
    id: int
    git_email: str
    git_name: str
    real_name: str
    department: str

    class Config:
        from_attributes = True


# --- Recipients ---
class RecipientCreate(BaseModel):
    email: str
    name: str = ""
    receive_daily: bool = True
    receive_weekly: bool = True
    receive_monthly: bool = True
    is_active: bool = True


class RecipientUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    receive_daily: Optional[bool] = None
    receive_weekly: Optional[bool] = None
    receive_monthly: Optional[bool] = None
    is_active: Optional[bool] = None


class RecipientOut(BaseModel):
    id: int
    email: str
    name: str
    receive_daily: bool
    receive_weekly: bool
    receive_monthly: bool
    is_active: bool

    class Config:
        from_attributes = True


# --- Schedules ---
class ScheduleCreate(BaseModel):
    report_type: str = "daily"
    run_time: str = "18:30"
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    timezone: str = "Asia/Shanghai"
    is_enabled: bool = True


class ScheduleUpdate(BaseModel):
    report_type: Optional[str] = None
    run_time: Optional[str] = None
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    timezone: Optional[str] = None
    is_enabled: Optional[bool] = None


class ScheduleOut(BaseModel):
    id: int
    report_type: str
    run_time: str
    day_of_week: Optional[int]
    day_of_month: Optional[int]
    timezone: str
    is_enabled: bool

    class Config:
        from_attributes = True


# --- Reports ---
class ReportTrigger(BaseModel):
    report_type: Literal["daily", "weekly", "monthly"] = "daily"
    repo_names: list[str] = Field(default_factory=list, description="指定仓库列表，空 = 全部")
    skip_fetch: bool = Field(True, description="跳过 git fetch，直接用本地缓存")
    snapshot_id: Optional[int] = Field(None, description="活跃项目筛选结果快照")
    activity_window: Optional[Literal["today", "this_week", "this_month"]] = Field(None, description="仓库活跃标签窗口")
    dry_run: bool = False


class ActiveRepositoriesRequest(BaseModel):
    report_type: Literal["daily", "weekly", "monthly"] = "daily"
    skip_fetch: bool = True
    activity_window: Optional[Literal["today", "this_week", "this_month"]] = None


class ReportOut(BaseModel):
    id: int
    org_name: str = ""
    report_type: str
    period_start: str
    period_end: str
    title: str
    total_commits: int
    status: str
    error: Optional[str]
    email_sent_at: Optional[str]
    created_at: str
    selection_snapshot_id: Optional[int] = None

    class Config:
        from_attributes = True


class ReportDetail(ReportOut):
    markdown: str
    html: str
    ai_analysis: str


class ReportStepOut(BaseModel):
    id: int
    run_id: int
    step_key: str
    step_name: str
    sequence: int
    status: str
    progress: int
    input_summary: dict = Field(default_factory=dict)
    output_summary: dict = Field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None


# --- Settings ---
class SettingsOut(BaseModel):
    timezone: str
    workspace: str
    subject_prefix: str
    ai_enabled: bool
    ai_model: str


class SettingsUpdate(BaseModel):
    timezone: Optional[str] = None
    workspace: Optional[str] = None
    subject_prefix: Optional[str] = None


# --- Proxy ---
class ProxyConfigOut(BaseModel):
    http_proxy: str
    https_proxy: str
    no_proxy: str
    enabled: bool
    updated_at: Optional[str] = None


class ProxyConfigUpdate(BaseModel):
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    no_proxy: Optional[str] = None
    enabled: Optional[bool] = None
