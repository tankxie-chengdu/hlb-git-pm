import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.periods import format_report_title, resolve_period


class PeriodTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 17, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    def test_daily_is_yesterday(self):
        start, end = resolve_period("daily", "Asia/Shanghai", self.now)
        self.assertEqual(start.isoformat(), "2026-07-16")
        self.assertEqual(end, start)

    def test_weekly_is_previous_calendar_week(self):
        start, end = resolve_period("weekly", "Asia/Shanghai", self.now)
        self.assertEqual(start.isoformat(), "2026-07-06")
        self.assertEqual(end.isoformat(), "2026-07-12")

    def test_monthly_is_previous_calendar_month(self):
        start, end = resolve_period("monthly", "Asia/Shanghai", self.now)
        self.assertEqual(start.isoformat(), "2026-06-01")
        self.assertEqual(end.isoformat(), "2026-06-30")

    def test_explicit_periods_are_used(self):
        self.assertEqual(
            resolve_period("daily", "Asia/Shanghai", self.now, date(2026, 7, 2), date(2026, 7, 2)),
            (date(2026, 7, 2), date(2026, 7, 2)),
        )
        self.assertEqual(
            resolve_period("weekly", "Asia/Shanghai", self.now, date(2026, 7, 1), date(2026, 7, 5)),
            (date(2026, 7, 1), date(2026, 7, 5)),
        )
        self.assertEqual(
            resolve_period("monthly", "Asia/Shanghai", self.now, date(2026, 6, 1), date(2026, 6, 30)),
            (date(2026, 6, 1), date(2026, 6, 30)),
        )

    def test_yearly_is_2026_to_today(self):
        self.assertEqual(
            resolve_period("yearly", "Asia/Shanghai", self.now),
            (date(2026, 1, 1), date(2026, 7, 17)),
        )

    def test_invalid_explicit_period_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "日报只能选择一天"):
            resolve_period("daily", "Asia/Shanghai", self.now, date(2026, 7, 1), date(2026, 7, 2))

    def test_report_titles_use_chinese_period_format(self):
        self.assertEqual(
            format_report_title("daily", date(2026, 7, 17), date(2026, 7, 17)),
            "WeFi-HLB 开发日报（2026 年07 月17 日）",
        )
        self.assertEqual(
            format_report_title("weekly", date(2026, 7, 6), date(2026, 7, 12)),
            "WeFi-HLB 开发周报（2026年07 月第 2 周）",
        )
        self.assertEqual(
            format_report_title("monthly", date(2026, 7, 1), date(2026, 7, 31)),
            "WeFi-HLB 开发月报（2026年07 月）",
        )
