from datetime import datetime, timezone
import unittest

from app.ai import fallback_analysis
from app.models import Commit, DailyReport, PeriodReport, RepositoryReport
from app.report import render_markdown, render_period_markdown


class ReportTests(unittest.TestCase):
    def test_report_totals_and_markdown(self):
        commit = Commit("demo", "abcdef123", "Alice", "alice@example.com", datetime.now(timezone.utc), "fix login", 2, 10, 3)
        report = DailyReport("2026-07-15", datetime.now(timezone.utc), [RepositoryReport("demo", "main", [commit])])
        report.ai_analysis = fallback_analysis(report)
        markdown = render_markdown(report)
        self.assertEqual(report.total_commits, 1)
        self.assertEqual(report.total_additions, 10)
        self.assertIn("+10/-3", markdown)
        self.assertIn("fix login", markdown)

    def test_empty_report_has_fallback_message(self):
        report = DailyReport("2026-07-15", datetime.now(timezone.utc), [RepositoryReport("demo", "main")])
        self.assertIn("没有捕获到提交", fallback_analysis(report))

    def test_period_template_contains_macro_and_repository_sections(self):
        first = Commit("demo", "abcdef123", "Alice", "alice@example.com", datetime(2026, 7, 15, tzinfo=timezone.utc), "feature one", 2, 10, 3)
        second = Commit("demo", "123456789", "Bob", "bob@example.com", datetime(2026, 7, 16, tzinfo=timezone.utc), "feature two", 1, 4, 1)
        report = PeriodReport(
            "weekly",
            "2026-07-13",
            "2026-07-19",
            datetime.now(timezone.utc),
            [RepositoryReport("demo", "all branches", [first, second])],
            "本周期完成两个主题。",
        )
        markdown = render_period_markdown(report)
        self.assertIn("## 2. 宏观概览", markdown)
        self.assertIn("## 3. 活动趋势", markdown)
        self.assertIn("## 4. 仓库活动分布", markdown)
        self.assertIn("## 5. 人员协作概览", markdown)
        self.assertIn("## 6. 仓库详情", markdown)
        self.assertIn("活跃", markdown)
        self.assertIn("Alice", markdown)
        self.assertIn("+10/-3", markdown)
