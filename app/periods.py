from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


REPORT_TYPES = ("daily", "weekly", "monthly", "yearly")


def format_report_title(report_type: str, period_start: date, period_end: date, organization: str = "WeFi-HLB") -> str:
    prefix = f"{organization} " if organization else ""
    if report_type == "daily":
        return f"{prefix}开发日报（{period_start.year} 年{period_start.month:02d} 月{period_start.day:02d} 日）"
    if report_type == "weekly":
        first_day = period_start.replace(day=1)
        week_number = ((period_start.day + first_day.weekday() - 1) // 7) + 1
        return f"{prefix}开发周报（{period_start.year}年{period_start.month:02d} 月第 {week_number} 周）"
    if report_type == "monthly":
        return f"{prefix}开发月报（{period_start.year}年{period_start.month:02d} 月）"
    if report_type == "yearly":
        return f"{prefix}开发年报（{period_start.year} 年）"
    return f"{prefix}{report_type}（{period_start.isoformat()} ~ {period_end.isoformat()}）"


def _month_end(value: date) -> date:
    first_next = value.replace(year=value.year + 1, month=1, day=1) if value.month == 12 else value.replace(month=value.month + 1, day=1)
    return first_next - timedelta(days=1)


def resolve_period(
    report_type: str,
    timezone: str,
    now: datetime | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> tuple[date, date]:
    if report_type not in REPORT_TYPES:
        raise ValueError(f"不支持的报告类型: {report_type}")
    tz = ZoneInfo(timezone)
    today = (now or datetime.now(tz)).astimezone(tz).date() if now else datetime.now(tz).date()
    if report_type == "yearly":
        return date(2026, 1, 1), today
    if period_start is not None or period_end is not None:
        if period_start is None or period_end is None:
            raise ValueError("必须同时提供周期开始和结束日期")
        if period_start > period_end:
            raise ValueError("周期开始日期不能晚于结束日期")
        if period_end > today:
            raise ValueError("不能生成未来周期的报告")
        days = (period_end - period_start).days + 1
        if report_type == "daily" and days != 1:
            raise ValueError("日报只能选择一天")
        if report_type == "weekly" and (days > 7 or (period_start.year, period_start.month) != (period_end.year, period_end.month)):
            raise ValueError("周报必须选择同一自然月内不超过 7 天的周区间")
        if report_type == "weekly":
            if period_start.day != 1 and period_start.weekday() != 0:
                raise ValueError("周报区间必须从月初或周一开始")
            days_to_sunday = 6 - period_start.weekday()
            expected_end = min(period_start + timedelta(days=days_to_sunday), _month_end(period_start), today)
            if period_end != expected_end:
                raise ValueError("周报结束日期必须是周日、月末或今天")
        if report_type == "monthly" and period_start.day != 1:
            raise ValueError("月报必须从当月 1 日开始")
        if report_type == "monthly" and (period_start.year, period_start.month) != (period_end.year, period_end.month):
            raise ValueError("月报起止日期必须属于同一个月")
        if report_type == "monthly" and period_end != min(_month_end(period_start), today):
            raise ValueError("月报结束日期必须是月末或今天")
        return period_start, period_end
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
