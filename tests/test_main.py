import logging
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

from app.config import AiConfig, AppConfig, EmailConfig, RepositoryConfig
from app.models import RepositoryReport


class SchedulerFailureTests(unittest.TestCase):
    @patch("app.main.time_module.sleep")
    @patch("app.main.run_once")
    @patch("app.main._next_run")
    def test_logs_critical_after_3_failures(self, mock_next_run, mock_run_once, mock_sleep):
        tz = ZoneInfo("Asia/Shanghai")
        config = AppConfig(
            repositories=(RepositoryConfig(name="demo", path="/tmp/demo"),),
            email=EmailConfig(host="smtp.example.com", sender="a@b.com", recipients=("c@d.com",)),
        )

        call_count = 0

        def fake_next_run(cfg, timezone):
            nonlocal call_count
            call_count += 1
            if call_count > 4:
                raise KeyboardInterrupt("stop test loop")
            return datetime.now(timezone) + timedelta(seconds=1)

        mock_next_run.side_effect = fake_next_run
        mock_run_once.side_effect = RuntimeError("boom")

        from app.main import run_scheduler

        with self.assertLogs("git_daily_report", level="WARNING") as cm:
            try:
                run_scheduler(config)
            except KeyboardInterrupt:
                pass

        critical_msgs = [msg for msg in cm.output if "CRITICAL" in msg]
        self.assertTrue(len(critical_msgs) >= 1, f"Expected CRITICAL log, got: {cm.output}")
        self.assertTrue(any("连续失败" in msg for msg in critical_msgs))


class WorkflowTests(unittest.TestCase):
    @patch("app.main.render_markdown", return_value="markdown")
    @patch("app.main.render_html", return_value="<html></html>")
    @patch("app.main.analyze", return_value="analysis")
    @patch("app.main.scan_repository", return_value=RepositoryReport("demo", "all branches"))
    def test_run_once_reports_workflow_steps(self, _scan, _analyze, _html, _markdown):
        from datetime import date
        from app.main import run_once

        class Recorder:
            def __init__(self):
                self.events = []

            def start(self, key, value=None): self.events.append(("start", key, value))
            def progress(self, key, value): self.events.append(("progress", key, value))
            def success(self, key, value=None): self.events.append(("success", key, value))
            def warning(self, key, value=None): self.events.append(("warning", key, value))
            def skip(self, key, value=None): self.events.append(("skip", key, value))
            def fail(self, key, error): self.events.append(("fail", key, error))
            def repository_progress(self, completed, total, last_repository, failed):
                self.events.append(("progress", "scan_repositories", {"completed": completed, "total": total}))

        config = AppConfig(
            repositories=(RepositoryConfig(name="demo", path="/tmp/demo", fetch=False),),
            email=EmailConfig(host="smtp.example.com", sender="a@b.com"),
            ai=AiConfig(enabled=False),
        )
        recorder = Recorder()
        run_once(config, date(2026, 7, 16), dry_run=True, output_dir="/tmp/hlb-git-pm-test-reports", workflow=recorder)
        terminal = {(event, key) for event, key, _ in recorder.events if event in {"success", "warning", "skip"}}
        self.assertIn(("success", "period"), terminal)
        self.assertIn(("success", "discover_repositories"), terminal)
        self.assertIn(("success", "scan_repositories"), terminal)
        self.assertIn(("success", "aggregate_metrics"), terminal)
        self.assertIn(("warning", "ai_analysis"), terminal)
        self.assertIn(("success", "render_report"), terminal)
        self.assertIn(("skip", "send_email"), terminal)
