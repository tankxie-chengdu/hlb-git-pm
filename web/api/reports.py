from __future__ import annotations

import logging
import json
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db_models import Member, Recipient, ReportHistory, ReportSelectionSnapshot, ReportStep, Repository, User
from ..deps import get_current_user, get_db
from ..schemas import ActiveRepositoriesRequest, ReportDetail, ReportOut, ReportStepOut, ReportTrigger

logger = logging.getLogger("hlb-git-pm.api.reports")

# These ranges match the activity levels shown on the repository board.
# Ranges are (min_days_ago, max_days_ago), where max is exclusive.
ACTIVITY_WINDOWS = {
    "today": (0, 1),
    "this_week": (0, 7),
    "this_month": (0, 30),
}

router = APIRouter(prefix="/reports", tags=["reports"])

# Reference to the loaded AppConfig; set by web.app at startup
_app_config = None


def set_app_config(config):
    global _app_config
    _app_config = config


def _serialize_repository_reports(reports, *, include_empty: bool = False, activity_window: str | None = None) -> str:
    """Persist the complete scan result, including commit numstat data."""
    payload = [
            {
                "name": report.name,
                "branch": report.branch,
                "error": report.error,
                "commits": [
                    {
                        "repository": commit.repository,
                        "sha": commit.sha,
                        "author_name": commit.author_name,
                        "author_email": commit.author_email,
                        "authored_at": commit.authored_at.isoformat(),
                        "committed_at": commit.committed_at.isoformat() if commit.committed_at else None,
                        "subject": commit.subject,
                        "files_changed": commit.files_changed,
                        "additions": commit.additions,
                        "deletions": commit.deletions,
                    }
                    for commit in report.commits
                ],
            }
            for report in reports
        ]
    # A metadata envelope keeps this compatible with snapshots created before
    # activity-window filtering was introduced.
    return json.dumps(
        {"repositories": payload, "include_empty": include_empty, "activity_window": activity_window},
        ensure_ascii=False,
    )


def _deserialize_repository_reports(value: str) -> tuple[list, bool, str | None]:
    from app.models import Commit, RepositoryReport

    payload = json.loads(value or "[]")
    if isinstance(payload, dict):
        items = payload.get("repositories", [])
        include_empty = bool(payload.get("include_empty", False))
        activity_window = payload.get("activity_window")
    else:
        items = payload
        include_empty = False
        activity_window = None
    reports = []
    for item in items:
        commits = [
            Commit(
                repository=str(commit.get("repository") or item.get("name") or ""),
                sha=str(commit.get("sha") or ""),
                author_name=str(commit.get("author_name") or ""),
                author_email=str(commit.get("author_email") or ""),
                authored_at=datetime.fromisoformat(str(commit["authored_at"]).replace("Z", "+00:00")),
                subject=str(commit.get("subject") or ""),
                files_changed=int(commit.get("files_changed") or 0),
                additions=int(commit.get("additions") or 0),
                deletions=int(commit.get("deletions") or 0),
                committed_at=(
                    datetime.fromisoformat(str(commit["committed_at"]).replace("Z", "+00:00"))
                    if commit.get("committed_at") else None
                ),
            )
            for commit in item.get("commits", [])
        ]
        reports.append(RepositoryReport(str(item.get("name") or ""), str(item.get("branch") or "all branches"), commits, item.get("error")))
    return reports, include_empty, activity_window


def _in_activity_window(repo: Repository | None, window: str) -> bool:
    """Use the same pushed_at semantics as the repository board labels."""
    if repo is None or not repo.is_cloned or not repo.pushed_at:
        return False
    try:
        pushed_at = datetime.fromisoformat(repo.pushed_at.replace("Z", "+00:00"))
        if pushed_at.tzinfo is None:
            pushed_at = pushed_at.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - pushed_at).total_seconds()
        lower_days, upper_days = ACTIVITY_WINDOWS[window]
        age_days = age_seconds / 86400
        return lower_days <= age_days < upper_days
    except (TypeError, ValueError):
        return False


@router.get("", response_model=list[ReportOut])
def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    offset = (page - 1) * page_size
    return (
        db.query(ReportHistory)
        .order_by(ReportHistory.id.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )


@router.get("/repo-names")
def list_repo_names(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Return a lightweight list of repo names from the repositories table.

    Falls back to the static config list if the table is empty.
    """
    if _app_config is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="配置未加载")

    # Query from DB
    names = [r.full_name for r in db.query(Repository.full_name).all()]
    if names:
        return sorted(names)

    # Fall back to static config
    names = [r.name for r in _app_config.repositories]
    return sorted(names)


@router.post("/active-repositories")
def list_active_repositories(
    body: ActiveRepositoriesRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Scan the selected period and return only repositories with commits."""
    if _app_config is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="配置未加载")

    from app.github_app import discover_repositories
    from app.git_service import scan_repository
    from app.periods import resolve_period

    start, end = resolve_period(body.report_type, _app_config.timezone)
    repository_configs = list(_app_config.repositories)
    if _app_config.github:
        discovered = discover_repositories(_app_config.github)
        by_name = {repo.name: repo for repo in repository_configs}
        by_name.update({repo.name: repo for repo in discovered})
        repository_configs = list(by_name.values())

    if body.activity_window:
        repo_rows = {
            row.full_name: row
            for row in db.query(Repository).filter(Repository.is_deleted == False).all()
        }
        repository_configs = [
            config for config in repository_configs
            if _in_activity_window(repo_rows.get(config.name), body.activity_window)
        ]

    if body.skip_fetch:
        import dataclasses
        repository_configs = [dataclasses.replace(repo, fetch=False) for repo in repository_configs]

    workspace = Path(_app_config.workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    reports = [
        scan_repository(
            config,
            workspace,
            start,
            ZoneInfo(_app_config.timezone),
            end_date=end,
            allow_clone=not body.skip_fetch,
        )
        for config in repository_configs
    ]
    active = []
    failed = []
    for report in reports:
        if report.error:
            failed.append({"name": report.name, "error": report.error})
        elif report.commits or body.activity_window:
            active.append(
                {
                    "name": report.name,
                    "branch": report.branch,
                    "commits": len(report.commits),
                    "contributors": len({(c.author_email or c.author_name).lower() for c in report.commits}),
                    "additions": sum(c.additions for c in report.commits),
                    "deletions": sum(c.deletions for c in report.commits),
                    "last_commit_at": (
                        max((c.activity_at for c in report.commits), default=None).isoformat()
                        if report.commits else None
                    ),
                }
            )
    active.sort(key=lambda item: (-item["commits"], item["name"]))
    snapshot = ReportSelectionSnapshot(
        report_type=body.report_type,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        repositories_json=_serialize_repository_reports(
            reports,
            include_empty=bool(body.activity_window),
            activity_window=body.activity_window,
        ),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return {
        "report_type": body.report_type,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "scanned_repositories": len(reports),
        "active_repositories": active,
        "failed_repositories": failed,
        "snapshot_id": snapshot.id,
        "source": "local_cache" if body.skip_fetch else "synchronized",
        "activity_window": body.activity_window,
    }


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(report_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    report = db.query(ReportHistory).filter(ReportHistory.id == report_id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return report


@router.get("/{report_id}/steps", response_model=list[ReportStepOut])
def get_report_steps(report_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    report = db.query(ReportHistory.id).filter(ReportHistory.id == report_id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    rows = db.query(ReportStep).filter(ReportStep.run_id == report_id).order_by(ReportStep.sequence).all()
    result = []
    import json
    for row in rows:
        result.append(
            ReportStepOut(
                id=row.id,
                run_id=row.run_id,
                step_key=row.step_key,
                step_name=row.step_name,
                sequence=row.sequence,
                status=row.status,
                progress=row.progress,
                input_summary=json.loads(row.input_summary or "{}"),
                output_summary=json.loads(row.output_summary or "{}"),
                error=row.error,
                started_at=row.started_at,
                finished_at=row.finished_at,
                duration_ms=row.duration_ms,
            )
        )
    return result


@router.post("/trigger", response_model=ReportOut, status_code=status.HTTP_202_ACCEPTED)
def trigger_report(body: ReportTrigger, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    if _app_config is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="配置未加载")

    from app.periods import resolve_period
    start, end = resolve_period(body.report_type, _app_config.timezone)

    snapshot_repositories = None
    snapshot_include_empty = False
    if body.snapshot_id is not None:
        snapshot = db.query(ReportSelectionSnapshot).filter(ReportSelectionSnapshot.id == body.snapshot_id).first()
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="活跃项目筛选结果不存在或已过期")
        if snapshot.report_type != body.report_type or snapshot.period_start != start.isoformat() or snapshot.period_end != end.isoformat():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="活跃项目筛选结果与当前报告周期不一致，请重新筛选")
        try:
            snapshot_repositories, snapshot_include_empty, snapshot_activity_window = _deserialize_repository_reports(snapshot.repositories_json)
            if snapshot_activity_window != body.activity_window:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仓库活跃筛选条件已变化，请重新筛选")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"活跃项目筛选结果无效: {error}") from error

    record = ReportHistory(
        org_name="",
        selection_snapshot_id=body.snapshot_id,
        report_type=body.report_type,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        status="running",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    report_id = record.id
    from web.report_steps import DbWorkflowReporter
    workflow = DbWorkflowReporter(report_id)
    config = _app_config
    dry_run = body.dry_run
    report_type = body.report_type
    repo_names = body.repo_names if body.repo_names else None
    skip_fetch = body.skip_fetch

    def _run():
        from web.database import get_session as _get_session
        session = _get_session()
        try:
            from app.main import run_once
            from app.models import MemberInfo

            run_config = config

            # Get total repository count from database
            total_repos_count = session.query(Repository).filter(Repository.is_deleted == False).count()

            # Build member mapping from DB
            members = session.query(Member).all()
            mapping: dict[str, MemberInfo] = {}
            for m in members:
                if m.git_email:
                    mapping[m.git_email.lower()] = MemberInfo(real_name=m.real_name, department=m.department)
                if m.git_name:
                    mapping[m.git_name] = MemberInfo(real_name=m.real_name, department=m.department)

            # Build recipient list from DB
            recipients_query = session.query(Recipient).filter(Recipient.is_active == True)
            if report_type == "daily":
                recipients_query = recipients_query.filter(Recipient.receive_daily == True)
            elif report_type == "weekly":
                recipients_query = recipients_query.filter(Recipient.receive_weekly == True)
            elif report_type == "monthly":
                recipients_query = recipients_query.filter(Recipient.receive_monthly == True)
            recipient_emails = [r.email for r in recipients_query.all()]

            result = run_once(
                run_config,
                start,
                end_date=end if end != start else None,
                report_type=report_type,
                recipients=recipient_emails if recipient_emails else None,
                member_mapping=mapping if mapping else None,
                repo_names=repo_names,
                skip_fetch=skip_fetch,
                dry_run=dry_run,
                workflow=workflow,
                snapshot_repositories=snapshot_repositories,
                snapshot_include_empty=snapshot_include_empty,
                snapshot_activity_window=body.activity_window,
                snapshot_id=body.snapshot_id,
            )

            # Set total repository count
            result.total_repositories_count = total_repos_count

            rec = session.query(ReportHistory).filter(ReportHistory.id == report_id).first()
            if rec:
                from app.report import render_markdown, render_html, render_period_markdown, render_period_html
                from app.models import PeriodReport

                if isinstance(result, PeriodReport):
                    rec.markdown = render_period_markdown(result)
                    rec.html = render_period_html(result)
                else:
                    rec.markdown = render_markdown(result)
                    rec.html = render_html(result)
                rec.ai_analysis = result.ai_analysis
                rec.total_commits = result.total_commits
                activity_label = {
                    "today": "今天活跃",
                    "this_week": "本周活跃",
                    "this_month": "本月活跃",
                }.get(body.activity_window)
                scope = f"（{activity_label}）" if activity_label else ""
                rec.title = f"{report_type}{scope} {start.isoformat()} ~ {end.isoformat()}"
                rec.status = "completed" if dry_run else "sent"
                if not dry_run and recipient_emails:
                    rec.email_sent_at = datetime.now(timezone.utc).isoformat()
                session.commit()
                workflow.start("persist_report", {"report_id": report_id})
                workflow.success(
                    "persist_report",
                    {
                        "report_id": report_id,
                        "status": rec.status,
                        "total_commits": rec.total_commits,
                        "email_sent": bool(rec.email_sent_at),
                        "selection_snapshot_id": rec.selection_snapshot_id,
                    },
                )
        except Exception as e:
            logger.exception("报告生成失败: %s", e)
            rec = session.query(ReportHistory).filter(ReportHistory.id == report_id).first()
            if rec:
                rec.status = "failed"
                rec.error = str(e)[:2000]
                session.commit()
            workflow.fail("persist_report", str(e))
        finally:
            session.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return record


@router.post("/{report_id}/resend", response_model=ReportOut)
def resend_report(report_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    if _app_config is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="配置未加载")

    report = db.query(ReportHistory).filter(ReportHistory.id == report_id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    if not report.html:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="报告内容为空")

    # Get recipients
    report_type = report.report_type
    recipients_query = db.query(Recipient).filter(Recipient.is_active == True)
    if report_type == "daily":
        recipients_query = recipients_query.filter(Recipient.receive_daily == True)
    elif report_type == "weekly":
        recipients_query = recipients_query.filter(Recipient.receive_weekly == True)
    elif report_type == "monthly":
        recipients_query = recipients_query.filter(Recipient.receive_monthly == True)
    recipient_emails = [r.email for r in recipients_query.all()]

    if not recipient_emails:
        recipient_emails = list(_app_config.email.recipients)
    if not recipient_emails:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可用的收件人")

    from app.emailer import send_email
    from app.report import refresh_ai_section_html
    from app.config import EmailConfig

    email_cfg = EmailConfig(
        host=_app_config.email.host,
        port=_app_config.email.port,
        username=_app_config.email.username,
        password=_app_config.email.password,
        sender=_app_config.email.sender,
        recipients=tuple(recipient_emails),
        use_tls=_app_config.email.use_tls,
        use_ssl=_app_config.email.use_ssl,
    )
    subject = report.title or f"报告重发 {report.period_start} ~ {report.period_end}"
    repaired_html = refresh_ai_section_html(report.html, report.ai_analysis)
    send_email(email_cfg, subject, report.markdown, repaired_html)

    report.email_sent_at = datetime.now(timezone.utc).isoformat()
    report.status = "sent"
    report.html = repaired_html
    db.commit()
    db.refresh(report)
    return report
