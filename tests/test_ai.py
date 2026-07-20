import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.ai import analyze, build_context, build_prompt, parse_analysis_response
from app.config import AiConfig
from app.models import Commit, DailyReport, MemberInfo, PeriodReport, RepositoryReport


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class AiTests(unittest.TestCase):
    def test_zai_thinking_flag_is_sent(self):
        config = AiConfig(
            base_url="https://api.z.ai/api/coding/paas/v4",
            api_key="test-key",
            model="glm-5.2",
            thinking_enabled=False,
        )
        response = _Response({"choices": [{"message": {"content": "分析完成"}}]})
        with patch("app.ai.urllib.request.urlopen", return_value=response) as request:
            result = analyze(DailyReport("2026-07-15", datetime.now(timezone.utc), []), config)
        body = json.loads(request.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(result, "分析完成")
        self.assertEqual(body["thinking"], {"type": "disabled"})

    def test_empty_content_falls_back_instead_of_returning_blank(self):
        config = AiConfig(api_key="test-key", thinking_enabled=False)
        response = _Response({"choices": [{"message": {"content": "", "reasoning_content": "..."}}]})
        with patch("app.ai.urllib.request.urlopen", return_value=response):
            result = analyze(DailyReport("2026-07-15", datetime.now(timezone.utc), []), config)
        self.assertIn("AI 返回空正文", result)

    def test_explicit_prompt_is_the_prompt_sent_to_model(self):
        config = AiConfig(api_key="test-key", thinking_enabled=False)
        response = _Response({"choices": [{"message": {"content": "分析完成"}}]})
        prompt = "这是本次报告的完整用户提示词。"
        with patch("app.ai.urllib.request.urlopen", return_value=response) as request:
            result = analyze(DailyReport("2026-07-15", datetime.now(timezone.utc), []), config, prompt=prompt)
        body = json.loads(request.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(result, "分析完成")
        self.assertEqual(body["messages"][1], {"role": "user", "content": prompt})

    def test_yearly_prompt_contains_project_and_person_dimensions(self):
        commit = Commit("demo", "abc", "Alice", "alice@example.com", datetime(2026, 7, 15, tzinfo=timezone.utc), "feature")
        report = PeriodReport(
            "yearly", "2026-01-01", "2026-07-20", datetime.now(timezone.utc),
            [RepositoryReport("demo", "all branches", [commit])],
            member_mapping={"alice@example.com": MemberInfo("alice(艾丽丝)")},
        )
        prompt = build_prompt(report, 80)
        self.assertIn("Git 年报", prompt)
        self.assertIn("项目维度贡献", prompt)
        self.assertIn("人员维度贡献", prompt)
        self.assertIn("alice(艾丽丝)", prompt)
        self.assertIn('"project_analyses"', prompt)

    def test_commit_context_is_sampled_across_projects(self):
        first = RepositoryReport(
            "first",
            "all branches",
            [Commit("first", str(index), "Alice", "alice@example.com", datetime.now(timezone.utc), f"first-{index}") for index in range(3)],
        )
        second = RepositoryReport(
            "second",
            "all branches",
            [Commit("second", str(index), "Bob", "bob@example.com", datetime.now(timezone.utc), f"second-{index}") for index in range(3)],
        )
        report = PeriodReport("weekly", "2026-07-13", "2026-07-19", datetime.now(timezone.utc), [first, second])
        context = build_context(report, 2)
        self.assertIn("first-0", context)
        self.assertIn("second-0", context)
        self.assertNotIn("first-1", context)

    def test_structured_analysis_is_validated_and_completed(self):
        report = PeriodReport(
            "weekly",
            "2026-07-13",
            "2026-07-19",
            datetime.now(timezone.utc),
            [RepositoryReport("demo", "all branches")],
        )
        response = json.dumps({
            "analysis_markdown": "### 执行摘要\n\n正常",
            "project_analyses": [{
                "repository": "demo",
                "work_summary": "开发功能",
                "quality_signal": "证据有限",
                "quality_level": "证据不足",
                "evidence": ["0 次提交"],
                "confidence": "低",
            }],
        }, ensure_ascii=False)
        analysis, projects, structured = parse_analysis_response(response, report)
        self.assertTrue(structured)
        self.assertEqual(analysis, "### 执行摘要\n\n正常")
        self.assertEqual(projects[0]["repository"], "demo")
        self.assertEqual(projects[0]["quality_level"], "证据不足")

    def test_unstructured_analysis_falls_back_without_losing_text(self):
        report = PeriodReport(
            "weekly", "2026-07-13", "2026-07-19", datetime.now(timezone.utc),
            [RepositoryReport("demo", "all branches")],
        )
        analysis, projects, structured = parse_analysis_response("普通 Markdown", report)
        self.assertFalse(structured)
        self.assertEqual(analysis, "普通 Markdown")
        self.assertEqual(projects[0]["quality_level"], "证据不足")

    def test_subjective_quality_language_is_downgraded(self):
        report = PeriodReport(
            "weekly", "2026-07-13", "2026-07-19", datetime.now(timezone.utc),
            [RepositoryReport("demo", "all branches")],
        )
        response = json.dumps({
            "analysis_markdown": "分析",
            "project_analyses": [{
                "repository": "demo",
                "work_summary": "开发功能",
                "quality_signal": "提交说明专业，代码很健康。",
                "quality_level": "稳定",
                "evidence": ["1 次提交"],
                "confidence": "高",
            }],
        }, ensure_ascii=False)
        _, projects, _ = parse_analysis_response(response, report)
        self.assertEqual(projects[0]["quality_level"], "证据不足")
        self.assertEqual(projects[0]["confidence"], "低")
        self.assertIn("已降级", projects[0]["quality_signal"])
