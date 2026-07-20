from datetime import datetime, timezone
import unittest

from app.ai import fallback_analysis
from app.models import Commit, DailyReport, MemberInfo, PeriodReport, RepositoryReport
from app.ai import context_commit_count
from app.report import refresh_ai_section_html, render_html, render_markdown, render_period_html, render_period_markdown


class ReportTests(unittest.TestCase):
    def test_report_totals_and_markdown(self):
        commit = Commit("demo", "abcdef123", "Alice", "alice@example.com", datetime.now(timezone.utc), "fix login", 2, 10, 3)
        report = DailyReport("2026-07-15", datetime.now(timezone.utc), [RepositoryReport("demo", "main", [commit])])
        report.ai_analysis = fallback_analysis(report)
        markdown = render_markdown(report)
        self.assertEqual(report.total_commits, 1)
        self.assertEqual(report.total_additions, 10)
        self.assertIn("# WeFi-HLB 开发日报（2026 年07 月15 日）", markdown)
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
        self.assertIn("## 3. 项目维度", markdown)
        self.assertIn("## 4. 人员维度", markdown)
        self.assertIn("## 5. 活动趋势", markdown)
        self.assertIn("## 6. 项目贡献明细", markdown)
        self.assertIn("活跃", markdown)
        self.assertIn("Alice", markdown)
        self.assertIn("+10/-3", markdown)

    def test_dimension_tables_keep_only_compact_columns(self):
        commit = Commit("demo", "abcdef123", "Alice", "alice@example.com", datetime.now(timezone.utc), "feature", 2, 10, 3)
        report = PeriodReport(
            "weekly",
            "2026-07-13",
            "2026-07-19",
            datetime.now(timezone.utc),
            [RepositoryReport("demo", "all branches", [commit])],
            member_mapping={"alice@example.com": MemberInfo("alice(艾丽丝)", "研发")},
        )

        markdown = render_period_markdown(report)
        html = render_period_html(report)
        self.assertIn("| 项目 | 提交 | 贡献者 | 文件 | 代码变更 | 人员贡献 | 综合分析 |", markdown)
        self.assertIn("| 人员 | 提交 | 活跃天数 | 项目数 | 文件 | 代码变更 | 项目贡献 |", markdown)
        self.assertNotIn("| 项目 | 状态 |", markdown)
        self.assertNotIn("| 人员 | 部门 |", markdown)
        self.assertNotIn("最近提交", markdown)
        self.assertNotIn("<th align=\"left\">状态</th>", html)
        self.assertNotIn("<th align=\"left\">部门</th>", html)
        self.assertNotIn(">最近提交</th>", html)

    def test_project_analysis_is_rendered_as_compact_column(self):
        commit = Commit("demo", "abc", "Alice", "alice@example.com", datetime.now(timezone.utc), "feature", 2, 10, 3)
        report = PeriodReport(
            "weekly",
            "2026-07-13",
            "2026-07-19",
            datetime.now(timezone.utc),
            [RepositoryReport("demo", "all branches", [commit])],
            project_analyses=[{
                "repository": "demo",
                "work_summary": "开发登录功能并补充测试。",
                "quality_signal": "变更集中，暂未发现回滚信号。",
                "quality_level": "稳定",
                "evidence": ["1 次提交", "新增 10 行"],
                "confidence": "中",
            }],
        )

        markdown = render_period_markdown(report)
        html = render_period_html(report)
        self.assertIn("工作：开发登录功能并补充测试。", markdown)
        self.assertIn("质量（稳定）：变更集中，暂未发现回滚信号。", markdown)
        self.assertIn("<th align=\"left\">综合分析</th>", html)
        self.assertIn("查看依据", html)

    def test_report_uses_short_repository_names_and_embeds_trend_chart(self):
        commit = Commit("WeFi-HLB/demo", "abc", "Alice", "alice@example.com", datetime.now(timezone.utc), "feature")
        report = PeriodReport(
            "weekly", "2026-07-13", "2026-07-19", datetime.now(timezone.utc),
            [RepositoryReport("WeFi-HLB/demo", "main", [commit])],
            project_analyses=[{"repository": "WeFi-HLB/demo", "work_summary": "开发功能", "quality_signal": "证据不足", "quality_level": "证据不足", "evidence": [], "confidence": "低"}],
            organization="WeFi-HLB",
            trend_chart_png=b"png",
        )
        markdown = render_period_markdown(report)
        html = render_period_html(report)
        self.assertIn("| demo |", markdown)
        self.assertNotIn("WeFi-HLB/demo", markdown)
        self.assertIn("src=\"cid:trend-chart\"", html)
        self.assertIn("<h3>demo", html)

    def test_outsourced_names_are_blue_in_html_only(self):
        commit = Commit("demo", "abc", "v_alice", "v_alice@example.com", datetime.now(timezone.utc), "feature", 1, 2, 1)
        report = PeriodReport(
            "weekly",
            "2026-07-13",
            "2026-07-19",
            datetime.now(timezone.utc),
            [RepositoryReport("demo", "all branches", [commit])],
            member_mapping={"v_alice@example.com": MemberInfo("v_alice(艾丽丝)")},
        )

        markdown = render_period_markdown(report)
        html = render_period_html(report)
        blue_name = '<span style="color:#2563eb;font-weight:600">v_alice(艾丽丝)</span>'
        self.assertIn(blue_name, html)
        self.assertIn("v_alice(艾丽丝)", markdown)
        self.assertNotIn("<span", markdown)

    def test_project_and_person_dimensions_use_member_mapping_and_include_zero_activity_people(self):
        commit = Commit("demo", "abc", "alice", "alice@work.local", datetime(2026, 7, 16, tzinfo=timezone.utc), "feature", 2, 10, 1)
        report = PeriodReport(
            "weekly",
            "2026-07-13",
            "2026-07-19",
            datetime.now(timezone.utc),
            [RepositoryReport("demo", "all branches", [commit])],
            member_mapping={
                "alice": MemberInfo("alice(艾丽丝)", "研发"),
                "bob": MemberInfo("bob(鲍勃)", "研发"),
            },
        )
        self.assertEqual(report.project_contributions[0]["contributors"][0]["name"], "alice(艾丽丝)")
        people = {row["name"]: row for row in report.person_contributions}
        self.assertEqual(people["alice(艾丽丝)"]["commit_count"], 1)
        self.assertEqual(people["bob(鲍勃)"]["commit_count"], 0)
        markdown = render_period_markdown(report)
        self.assertIn("alice(艾丽丝)", markdown)
        self.assertIn("bob(鲍勃)", markdown)

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
