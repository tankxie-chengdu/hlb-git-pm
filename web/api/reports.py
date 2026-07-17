from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db_models import Member, Recipient, ReportHistory, ReportStep, Repository, User
from ..deps import get_current_user, get_db
from ..schemas import ReportDetail, ReportOut, ReportStepOut, ReportTrigger

logger = logging.getLogger("hlb-git-pm.api.reports")

router = APIRouter(prefix="/reports", tags=["reports"])

# Reference to the loaded AppConfig; set by web.app at startup
_app_config = None


def set_app_config(config):
    global _app_config
    _app_config = config


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

    start = date.fromisoformat(body.start_date)
    end = date.fromisoformat(body.end_date) if body.end_date else start

    record = ReportHistory(
        org_name="",
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
            )

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
                rec.title = f"{report_type} {start.isoformat()} ~ {end.isoformat()}"
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
    send_email(email_cfg, subject, report.markdown, report.html)

    report.email_sent_at = datetime.now(timezone.utc).isoformat()
    report.status = "sent"
    db.commit()
    db.refresh(report)
    return report
