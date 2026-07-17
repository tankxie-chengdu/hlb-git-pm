import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.periods import resolve_period


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

