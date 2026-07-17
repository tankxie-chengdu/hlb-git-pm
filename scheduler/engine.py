from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.periods import resolve_period

logger = logging.getLogger("hlb-git-pm.scheduler")

_scheduler: BackgroundScheduler | None = None
_app_config = None


def _compute_date_range(report_type: str, timezone: str) -> tuple[date, date]:
    return resolve_period(report_type, timezone)


def _execute_scheduled_report(report_type: str, timezone: str) -> None:
    if _app_config is None:
        logger.error("App config not loaded, skipping scheduled report")
        return

    from web.database import get_session
    from web.db_models import Member, Recipient, ReportHistory
    from app.main import run_once
    from app.models import MemberInfo

    start_date, end_date = _compute_date_range(report_type, timezone)
    logger.info("执行定时 %s 报告: %s ~ %s", report_type, start_date, end_date)

    session = get_session()
    try:
        # Create history record
        record = ReportHistory(
            report_type=report_type,
            period_start=start_date.isoformat(),
            period_end=end_date.isoformat(),
            status="running",
            created_at=datetime.now().isoformat(),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        report_id = record.id
        from web.report_steps import DbWorkflowReporter
        workflow = DbWorkflowReporter(report_id)

        # Build member mapping
        members = session.query(Member).all()
        mapping: dict[str, MemberInfo] = {}
        for m in members:
            if m.git_email:
                mapping[m.git_email.lower()] = MemberInfo(real_name=m.real_name, department=m.department)
            if m.git_name:
                mapping[m.git_name] = MemberInfo(real_name=m.real_name, department=m.department)

        # Build recipient list
        recipients_query = session.query(Recipient).filter(Recipient.is_active == True)
        if report_type == "daily":
            recipients_query = recipients_query.filter(Recipient.receive_daily == True)
        elif report_type == "weekly":
            recipients_query = recipients_query.filter(Recipient.receive_weekly == True)
        elif report_type == "monthly":
            recipients_query = recipients_query.filter(Recipient.receive_monthly == True)
        recipient_emails = [r.email for r in recipients_query.all()]

        result = run_once(
            _app_config,
            start_date,
            end_date=end_date if end_date != start_date else None,
            report_type=report_type,
            recipients=recipient_emails if recipient_emails else None,
            member_mapping=mapping if mapping else None,
            workflow=workflow,
        )

        # Update record
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
            rec.title = f"{report_type} {start_date.isoformat()} ~ {end_date.isoformat()}"
            rec.status = "sent"
            rec.email_sent_at = datetime.now().isoformat()
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
            logger.info("定时 %s 报告完成: %d 次提交", report_type, result.total_commits)

    except Exception as e:
        logger.exception("定时 %s 报告失败: %s", report_type, e)
        try:
            if "workflow" in locals():
                workflow.fail("persist_report", str(e))
            rec = session.query(ReportHistory).filter(ReportHistory.id == report_id).first()
            if rec:
                rec.status = "failed"
                rec.error = str(e)[:2000]
                session.commit()
        except Exception:
            pass
    finally:
        session.close()


def sync_jobs() -> None:
    if _scheduler is None:
        return

    from web.database import get_session
    from web.db_models import Schedule

    session = get_session()
    try:
        schedules = session.query(Schedule).filter(Schedule.is_enabled == True).all()

        # Remove existing scheduled jobs (identified by our prefix)
        existing_jobs = _scheduler.get_jobs()
        for job in existing_jobs:
            if job.id.startswith("schedule_"):
                _scheduler.remove_job(job.id)

        # Add jobs from DB
        for sched in schedules:
            job_id = f"schedule_{sched.id}"
            hour, minute = sched.run_time.split(":", 1)

            if sched.report_type == "daily":
                trigger = CronTrigger(hour=int(hour), minute=int(minute), timezone=sched.timezone)
            elif sched.report_type == "weekly":
                dow = sched.day_of_week if sched.day_of_week is not None else 0
                trigger = CronTrigger(day_of_week=dow, hour=int(hour), minute=int(minute), timezone=sched.timezone)
            elif sched.report_type == "monthly":
                dom = sched.day_of_month if sched.day_of_month is not None else 1
                trigger = CronTrigger(day=dom, hour=int(hour), minute=int(minute), timezone=sched.timezone)
            else:
                continue

            _scheduler.add_job(
                _execute_scheduled_report,
                trigger=trigger,
                id=job_id,
                args=[sched.report_type, sched.timezone],
                replace_existing=True,
                misfire_grace_time=3600,
            )
            logger.info("已注册调度任务: %s (%s @ %s)", job_id, sched.report_type, sched.run_time)
    finally:
        session.close()


def init_scheduler(config) -> BackgroundScheduler:
    global _scheduler, _app_config
    _app_config = config
    _scheduler = BackgroundScheduler()
    _scheduler.start()
    sync_jobs()
    logger.info("APScheduler 已启动")
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("APScheduler 已停止")
