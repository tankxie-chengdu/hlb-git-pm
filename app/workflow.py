from __future__ import annotations

from typing import Any, Protocol


STEP_PLAN: tuple[tuple[str, str], ...] = (
    ("period", "确定统计周期"),
    ("discover_repositories", "确定仓库范围"),
    ("scan_repositories", "同步或复用提交"),
    ("aggregate_metrics", "计算宏观指标"),
    ("ai_analysis", "AI 分析"),
    ("render_report", "渲染报告"),
    ("send_email", "发送邮件"),
    ("persist_report", "保存报告历史"),
)


class WorkflowReporter(Protocol):
    def start(self, step_key: str, input_summary: dict[str, Any] | None = None) -> None: ...

    def progress(self, step_key: str, output_summary: dict[str, Any]) -> None: ...

    def success(self, step_key: str, output_summary: dict[str, Any] | None = None) -> None: ...

    def warning(self, step_key: str, output_summary: dict[str, Any] | None = None) -> None: ...

    def skip(self, step_key: str, output_summary: dict[str, Any] | None = None) -> None: ...

    def fail(self, step_key: str, error: str) -> None: ...
