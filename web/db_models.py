from __future__ import annotations

from sqlalchemy import Boolean, Column, Integer, String, Text, UniqueConstraint

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    display_name = Column(String, nullable=True, default="")
    is_active = Column(Boolean, nullable=False, default=True)


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    git_email = Column(String, nullable=False, default="", index=True)
    git_name = Column(String, nullable=False, default="")
    real_name = Column(String, nullable=False, default="")
    department = Column(String, nullable=False, default="")


class Recipient(Base):
    __tablename__ = "recipients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False, default="")
    receive_daily = Column(Boolean, nullable=False, default=True)
    receive_weekly = Column(Boolean, nullable=False, default=True)
    receive_monthly = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String, nullable=False, default="daily")  # daily / weekly / monthly
    run_time = Column(String, nullable=False, default="18:30")  # HH:MM
    day_of_week = Column(Integer, nullable=True)  # 0-6, for weekly
    day_of_month = Column(Integer, nullable=True)  # 1-28, for monthly
    timezone = Column(String, nullable=False, default="Asia/Shanghai")
    is_enabled = Column(Boolean, nullable=False, default=True)


class ReportHistory(Base):
    __tablename__ = "report_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_name = Column(String, nullable=False, default="")   # e.g. "WeFi-HLB"
    report_type = Column(String, nullable=False, default="daily")
    period_start = Column(String, nullable=False)
    period_end = Column(String, nullable=False)
    title = Column(String, nullable=False, default="")
    markdown = Column(Text, nullable=False, default="")
    html = Column(Text, nullable=False, default="")
    ai_analysis = Column(Text, nullable=False, default="")
    total_commits = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="running")
    error = Column(Text, nullable=True)
    email_sent_at = Column(String, nullable=True)
    created_at = Column(String, nullable=False)
    selection_snapshot_id = Column(Integer, nullable=True, index=True)


class ReportStep(Base):
    """One observable stage in a report run."""
    __tablename__ = "report_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False, index=True)
    step_key = Column(String, nullable=False)
    step_name = Column(String, nullable=False, default="")
    sequence = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="pending")
    progress = Column(Integer, nullable=False, default=0)
    input_summary = Column(Text, nullable=False, default="{}")
    output_summary = Column(Text, nullable=False, default="{}")
    error = Column(Text, nullable=True)
    started_at = Column(String, nullable=True)
    finished_at = Column(String, nullable=True)
    duration_ms = Column(Integer, nullable=True)


class ReportSelectionSnapshot(Base):
    """Repository scan results captured by the active-project filter."""
    __tablename__ = "report_selection_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String, nullable=False, index=True)
    period_start = Column(String, nullable=False)
    period_end = Column(String, nullable=False)
    repositories_json = Column(Text, nullable=False, default="[]")
    created_at = Column(String, nullable=False)


class Repository(Base):
    """Cached repository metadata — populated from GitHub API and local git stats."""
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_name = Column(String, nullable=False, default="", index=True)
    full_name = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=False, default="")
    language = Column(String, nullable=False, default="")
    default_branch = Column(String, nullable=False, default="main")
    pushed_at = Column(String, nullable=False, default="")
    stars = Column(Integer, nullable=False, default=0)
    is_archived = Column(Boolean, nullable=False, default=False)
    is_fork = Column(Boolean, nullable=False, default=False)
    clone_url = Column(String, nullable=False, default="")
    is_cloned = Column(Boolean, nullable=False, default=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    branch_count = Column(Integer, nullable=False, default=0)
    total_commits = Column(Integer, nullable=False, default=0)
    synced_at = Column(String, nullable=False, default="")        # last git sync time
    meta_updated_at = Column(String, nullable=False, default="")  # last GitHub API refresh time


class ContributorStat(Base):
    """Per-author per-repo commit statistics, refreshed on every sync."""
    __tablename__ = "contributor_stats"
    __table_args__ = (
        UniqueConstraint("repo_name", "git_email", name="uq_contributor_repo_email"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_name = Column(String, nullable=False, default="", index=True)  # e.g. "WeFi-HLB"
    repo_name = Column(String, nullable=False, index=True)
    git_email = Column(String, nullable=False, index=True)
    git_name = Column(String, nullable=False, default="")
    commit_count = Column(Integer, nullable=False, default=0)
    first_commit_at = Column(String, nullable=False, default="")
    last_commit_at = Column(String, nullable=False, default="")
    synced_at = Column(String, nullable=False, default="")


class SyncJob(Base):
    """Track repository sync job status for UI display."""
    __tablename__ = "sync_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_name = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="queued")  # queued, syncing, done, failed
    error = Column(String, nullable=False, default="")
    started_at = Column(String, nullable=False, default="")
    finished_at = Column(String, nullable=False, default="")
