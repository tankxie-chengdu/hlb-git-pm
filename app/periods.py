from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


REPORT_TYPES = ("daily", "weekly", "monthly")


def resolve_period(report_type: str, timezone: str, now: datetime | None = None) -> tuple[date, date]:
    if report_type not in REPORT_TYPES:
        raise ValueError(f"不支持的报告类型: {report_type}")
    tz = ZoneInfo(timezone)
    today = (now or datetime.now(tz)).astimezone(tz).date() if now else datetime.now(tz).date()
    if report_type == "daily":
        target = today - timedelta(days=1)
        return target, target
    if report_type == "weekly":
        # Previous calendar week, Monday through Sunday.
        this_monday = today - timedelta(days=today.weekday())
        end = this_monday - timedelta(days=1)
        return end - timedelta(days=6), end
    # Previous calendar month.
    first_of_this_month = today.replace(day=1)
    end = first_of_this_month - timedelta(days=1)
    return end.replace(day=1), end

