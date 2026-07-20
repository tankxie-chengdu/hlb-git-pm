from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Callable

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


def _json_candidate(value: str) -> object:
    """Decode a model response that may be wrapped in a JSON code fence."""
    candidate = (value or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1)
    return json.loads(candidate)


def _normalize_project_analysis(item: object, project_names: set[str]) -> dict[str, object] | None:
    if not isinstance(item, dict):
        return None
    repository = _clean_text(item.get("repository"), 300)
    if repository not in project_names:
        return None
    quality_signal = _clean_text(item.get("quality_signal"), 240) or "未提供工程质量信号。"
    quality_level = _clean_text(item.get("quality_level"), 20)
    confidence = _clean_text(item.get("confidence"), 10)
    if any(term in quality_signal for term in SUBJECTIVE_QUALITY_TERMS):
        quality_signal = "模型返回了主观质量评价，已降级；需结合代码审查、测试和 CI 结果确认。"
        quality_level = "证据不足"
        confidence = "低"
    evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
    return {
        "repository": repository,
        "work_summary": _clean_text(item.get("work_summary"), 240) or "未提供工作主题摘要。",
        "quality_signal": quality_signal,
        "quality_level": quality_level if quality_level in QUALITY_LEVELS else "证据不足",
        "evidence": [_clean_text(entry, 120) for entry in evidence[:3] if _clean_text(entry, 120)],
        "confidence": confidence if confidence in CONFIDENCE_LEVELS else "低",
    }


def parse_project_batch_response(
    value: str,
    projects: list[dict[str, object]],
) -> tuple[list[dict[str, object]], bool, str | None]:
    """Parse one yearly project-batch response and fill missing projects safely."""
    project_names = {str(row["name"]) for row in projects}
    try:
        payload = _json_candidate(value)
        if not isinstance(payload, dict) or not isinstance(payload.get("project_analyses"), list):
            raise ValueError("AI 批次响应缺少 project_analyses")
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return ([_fallback_project_analysis(row) for row in projects], False, str(error))

    parsed: dict[str, dict[str, object]] = {}
    for item in payload["project_analyses"]:
        normalized = _normalize_project_analysis(item, project_names)
        if normalized and normalized["repository"] not in parsed:
            parsed[str(normalized["repository"])] = normalized
    completed = [parsed.get(str(row["name"])) or _fallback_project_analysis(row) for row in projects]
    missing = len(parsed) != len(project_names)
    return completed, not missing, (f"批次缺少 {len(project_names) - len(parsed)} 个项目" if missing else None)


def _commit_prompt_record(report: DailyReport | PeriodReport, commit) -> dict[str, object]:
    return {
        "repository": commit.repository,
        "sha": commit.sha[:12],
        "author": report._resolve_name(commit),
        "activity_at": commit.activity_at.isoformat(),
        "subject": commit.subject,
        "files_changed": commit.files_changed,
        "additions": commit.additions,
        "deletions": commit.deletions,
    }


def _yearly_project_batch_prompt(
    report: PeriodReport,
    projects: list[dict[str, object]],
    selected_commits: dict[str, list],
    batch_number: int,
    batch_count: int,
) -> str:
    project_names = {str(row["name"]) for row in projects}
    commit_records = [
        _commit_prompt_record(report, commit)
        for repo in report.repositories
        if repo.name in project_names
        for commit in selected_commits.get(repo.name, [])
    ]
    return (
        f"这是 Git 年报的项目分批分析，第 {batch_number}/{batch_count} 批。统计周期：{report.period_start} ~ {report.period_end}。"
        "只返回一个合法 JSON 对象，不要使用代码围栏或额外文字。"
        "顶层结构必须是 {\"project_analyses\":[...]}，每个项目必须输出 repository、work_summary、"
        "quality_signal、quality_level、evidence、confidence。只能依据输入事实，无法判断时使用证据不足。"
        "不要把提交数或代码行数直接等同于绩效。\n\n"
        "项目聚合数据：\n"
        + json.dumps(projects, ensure_ascii=False, default=str)
        + "\n\n提交主题样本：\n"
        + json.dumps(commit_records, ensure_ascii=False, default=str)
    )


def _yearly_global_context(
    report: PeriodReport,
    project_analyses: list[dict[str, object]],
    max_commits: int,
) -> tuple[str, list[dict[str, object]]]:
    """Build a smaller synthesis context after project batches finish."""
    sections = _context_sections(report, max_commits)
    selected_keys = {"scope", "metrics", "person_contributions", "repository_activity", "daily_trend"}
    lines: list[str] = []
    sources: list[dict[str, object]] = []
    for section in sections:
        if section["key"] not in selected_keys:
            continue
        section_lines = "\n".join(section["lines"])
        lines.extend(section["lines"])
        sources.append(
            {
                "key": section["key"],
                "label": section["label"],
                "origin": section["origin"],
                "records": section["records"],
                "included_records": section["included_records"],
                "omitted_records": section["omitted_records"],
                "characters": len(section_lines),
                "details": section["details"],
            }
        )
    batch_text = json.dumps(project_analyses, ensure_ascii=False, default=str)
    lines.extend(["项目分批分析结果:", batch_text])
    sources.append(
        {
            "key": "yearly_project_batches",
            "label": "项目分批分析",
            "origin": "按项目批次调用 AI 后合并",
            "records": len(project_analyses),
            "included_records": len(project_analyses),
            "omitted_records": 0,
            "characters": len(batch_text),
            "details": {"project_count": len(project_analyses)},
        }
    )
    return "\n".join(lines), sources


def _yearly_synthesis_prompt(report: PeriodReport, context: str) -> str:
    return (
        "请根据以下 Git 年报统计上下文和已完成的项目分批分析，生成面向研发负责人的简洁中文全局分析。"
        "只返回一个合法 JSON 对象，不要使用代码围栏或额外文字。顶层结构必须是 "
        "{\"analysis_markdown\":\"完整 Markdown 分析\"}。"
        "analysis_markdown 严格包含：1) 执行摘要；2) 项目维度总体进展；3) 人员维度总体贡献；"
        "4) 工作分配与协作信号；5) 风险及需要核实的事项；6) 下一周期建议。"
        "必须区分事实、推断和建议；提交数、代码行数不直接等同于绩效；不要臆造代码质量或需求完成度。\n\n"
        + context
    )


def _request_completion(config: AiConfig, prompt: str) -> str:
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
    with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
        result = json.loads(response.read().decode("utf-8"))
    message = result["choices"][0]["message"]
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("AI 返回空正文，可能只返回了 reasoning_content")
    return content.strip()


def analyze_yearly(
    report: PeriodReport,
    config: AiConfig,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, Any]:
    """Analyze yearly reports in project batches, then synthesize globally."""
    if not config.enabled or not config.api_key:
        return {
            "raw_response": fallback_analysis(report),
            "degraded": True,
            "strategy": "fallback",
            "batch_size": config.yearly_project_batch_size,
            "batch_count": 0,
            "batches": [],
            "synthesis": {"status": "skipped", "reason": "AI 未启用或未配置 API key"},
        }

    projects = list(report.project_contributions)
    batch_size = max(1, config.yearly_project_batch_size)
    project_batches = [projects[index:index + batch_size] for index in range(0, len(projects), batch_size)]
    selected_commits = _stratified_commits(report, config.max_commits)
    batch_details: list[dict[str, object]] = []
    project_analyses: list[dict[str, object]] = []
    degraded = False

    for index, batch in enumerate(project_batches, start=1):
        prompt = _yearly_project_batch_prompt(report, batch, selected_commits, index, len(project_batches))
        started = time.monotonic()
        error_text = None
        status = "success"
        raw_batch = ""
        try:
            raw_batch = _request_completion(config, prompt)
            analyses, structured, parse_error = parse_project_batch_response(raw_batch, batch)
            if not structured:
                status = "warning"
                error_text = parse_error
                degraded = True
        except (OSError, urllib.error.HTTPError, KeyError, IndexError, ValueError, json.JSONDecodeError) as error:
            analyses = [_fallback_project_analysis(row) for row in batch]
            status = "warning"
            error_text = str(error)
            degraded = True
        project_analyses.extend(analyses)
        batch_details.append(
            {
                "batch_number": index,
                "batch_count": len(project_batches),
                "status": status,
                "project_names": [str(row["name"]) for row in batch],
                "project_count": len(batch),
                "selected_commit_count": sum(len(selected_commits.get(str(row["name"]), [])) for row in batch),
                "prompt_characters": len(prompt),
                "prompt_preview": prompt[:2000],
                "output_project_count": len(analyses),
                "response_preview": raw_batch[:2000],
                "duration_ms": int((time.monotonic() - started) * 1000),
                "error": error_text,
            }
        )
        if progress_callback:
            progress_callback(
                {
                    "process": f"已完成年报项目批次 {index}/{len(project_batches)}，准备继续分析。",
                    "progress": int(index * 100 / (len(project_batches) + 1)),
                    "analysis_stages": {
                        "strategy": "yearly_project_batches",
                        "batch_size": batch_size,
                        "batch_count": len(project_batches),
                        "completed_batches": index,
                        "batches": batch_details,
                    },
                }
            )

    global_context, global_sources = _yearly_global_context(report, project_analyses, config.max_commits)
    synthesis_prompt = _yearly_synthesis_prompt(report, global_context)
    synthesis_started = time.monotonic()
    synthesis_status = "success"
    synthesis_error = None
    try:
        raw_synthesis = _request_completion(config, synthesis_prompt)
        payload = _json_candidate(raw_synthesis)
        analysis_markdown = str(payload.get("analysis_markdown") or "").strip() if isinstance(payload, dict) else ""
        if not analysis_markdown:
            raise ValueError("AI 汇总响应缺少 analysis_markdown")
    except (OSError, urllib.error.HTTPError, KeyError, IndexError, ValueError, json.JSONDecodeError) as error:
        analysis_markdown = fallback_analysis(report)
        synthesis_status = "warning"
        synthesis_error = str(error)
        degraded = True

    raw_response = json.dumps(
        {"analysis_markdown": analysis_markdown, "project_analyses": project_analyses},
        ensure_ascii=False,
    )
    return {
        "raw_response": raw_response,
        "degraded": degraded,
        "strategy": "yearly_project_batches",
        "batch_size": batch_size,
        "batch_count": len(project_batches),
        "batches": batch_details,
        "synthesis": {
            "status": synthesis_status,
            "prompt_characters": len(synthesis_prompt),
            "context_characters": len(global_context),
            "duration_ms": int((time.monotonic() - synthesis_started) * 1000),
            "error": synthesis_error,
        },
        "synthesis_prompt": synthesis_prompt,
        "global_prompt_sources": global_sources,
    }


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
    try:
        return _request_completion(config, prompt)
    except (OSError, urllib.error.HTTPError, KeyError, IndexError, ValueError, json.JSONDecodeError) as error:
        return fallback_analysis(report) + f"\n\n> AI 分析调用失败，已降级为规则摘要：{error}"
