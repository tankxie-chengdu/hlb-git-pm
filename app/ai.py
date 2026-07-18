from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import AiConfig
from .models import DailyReport, PeriodReport


def build_context(report: DailyReport | PeriodReport, max_commits: int) -> str:
    lines = []
    if isinstance(report, PeriodReport):
        type_label = {"daily": "日报", "weekly": "周报", "monthly": "月报"}.get(report.report_type, report.report_type)
        lines.append(f"报告类型: {type_label}")
        lines.append(f"统计周期: {report.period_start} ~ {report.period_end}")
    else:
        lines.append(f"日报日期: {report.report_date}")
    lines.extend(
        [
            f"扫描仓库: {report.scanned_repositories}, 活跃仓库: {report.active_repositories}, "
            f"无提交仓库: {report.empty_repositories}, 扫描失败: {report.failed_repositories}",
            f"贡献者: {report.contributor_count}, 总提交: {report.total_commits}, "
            f"文件变更: {report.total_files_changed}, 新增: {report.total_additions}, 删除: {report.total_deletions}",
        ]
    )

    lines.append("仓库活动:")
    for row in report.repository_activity:
        lines.append(
            f"  - {row['name']} | 状态={row['status']} | 提交={row['commits']} | "
            f"贡献者={row['contributors']} | 文件={row['files_changed']} | "
            f"+{row['additions']}/-{row['deletions']}"
        )

    if report.daily_trend:
        lines.append("按日趋势:")
        lines.extend(
            f"  - {row['date']} | 提交={row['commits']} | 仓库={row['repositories']} | 贡献者={row['contributors']}"
            for row in report.daily_trend
        )

    remaining = max_commits
    for repo in report.repositories:
        lines.append(f"仓库 {repo.name} ({repo.branch}): {len(repo.commits)} 次提交")
        if repo.error:
            lines.append(f"  扫描错误: {repo.error}")
        for commit in repo.commits[:remaining]:
            lines.append(
                f"  - {commit.author_name} | {commit.sha[:8]} | "
                f"+{commit.additions}/-{commit.deletions}, {commit.files_changed} files | {commit.subject}"
            )
        remaining = max(0, remaining - len(repo.commits))
    return "\n".join(lines)


def context_commit_count(report: DailyReport | PeriodReport, max_commits: int) -> int:
    """Return how many commit detail rows are actually sent to the AI."""
    remaining = max(0, max_commits)
    included = 0
    for repo in report.repositories:
        if remaining <= 0:
            break
        included += min(len(repo.commits), remaining)
        remaining = max(0, remaining - len(repo.commits))
    return included


def fallback_analysis(report: DailyReport | PeriodReport) -> str:
    if not report.commits:
        return "本周期内没有捕获到提交。建议确认分支、时区和仓库同步状态。"
    authors: dict[str, int] = {}
    for commit in report.commits:
        authors[commit.author_name] = authors.get(commit.author_name, 0) + 1
    top = sorted(authors.items(), key=lambda item: item[1], reverse=True)[:3]
    people = "、".join(f"{name}（{count} 次）" for name, count in top)
    return (
        f"共 {report.total_commits} 次提交，代码变更 +{report.total_additions}/-"
        f"{report.total_deletions}。主要提交者：{people}。"
        "当前为本地规则摘要；配置 AI API 后可生成风险、协作和工作量分析。"
    )


def _build_prompt(report: DailyReport | PeriodReport, max_commits: int) -> str:
    context = build_context(report, max_commits)
    if isinstance(report, PeriodReport) and report.report_type in ("weekly", "monthly"):
        type_label = "周报" if report.report_type == "weekly" else "月报"
        return (
            f"你是工程团队的代码活动分析助手。请根据以下 Git {type_label}，输出面向研发负责人的简洁中文分析，包含："
            "1) 执行摘要；2) 重点进展主题；3) 仓库活动和趋势；4) 人员协作概况；"
            "5) 潜在风险或需要跟进的事项；6) 下一周期建议。"
            "只能基于提供的事实进行归纳，不要把提交数量直接解释为绩效，不要臆造需求完成度。"
            "使用 Markdown 小标题和项目符号，并明确区分事实与推断。\n\n" + context
        )
    return (
        "你是工程团队的代码活动分析助手。请根据以下 Git 日报，输出面向研发负责人的简洁中文分析，包含："
        "1) 执行摘要；2) 重点进展主题；3) 仓库活动概况；4) 人员协作概况；"
        "5) 潜在风险或需要跟进的事项；6) 明日建议。"
        "只能基于提供的事实进行归纳，不要把提交数量直接解释为绩效，不要臆造需求完成度。"
        "使用 Markdown 小标题和项目符号，并明确区分事实与推断。\n\n" + context
    )


def analyze(report: DailyReport | PeriodReport, config: AiConfig) -> str:
    if not config.enabled or not config.api_key:
        return fallback_analysis(report)
    prompt = _build_prompt(report, config.max_commits)
    request_body = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": "你输出面向研发经理的客观、可执行的报告分析。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    if config.thinking_enabled is not None:
        request_body["thinking"] = {"type": "enabled" if config.thinking_enabled else "disabled"}
    payload = json.dumps(request_body).encode("utf-8")
    request = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
        message = result["choices"][0]["message"]
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("AI 返回空正文，可能只返回了 reasoning_content")
        return content.strip()
    except (OSError, urllib.error.HTTPError, KeyError, IndexError, ValueError, json.JSONDecodeError) as error:
        return fallback_analysis(report) + f"\n\n> AI 分析调用失败，已降级为规则摘要：{error}"
