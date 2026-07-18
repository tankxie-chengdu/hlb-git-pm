from datetime import datetime, timezone
import unittest

from app.ai import fallback_analysis
from app.models import Commit, DailyReport, PeriodReport, RepositoryReport
from app.ai import context_commit_count
from app.report import refresh_ai_section_html, render_html, render_markdown, render_period_markdown


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

    def test_html_renders_ai_markdown_as_html(self):
        report = DailyReport(
            "2026-07-15",
            datetime.now(timezone.utc),
            [RepositoryReport("demo", "main")],
        )
        report.ai_analysis = "### 重点\n\n- **完成** 登录流程"
        html = render_html(report)
        self.assertIn("<h3>重点</h3>", html)
        self.assertIn("<strong>完成</strong>", html)
        self.assertNotIn("### 重点", html)
        report.ai_analysis += "\n<script>alert(1)</script>"
        self.assertNotIn("<script>", render_html(report))

    def test_refresh_ai_section_repairs_saved_html(self):
        old_html = '<section style="x"><h2>1. 执行摘要</h2>### 旧格式<br></section>'
        repaired = refresh_ai_section_html(old_html, "### 新格式\n\n- **完成**")
        self.assertIn("<h3>新格式</h3>", repaired)
        self.assertNotIn("### 新格式", repaired)

    def test_trend_uses_committer_time_when_available(self):
        commit = Commit(
            "demo",
            "abcdef123",
            "Alice",
            "alice@example.com",
            datetime(2026, 6, 24, tzinfo=timezone.utc),
            "merged change",
            1,
            1,
            0,
            datetime(2026, 7, 7, tzinfo=timezone.utc),
        )
        report = PeriodReport("weekly", "2026-07-06", "2026-07-12", datetime.now(timezone.utc), [RepositoryReport("demo", "main", [commit])])
        self.assertEqual(report.daily_trend[0]["date"], "2026-07-07")

    def test_ai_context_reports_omitted_commit_count(self):
        commits = [
            Commit("demo", str(index), "Alice", "alice@example.com", datetime.now(timezone.utc), str(index))
            for index in range(3)
        ]
        report = PeriodReport("weekly", "2026-07-06", "2026-07-12", datetime.now(timezone.utc), [RepositoryReport("demo", "main", commits)])
        self.assertEqual(context_commit_count(report, 2), 2)
