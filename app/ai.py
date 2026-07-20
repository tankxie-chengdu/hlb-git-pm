from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .config import AiConfig
from .models import DailyReport, PeriodReport

SYSTEM_PROMPT = (
    "你是面向研发负责人的代码活动分析助手。必须区分数据事实、风险推断和跟进建议；"
    "提交数、代码行数和文件数不直接等同于产能或绩效，无提交也不能推断为未工作。"
)

QUALITY_LEVELS = {"稳定", "需关注", "证据不足"}
CONFIDENCE_LEVELS = {"高", "中", "低"}
SUBJECTIVE_QUALITY_TERMS = ("专业", "健康", "优秀", "低劣", "糟糕", "高质量", "低质量")


def _stratified_commits(report: DailyReport | PeriodReport, max_commits: int) -> dict[str, list]:
    """Select recent commits fairly across active projects."""
    active = [repo for repo in report.repositories if repo.commits and not repo.error]
    selected = {repo.name: [] for repo in report.repositories}
    remaining = max(0, max_commits)
    offset = 0
    while remaining and active:
        next_active = []
        for repo in active:
            if offset < len(repo.commits):
                selected[repo.name].append(repo.commits[offset])
                remaining -= 1
                if remaining == 0:
                    break
            if offset + 1 < len(repo.commits):
                next_active.append(repo)
        active = next_active
        offset += 1
    return selected


def _context_sections(report: DailyReport | PeriodReport, max_commits: int) -> list[dict]:
    """Build the exact context blocks and metadata used by the AI prompt."""
    sections: list[dict] = []
    if isinstance(report, PeriodReport):
        type_label = {"daily": "日报", "weekly": "周报", "monthly": "月报", "yearly": "年报"}.get(report.report_type, report.report_type)
        scope_lines = [f"报告类型: {type_label}", f"统计周期: {report.period_start} ~ {report.period_end}"]
        scope_details = {"report_type": report.report_type, "period_start": report.period_start, "period_end": report.period_end}
    else:
        scope_lines = [f"日报日期: {report.report_date}"]
        scope_details = {"report_type": "daily", "report_date": report.report_date}
    sections.append({"key": "scope", "label": "统计范围", "origin": "DailyReport / PeriodReport", "lines": scope_lines, "records": 1, "included_records": 1, "omitted_records": 0, "details": scope_details})

    metrics_lines = [
        f"扫描仓库: {report.scanned_repositories}, 活跃仓库: {report.active_repositories}, "
        f"无提交仓库: {report.empty_repositories}, 扫描失败: {report.failed_repositories}",
        f"贡献者: {report.contributor_count}, 总提交: {report.total_commits}, "
        f"文件变更: {report.total_files_changed}, 新增: {report.total_additions}, 删除: {report.total_deletions}",
    ]
    sections.append(
        {
            "key": "metrics",
            "label": "宏观指标",
            "origin": "报告对象的聚合属性",
            "lines": metrics_lines,
            "records": 2,
            "included_records": 2,
            "omitted_records": 0,
            "details": {
                "scanned_repositories": report.scanned_repositories,
                "active_repositories": report.active_repositories,
                "empty_repositories": report.empty_repositories,
                "failed_repositories": report.failed_repositories,
                "contributors": report.contributor_count,
                "commits": report.total_commits,
                "files_changed": report.total_files_changed,
                "additions": report.total_additions,
                "deletions": report.total_deletions,
            },
        }
    )

    project_lines = ["项目维度贡献:"]
    for project in report.project_contributions:
        project_lines.append(
            f"  - {project['name']} | 状态={project['status']} | 提交={project['commit_count']} | "
            f"贡献者={project['contributor_count']} | 文件={project['files_changed']} | +{project['additions']}/-{project['deletions']}"
        )
        project_lines.extend(
            f"    * {person['name']} | 提交={person['commit_count']} | 活跃天数={person['active_days']} | "
            f"文件={person['files_changed']} | +{person['additions']}/-{person['deletions']}"
            for person in project["contributors"]
        )
    sections.append(
        {
            "key": "project_contributions",
            "label": "项目维度贡献",
            "origin": "所选周期全部提交按项目和人员聚合",
            "lines": project_lines,
            "records": len(report.project_contributions),
            "included_records": len(report.project_contributions),
            "omitted_records": 0,
            "details": {"projects": report.project_contributions},
        }
    )

    person_lines = ["人员维度贡献:"]
    for person in report.person_contributions:
        projects = "、".join(f"{project['name']}({project['commits']})" for project in person["projects"]) or "无"
        person_lines.append(
            f"  - {person['name']} | 部门={person['department'] or '-'} | 提交={person['commit_count']} | "
            f"活跃天数={person['active_days']} | 项目={person['repository_count']} | 文件={person['files_changed']} | "
            f"+{person['additions']}/-{person['deletions']} | 项目贡献={projects}"
        )
    sections.append(
        {
            "key": "person_contributions",
            "label": "人员维度贡献",
            "origin": "人员名单与所选周期全部提交归并",
            "lines": person_lines,
            "records": len(report.person_contributions),
            "included_records": len(report.person_contributions),
            "omitted_records": 0,
            "details": {"people": report.person_contributions},
        }
    )

    repository_lines = ["仓库活动:"]
    for row in report.repository_activity:
        repository_lines.append(
            f"  - {row['name']} | 状态={row['status']} | 提交={row['commits']} | "
            f"贡献者={row['contributors']} | 文件={row['files_changed']} | "
            f"+{row['additions']}/-{row['deletions']}"
        )
    sections.append(
        {
            "key": "repository_activity",
            "label": "仓库活动",
            "origin": "RepositoryReport.commits 按仓库聚合",
            "lines": repository_lines,
            "records": len(report.repository_activity),
            "included_records": len(report.repository_activity),
            "omitted_records": 0,
            "details": {
                "repositories": [
                    {
                        "name": row["name"],
                        "branch": row["branch"],
                        "status": row["status"],
                        "commits": row["commits"],
                        "contributors": row["contributors"],
                        "files_changed": row["files_changed"],
                        "additions": row["additions"],
                        "deletions": row["deletions"],
                        "error": row["error"],
                    }
                    for row in report.repository_activity
                ]
            },
        }
    )

    if report.daily_trend:
        trend_lines = ["按日趋势:"]
        trend_lines.extend(
            f"  - {row['date']} | 提交={row['commits']} | 仓库={row['repositories']} | 贡献者={row['contributors']}"
            for row in report.daily_trend
        )
        sections.append(
            {
                "key": "daily_trend",
                "label": "按日趋势",
                "origin": "Commit.activity_at 按日期聚合",
                "lines": trend_lines,
                "records": len(report.daily_trend),
                "included_records": len(report.daily_trend),
                "omitted_records": 0,
                "details": {"trend": report.daily_trend},
            }
        )

    selected_commits = _stratified_commits(report, max_commits)
    commit_lines = []
    commit_repositories = []
    included_commits = 0
    for repo in report.repositories:
        commit_lines.append(f"仓库 {repo.name} ({repo.branch}): {len(repo.commits)} 次提交")
        if repo.error:
            commit_lines.append(f"  扫描错误: {repo.error}")
        included = selected_commits.get(repo.name, [])
        included_for_repo = len(included)
        included_commits += included_for_repo
        for commit in included:
            commit_lines.append(
                f"  - {report._resolve_name(commit)} | {commit.sha[:8]} | "
                f"+{commit.additions}/-{commit.deletions}, {commit.files_changed} files | {commit.subject}"
            )
        commit_repositories.append(
            {
                "name": repo.name,
                "branch": repo.branch,
                "total_commits": len(repo.commits),
                "included_commits": included_for_repo,
                "omitted_commits": max(0, len(repo.commits) - included_for_repo),
                "error": repo.error,
            }
        )
    sections.append(
        {
            "key": "commit_details",
            "label": "提交明细",
            "origin": "RepositoryReport.commits 跨项目均匀截取",
            "lines": commit_lines,
            "records": report.total_commits,
            "included_records": included_commits,
            "omitted_records": max(0, report.total_commits - included_commits),
            "details": {"max_commits": max(0, max_commits), "repositories": commit_repositories},
        }
    )
    return sections


def build_context(report: DailyReport | PeriodReport, max_commits: int) -> str:
    return "\n".join(line for section in _context_sections(report, max_commits) for line in section["lines"])


def context_source_summary(report: DailyReport | PeriodReport, max_commits: int) -> list[dict]:
    """Return provenance metadata for the context shown in the user prompt."""
    sections = _context_sections(report, max_commits)
    result = []
    for section in sections:
        text = "\n".join(section["lines"])
        result.append(
            {
                "key": section["key"],
                "label": section["label"],
                "origin": section["origin"],
                "records": section["records"],
                "included_records": section["included_records"],
                "omitted_records": section["omitted_records"],
                "characters": len(text),
                "details": section["details"],
            }
        )
    return result


def context_commit_count(report: DailyReport | PeriodReport, max_commits: int) -> int:
    """Return how many commit detail rows are actually sent to the AI."""
    return sum(len(commits) for commits in _stratified_commits(report, max_commits).values())


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


def build_prompt(report: DailyReport | PeriodReport, max_commits: int) -> str:
    context = build_context(report, max_commits)
    if isinstance(report, PeriodReport):
        type_label = {"daily": "日报", "weekly": "周报", "monthly": "月报", "yearly": "年报"}.get(report.report_type, report.report_type)
    else:
        type_label = "日报"
    return (
        f"请根据以下 Git {type_label}生成面向研发负责人的简洁中文分析。"
        "只返回一个合法 JSON 对象，不要使用 JSON 代码围栏，也不要在 JSON 前后输出其他文字。"
        "JSON 顶层结构必须是："
        '{"analysis_markdown":"完整 Markdown 分析",'
        '"project_analyses":[{"repository":"必须与输入仓库名完全一致",'
        '"work_summary":"简述大家在做什么，最多120字",'
        '"quality_signal":"客观工程质量信号，最多120字",'
        '"quality_level":"稳定|需关注|证据不足",'
        '"evidence":["最多3条数据依据"],"confidence":"高|中|低"}]}。'
        "analysis_markdown 严格按以下结构组织："
        "1) 执行摘要；2) 项目维度：逐项目说明参与人员、贡献分布和进展主题；"
        "3) 人员维度：逐人说明其在所有项目中的贡献、活跃天数和主要方向，包括零提交名单人员；"
        "4) 工作分配与协作信号；5) 风险及需要核实的事项；6) 下一周期建议。"
        "项目和人员统计必须使用完整聚合数据，提交明细只用于归纳主题。"
        "project_analyses 必须覆盖输入中的每一个项目；没有足够提交主题证据时必须写证据不足。"
        "质量分析只能描述可观察的工程活动信号，不得臆测代码正确性、需求完成度或个人绩效。"
        "禁止使用专业、健康、优秀、高质量、低质量等主观评价词；无法找到事实依据时输出证据不足。"
        "不要把提交数量、代码行数直接解释为绩效，不要臆造需求完成度。"
        "使用 Markdown 小标题和项目符号，明确区分事实、推断与建议。\n\n" + context
    )


def _clean_text(value: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _fallback_project_analysis(project: dict[str, object]) -> dict[str, object]:
    return {
        "repository": str(project["name"]),
        "work_summary": "未获得结构化项目主题，建议结合提交明细确认具体工作内容。",
        "quality_signal": "当前证据不足，无法仅凭提交数量和代码行数判断产出质量。",
        "quality_level": "证据不足",
        "evidence": [
            f"{project['commit_count']} 次提交",
            f"{project['contributor_count']} 名贡献者",
            f"变更 +{project['additions']}/-{project['deletions']}",
        ],
        "confidence": "低",
    }


def parse_analysis_response(
    value: str,
    report: DailyReport | PeriodReport,
) -> tuple[str, list[dict[str, object]], bool]:
    """Parse and validate the model's structured response with safe fallbacks."""
    raw = (value or "").strip()
    candidate = raw
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1)
    try:
        payload = json.loads(candidate)
        if not isinstance(payload, dict):
            raise ValueError("AI response is not an object")
        analysis = str(payload.get("analysis_markdown") or "").strip()
        items = payload.get("project_analyses")
        if not analysis or not isinstance(items, list):
            raise ValueError("AI response is missing structured fields")
    except (json.JSONDecodeError, TypeError, ValueError):
        fallbacks = [_fallback_project_analysis(row) for row in report.project_contributions]
        return raw or fallback_analysis(report), fallbacks, False

    project_names = {str(row["name"]) for row in report.project_contributions}
    parsed: dict[str, dict[str, object]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        repository = _clean_text(item.get("repository"), 300)
        if repository not in project_names or repository in parsed:
            continue
        quality_level = _clean_text(item.get("quality_level"), 20)
        confidence = _clean_text(item.get("confidence"), 10)
        quality_signal = _clean_text(item.get("quality_signal"), 240) or "未提供工程质量信号。"
        if any(term in quality_signal for term in SUBJECTIVE_QUALITY_TERMS):
            quality_signal = "模型返回了主观质量评价，已降级；需结合代码审查、测试和 CI 结果确认。"
            quality_level = "证据不足"
            confidence = "低"
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        parsed[repository] = {
            "repository": repository,
            "work_summary": _clean_text(item.get("work_summary"), 240) or "未提供工作主题摘要。",
            "quality_signal": quality_signal,
            "quality_level": quality_level if quality_level in QUALITY_LEVELS else "证据不足",
            "evidence": [_clean_text(entry, 120) for entry in evidence[:3] if _clean_text(entry, 120)],
            "confidence": confidence if confidence in CONFIDENCE_LEVELS else "低",
        }

    completed = [parsed.get(str(row["name"])) or _fallback_project_analysis(row) for row in report.project_contributions]
    return analysis, completed, len(parsed) == len(project_names)


def _build_prompt(report: DailyReport | PeriodReport, max_commits: int) -> str:
    """Backward-compatible alias for callers that used the old private helper."""
    return build_prompt(report, max_commits)


def analyze(report: DailyReport | PeriodReport, config: AiConfig, prompt: str | None = None) -> str:
    if not config.enabled or not config.api_key:
        return fallback_analysis(report)
    prompt = prompt if prompt is not None else build_prompt(report, config.max_commits)
    request_body = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
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
