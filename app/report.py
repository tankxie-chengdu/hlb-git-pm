from __future__ import annotations

import re
from datetime import datetime
from html import escape

from .models import DailyReport, PeriodReport, RepositoryReport


Report = DailyReport | PeriodReport
_TYPE_LABELS = {"daily": "日报", "weekly": "周报", "monthly": "月报"}


def _report_type(report: Report) -> str:
    return "daily" if isinstance(report, DailyReport) else report.report_type


def _period(report: Report) -> tuple[str, str]:
    if isinstance(report, DailyReport):
        return report.report_date, report.report_date
    return report.period_start, report.period_end


def _label(report: Report) -> str:
    return _TYPE_LABELS.get(_report_type(report), _report_type(report))


def _resolve_name(report: Report, commit) -> str:
    if isinstance(report, PeriodReport):
        return report._resolve_name(commit)
    return commit.author_name


def _status_label(status: str) -> str:
    return {"active": "活跃", "empty": "无提交", "failed": "扫描失败"}.get(status, status)


def _last_commit_text(value: datetime | None) -> str:
    return value.strftime("%m-%d %H:%M") if value else "-"


def _render_ai_html(value: str) -> str:
    """Convert the AI's Markdown response into safe email HTML."""
    text = value or "暂无 AI 分析。"
    try:
        import markdown

        return markdown.markdown(
            # Escape raw HTML before Markdown parsing; AI output is untrusted.
            escape(text),
            extensions=["extra", "sane_lists", "nl2br"],
            output_format="html5",
        )
    except ImportError:
        # Keep email generation functional in minimal installations.
        return escape(text).replace("\n", "<br>")


def refresh_ai_section_html(html: str, value: str) -> str:
    """Repair the AI section of HTML saved by older report versions."""
    pattern = re.compile(
        r"(<section[^>]*>\s*<h2[^>]*>1\. 执行摘要</h2>).*?(</section>)",
        re.DOTALL,
    )
    return pattern.sub(lambda match: f"{match.group(1)}{_render_ai_html(value)}{match.group(2)}", html, count=1)


def _render_commit_markdown(report: Report, commit) -> str:
    subject = commit.subject.replace("|", "\\|")
    return (
        f"| {commit.activity_at.strftime('%m-%d')} | {commit.activity_at.strftime('%H:%M')} | "
        f"{_resolve_name(report, commit)} | `{commit.sha[:8]}` | +{commit.additions}/-{commit.deletions} | "
        f"{subject} |"
    )


def _render_markdown(report: Report) -> str:
    start, end = _period(report)
    type_label = _label(report)
    coverage = (
        f"扫描 {report.scanned_repositories} 个仓库，活跃 {report.active_repositories} 个，"
        f"无提交 {report.empty_repositories} 个，失败 {report.failed_repositories} 个。"
    )
    synced_count = report.scanned_repositories - report.failed_repositories
    total_repos = report.total_repositories_count or report.scanned_repositories
    lines = [
        f"# Git {type_label} | {start}" + (f" ~ {end}" if end != start else ""),
        "",
        "## 0. WeFi-HLB 概览",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 仓库总数 | {total_repos} |",
        f"| 同步成功 | {synced_count} |",
        f"| 活跃仓库 | {report.active_repositories} |",
        f"| 无提交仓库 | {report.empty_repositories} |",
        f"| 同步失败 | {report.failed_repositories} |",
        f"| 提交总数 | {report.total_commits} |",
        f"| 贡献者总数 | {report.contributor_count} |",
        "",
        "## 1. 执行摘要",
        "",
        report.ai_analysis or "暂无 AI 分析。",
        "",
        "## 2. 宏观概览",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 扫描仓库 | {report.scanned_repositories} |",
        f"| 活跃仓库 | {report.active_repositories} |",
        f"| 无提交仓库 | {report.empty_repositories} |",
        f"| 扫描失败仓库 | {report.failed_repositories} |",
        f"| 贡献者 | {report.contributor_count} |",
        f"| 提交数 | {report.total_commits} |",
        f"| 文件变更 | {report.total_files_changed} |",
        f"| 代码变更 | +{report.total_additions} / -{report.total_deletions} |",
        "",
        "## 3. 活动趋势",
        "",
    ]
    if report.daily_trend:
        lines.extend(
            [
                "| 日期 | 提交 | 活跃仓库 | 贡献者 |",
                "| --- | ---: | ---: | ---: |",
                *[
                    f"| {row['date']} | {row['commits']} | {row['repositories']} | {row['contributors']} |"
                    for row in report.daily_trend
                ],
            ]
        )
    else:
        lines.append("本周期无提交，暂无趋势数据。")
    lines.extend(["", "## 4. 仓库活动分布", "", "| 仓库 | 状态 | 提交 | 贡献者 | 文件变更 | 新增 | 删除 | 最近提交 |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"])
    for row in report.repository_activity:
        lines.append(
            f"| {row['name']} | {_status_label(str(row['status']))} | {row['commits']} | "
            f"{row['contributors']} | {row['files_changed']} | +{row['additions']} | -{row['deletions']} | "
            f"{_last_commit_text(row['last_commit_at'])} |"
        )

    lines.extend(["", "## 5. 人员协作概览", ""])
    by_author = report.commits_by_author if isinstance(report, PeriodReport) else _daily_by_author(report)
    if by_author:
        lines.extend(["| 人员 | 提交 | 涉及仓库 | 新增 | 删除 |", "| --- | ---: | ---: | ---: | ---: |"])
        for name, commits in sorted(by_author.items(), key=lambda item: (-len(item[1]), item[0])):
            lines.append(
                f"| {name} | {len(commits)} | {len({c.repository for c in commits})} | "
                f"+{sum(c.additions for c in commits)} | -{sum(c.deletions for c in commits)} |"
            )
    else:
        lines.append("本周期无提交，暂无人员活动数据。")

    lines.extend(["", "## 6. 仓库详情", ""])
    for repo in report.repositories:
        lines.extend([f"### {repo.name} ({repo.branch})", ""])
        if repo.error:
            lines.extend([f"> 扫描失败：{repo.error}", ""])
            continue
        if not repo.commits:
            lines.extend(["本周期无提交。", ""])
            continue
        lines.extend(
            [
                f"提交 **{len(repo.commits)}** 次，贡献者 **{len({(c.author_email or c.author_name).lower() for c in repo.commits})}**，"
                f"代码变更 **+{sum(c.additions for c in repo.commits)} / -{sum(c.deletions for c in repo.commits)}**。",
                "",
                "<details><summary>提交明细</summary>",
                "",
                "| 日期 | 时间 | 提交者 | 提交 | 变更 | 摘要 |",
                "| --- | --- | --- | --- | ---: | --- |",
                *[_render_commit_markdown(report, commit) for commit in repo.commits],
                "",
                "</details>",
                "",
            ]
        )

    lines.extend(
        [
            "## 7. 数据说明",
            "",
            "- 提交统计按仓库内 commit SHA 去重，时间范围按报告时区解释。",
            "- 增删行是代码活动指标，不直接等同于工作量或绩效。",
            "- AI 分析基于提交信息和统计数据，风险判断需要人工确认。",
        ]
    )
    return "\n".join(lines)


def _daily_by_author(report: DailyReport) -> dict[str, list]:
    result: dict[str, list] = {}
    for commit in report.commits:
        result.setdefault(commit.author_name, []).append(commit)
    return result


def render_markdown(report: DailyReport) -> str:
    return _render_markdown(report)


def render_period_markdown(report: PeriodReport) -> str:
    return _render_markdown(report)


def _render_html(report: Report) -> str:
    start, end = _period(report)
    type_label = _label(report)
    synced_count = report.scanned_repositories - report.failed_repositories
    total_repos = report.total_repositories_count or report.scanned_repositories
    overview_rows = f"""<tr><td>仓库总数</td><td><strong>{total_repos}</strong></td></tr>
<tr><td>同步成功</td><td><strong style="color:#0d9488">{synced_count}</strong></td></tr>
<tr><td>活跃仓库</td><td><strong style="color:#059669">{report.active_repositories}</strong></td></tr>
<tr><td>无提交仓库</td><td>{report.empty_repositories}</td></tr>
<tr><td>同步失败</td><td><strong style="color:#dc2626">{report.failed_repositories}</strong></td></tr>
<tr><td>提交总数</td><td><strong>{report.total_commits}</strong></td></tr>
<tr><td>贡献者总数</td><td><strong>{report.contributor_count}</strong></td></tr>"""
    activity_rows = "".join(
        f"<tr><td>{escape(str(row['name']))}</td><td>{escape(_status_label(str(row['status'])))}</td>"
        f"<td>{row['commits']}</td><td>{row['contributors']}</td><td>{row['files_changed']}</td>"
        f"<td>+{row['additions']}</td><td>-{row['deletions']}</td>"
        f"<td>{escape(_last_commit_text(row['last_commit_at']))}</td></tr>"
        for row in report.repository_activity
    )
    trend_rows = "".join(
        f"<tr><td>{escape(str(row['date']))}</td><td>{row['commits']}</td>"
        f"<td>{row['repositories']}</td><td>{row['contributors']}</td></tr>"
        for row in report.daily_trend
    ) or '<tr><td colspan="4">本周期无提交，暂无趋势数据。</td></tr>'
    by_author = report.commits_by_author if isinstance(report, PeriodReport) else _daily_by_author(report)
    author_rows = "".join(
        f"<tr><td>{escape(name)}</td><td>{len(commits)}</td>"
        f"<td>{len({c.repository for c in commits})}</td>"
        f"<td>+{sum(c.additions for c in commits)}</td><td>-{sum(c.deletions for c in commits)}</td></tr>"
        for name, commits in sorted(by_author.items(), key=lambda item: (-len(item[1]), item[0]))
    ) or '<tr><td colspan="5">本周期无提交，暂无人员活动数据。</td></tr>'

    repo_sections = []
    for repo in report.repositories:
        if repo.error:
            body = f'<p style="color:#b42318">扫描失败：{escape(repo.error)}</p>'
        elif not repo.commits:
            body = '<p style="color:#667085">本周期无提交。</p>'
        else:
            rows = "".join(
                f"<tr><td>{commit.activity_at.strftime('%m-%d')}</td><td>{commit.activity_at.strftime('%H:%M')}</td>"
                f"<td>{escape(_resolve_name(report, commit))}</td><td><code>{commit.sha[:8]}</code></td>"
                f"<td>+{commit.additions}/-{commit.deletions}</td><td>{escape(commit.subject)}</td></tr>"
                for commit in repo.commits
            )
            body = (
                f"<p>提交 <strong>{len(repo.commits)}</strong> 次，贡献者 <strong>{len({(c.author_email or c.author_name).lower() for c in repo.commits})}</strong>，"
                f"代码变更 <strong>+{sum(c.additions for c in repo.commits)}/-{sum(c.deletions for c in repo.commits)}</strong>。</p>"
                '<details><summary>提交明细</summary>'
                '<table style="width:100%;border-collapse:collapse;font-size:13px">'
                '<tr style="background:#f2f4f7"><th align="left">日期</th><th align="left">时间</th>'
                '<th align="left">提交者</th><th align="left">提交</th><th align="left">变更</th><th align="left">摘要</th></tr>'
                + rows + "</table></details>"
            )
        repo_sections.append(f"<h3>{escape(repo.name)} <small>({escape(repo.branch)})</small></h3>{body}")

    return f"""<!doctype html><html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#101828;max-width:1100px;margin:0 auto;padding:24px">
<h1>Git {escape(type_label)} | {escape(start)}""" + (f" ~ {escape(end)}" if end != start else "") + f"""</h1>
<h2 style="margin-top:0;margin-bottom:12px">0. WeFi-HLB 概览</h2>
<table style="border-collapse:collapse;width:100%;margin-bottom:24px"><tr style="background:#f2f4f7"><th align="left">指标</th><th align="left">数值</th></tr>
{overview_rows}
</table>
<section style="background:#f0fdfa;border-left:4px solid #0d9488;padding:16px;margin-bottom:24px"><h2 style="margin-top:0">1. 执行摘要</h2>{_render_ai_html(report.ai_analysis)}</section>
<h2>2. 宏观概览</h2><table style="border-collapse:collapse;width:100%"><tr style="background:#f2f4f7"><th align="left">指标</th><th align="left">数值</th></tr>
<tr><td>扫描仓库</td><td>{report.scanned_repositories}</td></tr><tr><td>活跃仓库</td><td>{report.active_repositories}</td></tr><tr><td>无提交仓库</td><td>{report.empty_repositories}</td></tr><tr><td>扫描失败仓库</td><td>{report.failed_repositories}</td></tr><tr><td>贡献者</td><td>{report.contributor_count}</td></tr><tr><td>提交数</td><td>{report.total_commits}</td></tr><tr><td>文件变更</td><td>{report.total_files_changed}</td></tr><tr><td>代码变更</td><td>+{report.total_additions} / -{report.total_deletions}</td></tr></table>
<h2>3. 活动趋势</h2><table style="border-collapse:collapse;width:100%"><tr style="background:#f2f4f7"><th align="left">日期</th><th>提交</th><th>活跃仓库</th><th>贡献者</th></tr>{trend_rows}</table>
<h2>4. 仓库活动分布</h2><table style="border-collapse:collapse;width:100%;font-size:14px"><tr style="background:#f2f4f7"><th align="left">仓库</th><th align="left">状态</th><th>提交</th><th>贡献者</th><th>文件</th><th>新增</th><th>删除</th><th align="left">最近提交</th></tr>{activity_rows}</table>
<h2>5. 人员协作概览</h2><table style="border-collapse:collapse;width:100%"><tr style="background:#f2f4f7"><th align="left">人员</th><th>提交</th><th>仓库</th><th>新增</th><th>删除</th></tr>{author_rows}</table>
<h2>6. 仓库详情</h2>{''.join(repo_sections)}
<h2>7. 数据说明</h2><ul><li>提交统计按仓库内 commit SHA 去重，时间范围按报告时区解释。</li><li>增删行是代码活动指标，不直接等同于工作量或绩效。</li><li>AI 分析基于提交信息和统计数据，风险判断需要人工确认。</li></ul>
</body></html>"""


def render_html(report: DailyReport) -> str:
    return _render_html(report)


def render_period_html(report: PeriodReport) -> str:
    return _render_html(report)
