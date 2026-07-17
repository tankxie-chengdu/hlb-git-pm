from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db_models import ContributorStat, Member, Recipient, ReportHistory, Schedule, User
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    today = date.today()
    last_7 = (today - timedelta(days=6)).isoformat()
    last_30 = (today - timedelta(days=29)).isoformat()

    # --- 报告统计 ---
    total_reports = db.query(func.count(ReportHistory.id)).scalar() or 0
    reports_7d = (
        db.query(func.count(ReportHistory.id))
        .filter(ReportHistory.period_start >= last_7)
        .scalar()
        or 0
    )
    sent_count = (
        db.query(func.count(ReportHistory.id))
        .filter(ReportHistory.status == "sent")
        .scalar()
        or 0
    )
    failed_count = (
        db.query(func.count(ReportHistory.id))
        .filter(ReportHistory.status == "failed")
        .scalar()
        or 0
    )

    # 各类型数量
    type_rows = (
        db.query(ReportHistory.report_type, func.count(ReportHistory.id))
        .group_by(ReportHistory.report_type)
        .all()
    )
    by_type = {row[0]: row[1] for row in type_rows}

    # --- 提交统计 ---
    total_commits = (
        db.query(func.sum(ReportHistory.total_commits))
        .filter(ReportHistory.status.in_(["sent", "completed"]))
        .scalar()
        or 0
    )
    commits_7d = (
        db.query(func.sum(ReportHistory.total_commits))
        .filter(
            ReportHistory.period_start >= last_7,
            ReportHistory.status.in_(["sent", "completed"]),
        )
        .scalar()
        or 0
    )
    commits_30d = (
        db.query(func.sum(ReportHistory.total_commits))
        .filter(
            ReportHistory.period_start >= last_30,
            ReportHistory.status.in_(["sent", "completed"]),
        )
        .scalar()
        or 0
    )

    # --- 人员 / 收件人 ---
    member_count = db.query(func.count(Member.id)).scalar() or 0
    recipient_count = (
        db.query(func.count(Recipient.id)).filter(Recipient.is_active == True).scalar() or 0
    )
    active_schedule_count = (
        db.query(func.count(Schedule.id)).filter(Schedule.is_enabled == True).scalar() or 0
    )

    # --- 最近 30 天日报折线图 (每天 total_commits) ---
    daily_rows = (
        db.query(ReportHistory.period_start, func.sum(ReportHistory.total_commits))
        .filter(
            ReportHistory.report_type == "daily",
            ReportHistory.period_start >= last_30,
            ReportHistory.status.in_(["sent", "completed"]),
        )
        .group_by(ReportHistory.period_start)
        .order_by(ReportHistory.period_start)
        .all()
    )
    commit_trend = [{"date": r[0], "commits": int(r[1] or 0)} for r in daily_rows]

    # --- Top 5 贡献者 (from contributor_stats) ---
    top_contributors_rows = (
        db.query(
            ContributorStat.git_email,
            ContributorStat.git_name,
            func.sum(ContributorStat.commit_count).label("total"),
        )
        .group_by(ContributorStat.git_email, ContributorStat.git_name)
        .order_by(func.sum(ContributorStat.commit_count).desc())
        .limit(5)
        .all()
    )
    # Enrich with member real_name
    member_map = {
        m.git_email.lower(): m.real_name
        for m in db.query(Member).all()
        if m.git_email
    }
    top_contributors = [
        {
            "git_email": r[0],
            "git_name": r[1],
            "real_name": member_map.get(r[0].lower(), ""),
            "total_commits": int(r[2] or 0),
        }
        for r in top_contributors_rows
    ]

    # --- 最近 5 条报告 ---
    recent_reports = (
        db.query(ReportHistory)
        .order_by(ReportHistory.id.desc())
        .limit(5)
        .all()
    )
    recent_reports_data = [
        {
            "id": r.id,
            "report_type": r.report_type,
            "period_start": r.period_start,
            "period_end": r.period_end,
            "title": r.title,
            "total_commits": r.total_commits,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in recent_reports
    ]

    return {
        # 汇总卡片数据
        "total_reports": total_reports,
        "reports_7d": reports_7d,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "by_type": by_type,
        "total_commits": int(total_commits),
        "commits_7d": int(commits_7d),
        "commits_30d": int(commits_30d),
        "member_count": member_count,
        "recipient_count": recipient_count,
        "active_schedule_count": active_schedule_count,
        # 图表数据
        "commit_trend": commit_trend,
        "top_contributors": top_contributors,
        # 最近报告
        "recent_reports": recent_reports_data,
    }
