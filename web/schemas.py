from __future__ import annotations

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
    display_name: str | None = None
    is_active: bool


# --- Members ---
class MemberCreate(BaseModel):
    git_email: str = ""
    git_name: str = ""
    real_name: str = ""
    department: str = ""


class MemberUpdate(BaseModel):
    git_email: str | None = None
    git_name: str | None = None
    real_name: str | None = None
    department: str | None = None


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
    email: str | None = None
    name: str | None = None
    receive_daily: bool | None = None
    receive_weekly: bool | None = None
    receive_monthly: bool | None = None
    is_active: bool | None = None


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
    day_of_week: int | None = None
    day_of_month: int | None = None
    timezone: str = "Asia/Shanghai"
    is_enabled: bool = True


class ScheduleUpdate(BaseModel):
    report_type: str | None = None
    run_time: str | None = None
    day_of_week: int | None = None
    day_of_month: int | None = None
    timezone: str | None = None
    is_enabled: bool | None = None


class ScheduleOut(BaseModel):
    id: int
    report_type: str
    run_time: str
    day_of_week: int | None
    day_of_month: int | None
    timezone: str
    is_enabled: bool

    class Config:
        from_attributes = True


# --- Reports ---
class ReportTrigger(BaseModel):
    report_type: str = "daily"
    start_date: str = Field(..., description="ISO date YYYY-MM-DD")
    end_date: str | None = None
    repo_names: list[str] = Field(default_factory=list, description="指定仓库列表，空 = 全部")
    skip_fetch: bool = Field(False, description="跳过 git fetch，直接用本地缓存")
    dry_run: bool = False


class ReportOut(BaseModel):
    id: int
    org_name: str = ""
    report_type: str
    period_start: str
    period_end: str
    title: str
    total_commits: int
    status: str
    error: str | None
    email_sent_at: str | None
    created_at: str

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
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None


# --- Settings ---
class SettingsOut(BaseModel):
    timezone: str
    workspace: str
    subject_prefix: str
    ai_enabled: bool
    ai_model: str


class SettingsUpdate(BaseModel):
    timezone: str | None = None
    workspace: str | None = None
    subject_prefix: str | None = None
