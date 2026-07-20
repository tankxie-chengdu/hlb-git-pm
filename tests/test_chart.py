import io
import unittest
from datetime import datetime, timezone

from PIL import Image

from app.chart import render_trend_chart, trend_points
from app.models import Commit, DailyReport, PeriodReport, RepositoryReport


class TrendChartTests(unittest.TestCase):
    def test_daily_chart_uses_hourly_points_and_is_non_blank(self):
        commits = [
            Commit("WeFi-HLB/demo", "a", "Alice", "alice@example.com", datetime(2026, 7, 17, 9, tzinfo=timezone.utc), "one"),
            Commit("WeFi-HLB/demo", "b", "Alice", "alice@example.com", datetime(2026, 7, 17, 9, 30, tzinfo=timezone.utc), "two"),
        ]
        report = DailyReport("2026-07-17", datetime.now(timezone.utc), [RepositoryReport("WeFi-HLB/demo", "main", commits)])
        points = trend_points(report)
        image_bytes = render_trend_chart(report)
        image = Image.open(io.BytesIO(image_bytes))
        self.assertEqual(len(points), 24)
        self.assertEqual(points[9]["commits"], 2)
        self.assertEqual(image.format, "PNG")
        self.assertGreater(len(image_bytes), 1000)
        self.assertGreater(len(image.convert("RGB").getcolors(maxcolors=1_000_000)), 2)

    def test_period_chart_uses_daily_points_and_empty_reports_have_no_image(self):
        report = PeriodReport("weekly", "2026-07-13", "2026-07-19", datetime.now(timezone.utc), [RepositoryReport("demo", "main")])
        self.assertEqual(len(trend_points(report)), 7)
        self.assertIsNone(render_trend_chart(report))
