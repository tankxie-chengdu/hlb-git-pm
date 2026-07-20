from __future__ import annotations

import argparse
import logging
import time as time_module
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .ai import SYSTEM_PROMPT, analyze, analyze_yearly, build_context, build_prompt, context_commit_count, context_source_summary, parse_analysis_response
from .chart import render_trend_chart
from .config import AppConfig, load_config
from .emailer import send_email
from .github_app import discover_repositories
from .git_service import scan_repository
from .models import DailyReport, MemberInfo, PeriodReport, RepositoryReport
from .periods import format_report_title
from .report import render_html, render_markdown, render_period_html, render_period_markdown
from .workflow import WorkflowReporter

REPORT_TOP_LEVEL_SECTION_COUNT = 8

logger = logging.getLogger("git_daily_report")


def _repository_details(repositories: list[RepositoryReport]) -> list[dict[str, object]]:
    return [
        {
            "name": repo.name,
            "status": "failed" if repo.error else ("active" if repo.commits else "empty"),
            "commits": len(repo.commits),
            "contributors": len({(commit.author_email or commit.author_name).lower() for commit in repo.commits}),
            "files_changed": sum(commit.files_changed for commit in repo.commits),
            "additions": sum(commit.additions for commit in repo.commits),
            "deletions": sum(commit.deletions for commit in repo.commits),
            "last_commit_at": max((commit.activity_at for commit in repo.commits), default=None),
            "error": repo.error,
        }
        for repo in repositories
    ]


def _top_contributors(report) -> list[dict[str, object]]:
    return [
        {
            "name": row["name"],
            "is_outsourced": row.get("is_outsourced"),
            "commits": row["commit_count"],
            "repositories": row["repository_count"],
            "additions": row["additions"],
            "deletions": row["deletions"],
        }
        for row in report.person_contributions[:10]
        if row["commit_count"]
    ]


def _text_preview(value: str, limit: int = 6000) -> str:
    if len(value) <= limit:
        return value
    head = limit * 2 // 3
    return value[:head] + "\n...[中间内容已截断]...\n" + value[-(limit - head):]


def run_once(
    config: AppConfig,
    target_date: date,
    *,
    end_date: date | None = None,
    report_type: str = "daily",
    recipients: list[str] | None = None,
    member_mapping: dict[str, MemberInfo] | None = None,
    repo_names: list[str] | None = None,   # None = all repos
    skip_fetch: bool = False,               # True = skip git fetch/clone
    dry_run: bool = False,
    output_dir: str = ".data/reports",
    workflow: WorkflowReporter | None = None,
    snapshot_repositories: list[RepositoryReport] | None = None,
    snapshot_include_empty: bool = False,
    snapshot_activity_window: str | None = None,
    snapshot_id: int | None = None,
) -> DailyReport | PeriodReport:
    timezone = ZoneInfo(config.timezone)
    workspace = Path(config.workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    _end = end_date if end_date is not None else target_date
    if workflow:
        workflow.start(
            "period",
            {
                "report_type": report_type,
                "start_date": target_date.isoformat(),
                "end_date": _end.isoformat(),
                "timezone": config.timezone,
                "source": "active_snapshot" if snapshot_repositories is not None else "live_scan",
                "snapshot_id": snapshot_id,
                "activity_window": snapshot_activity_window,
            },
        )
        workflow.success(
            "period",
            {
                "process": "根据报告类型、时区和快照条件确定统计周期，不执行 Git 操作。",
                "period_start": target_date.isoformat(),
                "period_end": _end.isoformat(),
                "days": (_end - target_date).days + 1,
                "timezone": config.timezone,
            },
        )

    repositories: list[RepositoryReport]
    if snapshot_repositories is not None:
        # The active-project filter already scanned these repositories. Reuse its
        # exact results so report generation never performs a second Git scan.
        repositories = list(snapshot_repositories) if snapshot_include_empty else [repo for repo in snapshot_repositories if repo.commits or repo.error]
        if repo_names:
            selected = set(repo_names)
            repositories = [repo for repo in repositories if repo.name in selected]
        logger.info("复用活跃项目筛选快照：%d 个仓库", len(repositories))
        if workflow:
            workflow.start(
                "discover_repositories",
                {
                    "source": "active_snapshot",
                    "snapshot_repositories": len(snapshot_repositories),
                    "requested_repositories": repo_names or [],
                    "activity_window": snapshot_activity_window,
                },
            )
            workflow.skip(
                "discover_repositories",
                {
                    "process": "从活跃项目筛选快照读取仓库范围，不重新调用 GitHub API。",
                    "operation": "reuse_snapshot",
                    "source": "active_snapshot",
                    "snapshot_id": snapshot_id,
                    "selected_repositories": [repo.name for repo in repositories],
                    "activity_window": snapshot_activity_window,
                },
            )
            workflow.start("scan_repositories", {"source": "active_snapshot", "repository_count": len(repositories), "repository_names": [repo.name for repo in repositories], "fetch_latest": False})
            scan_failed = sum(1 for repo in repositories if repo.error)
            scan_output = {
                "process": "复用筛选阶段已经采集的 RepositoryReport，不 fetch、不 clone、不重新执行 git log。",
                "source": "active_snapshot",
                "total_repositories": len(repositories),
                "successful_repositories": len(repositories) - scan_failed,
                "failed_repositories": scan_failed,
                "commits_found": sum(len(repo.commits) for repo in repositories),
                "files_changed": sum(commit.files_changed for repo in repositories for commit in repo.commits),
                "repository_details": _repository_details(repositories),
            }
            scan_output.update({"operation": "reuse_snapshot", "snapshot_id": snapshot_id})
            if scan_failed:
                workflow.warning("scan_repositories", scan_output)
            else:
                workflow.skip("scan_repositories", scan_output)
    else:
        repository_configs = list(config.repositories)
        if workflow:
            workflow.start(
                "discover_repositories",
                {
                    "organization": config.github.organization if config.github else None,
                    "static_repositories": len(config.repositories),
                    "requested_repositories": repo_names or [],
                },
            )
        try:
            if config.github:
                discovered = discover_repositories(config.github)
                static_by_name = {repo.name: repo for repo in repository_configs}
                static_by_name.update({repo.name: repo for repo in discovered})
                repository_configs = list(static_by_name.values())
                logger.info("GitHub App 已发现 %d 个可访问仓库", len(discovered))

            if repo_names:
                repo_set = set(repo_names)
                repository_configs = [r for r in repository_configs if r.name in repo_set]
                logger.info("按名称过滤后剩余 %d 个仓库", len(repository_configs))

            if workflow:
                workflow.success(
                    "discover_repositories",
                    {
                        "process": "调用 GitHub App 发现可访问仓库，合并静态配置并按名称过滤。",
                        "discovered_repositories": len(repository_configs),
                        "selected_repositories": [repo.name for repo in repository_configs],
                        "fetch_enabled": not skip_fetch,
                    },
                )
        except Exception as error:
            if workflow:
                workflow.fail("discover_repositories", str(error))
            raise

        if skip_fetch:
            import dataclasses
            repository_configs = [dataclasses.replace(r, fetch=False) for r in repository_configs]
            logger.info("skip_fetch=True，跳过 git fetch/clone")

        repositories = []
        if workflow:
            workflow.start(
                "scan_repositories",
                {
                    "repository_count": len(repository_configs),
                    "workspace": str(workspace),
                    "repository_names": [repo.name for repo in repository_configs],
                    "fetch_latest": not skip_fetch,
                    "refs": "all" if all(not repo.branch for repo in repository_configs) else "configured",
                },
            )
        scan_failed = 0
        try:
            for index, repo_cfg in enumerate(repository_configs, start=1):
                result = scan_repository(
                    repo_cfg,
                    workspace,
                    target_date,
                    timezone,
                    end_date=_end,
                    allow_clone=not skip_fetch,
                )
                if result.error:
                    scan_failed += 1
                    logger.warning("仓库 %s 扫描失败: %s", repo_cfg.name, result.error)
                repositories.append(result)
                if workflow and hasattr(workflow, "repository_progress"):
                    workflow.repository_progress(index, len(repository_configs), repo_cfg.name, scan_failed)
            if workflow:
                scan_output = {
                    "process": "逐个仓库确保本地 mirror 可用，根据 fetch 配置同步 refs，再用一次 git log --numstat 解析提交。",
                    "total_repositories": len(repositories),
                    "successful_repositories": len(repositories) - scan_failed,
                    "failed_repositories": scan_failed,
                    "commits_found": sum(len(repo.commits) for repo in repositories),
                    "files_changed": sum(commit.files_changed for repo in repositories for commit in repo.commits),
                    "repository_details": _repository_details(repositories),
                }
                if scan_failed:
                    workflow.warning("scan_repositories", scan_output)
                else:
                    workflow.success("scan_repositories", scan_output)
        except Exception as error:
            if workflow:
                workflow.fail("scan_repositories", str(error))
            raise

    # Build the appropriate report object
    if workflow:
        workflow.start("aggregate_metrics", {"repository_reports": len(repositories), "repository_names": [repo.name for repo in repositories]})
    try:
        if report_type == "daily" and end_date is None:
            report: DailyReport | PeriodReport = DailyReport(
                target_date.isoformat(),
                datetime.now(timezone),
                repositories,
                member_mapping=member_mapping or {},
                organization=config.github.organization if config.github else "",
            )
        else:
            report = PeriodReport(
                report_type=report_type,
                period_start=target_date.isoformat(),
                period_end=_end.isoformat(),
                generated_at=datetime.now(timezone),
                repositories=repositories,
                member_mapping=member_mapping or {},
                organization=config.github.organization if config.github else "",
            )
        if workflow:
            workflow.success(
                "aggregate_metrics",
                {
                    "process": "在内存中按提交、仓库、贡献者和日期聚合统计，不访问 GitHub 或本地 Git。",
                    "scanned_repositories": report.scanned_repositories,
                    "active_repositories": report.active_repositories,
                    "empty_repositories": report.empty_repositories,
                    "failed_repositories": report.failed_repositories,
                    "contributors": report.contributor_count,
                    "commits": report.total_commits,
                    "files_changed": report.total_files_changed,
                    "additions": report.total_additions,
                    "deletions": report.total_deletions,
                    "trend_points": len(report.daily_trend),
                    "daily_trend": report.daily_trend,
                    "repository_details": _repository_details(repositories),
                    "top_contributors": _top_contributors(report),
                    "project_contributions": report.project_contributions,
                    "person_contributions": report.person_contributions,
                },
            )
    except Exception as error:
        if workflow:
            workflow.fail("aggregate_metrics", str(error))
        raise

    ai_context = build_context(report, config.ai.max_commits)
    ai_context_commits = context_commit_count(report, config.ai.max_commits)
    ai_prompt = build_prompt(report, config.ai.max_commits)
    if workflow:
        workflow.start(
            "ai_analysis",
            {
                "enabled": config.ai.enabled,
                "base_url": config.ai.base_url,
                "model": config.ai.model,
                "thinking_enabled": config.ai.thinking_enabled,
                "max_commits": config.ai.max_commits,
                "analysis_strategy": "yearly_project_batches" if report_type == "yearly" else "single_request",
                "yearly_project_batch_size": config.ai.yearly_project_batch_size if report_type == "yearly" else None,
                "yearly_project_batch_count": (
                    (len(report.project_contributions) + config.ai.yearly_project_batch_size - 1) // config.ai.yearly_project_batch_size
                    if report_type == "yearly" else 0
                ),
                "process": (
                    "年报先按项目批次分析，再基于批次结果生成全局汇总。"
                    if report_type == "yearly"
                    else "将宏观指标、趋势、仓库摘要和最多 max_commits 条提交明细组装为提示词，调用配置的 AI 模型。"
                ),
                "report_commits": report.total_commits,
                "context_commits": ai_context_commits,
                "omitted_commits": max(0, report.total_commits - ai_context_commits),
                "context_characters": len(ai_context),
                "context_preview": _text_preview(ai_context),
                "prompt_sources": context_source_summary(report, config.ai.max_commits),
                "system_prompt": SYSTEM_PROMPT,
                "user_prompt": ai_prompt,
                "prompt_characters": len(ai_prompt),
            },
        )
    try:
        yearly_stages = None
        if report_type == "yearly" and isinstance(report, PeriodReport):
            yearly_stages = analyze_yearly(
                report,
                config.ai,
                progress_callback=(
                    (lambda output: workflow.progress("ai_analysis", output))
                    if workflow else None
                ),
            )
            raw_ai_analysis = yearly_stages["raw_response"]
        else:
            raw_ai_analysis = analyze(report, config.ai, prompt=ai_prompt)
        report.ai_analysis, report.project_analyses, structured_ai = parse_analysis_response(raw_ai_analysis, report)
    except Exception as error:
        if workflow:
            workflow.fail("ai_analysis", str(error))
        raise
    ai_degraded = (
        not config.ai.enabled
        or not config.ai.api_key
        or "AI 分析调用失败" in report.ai_analysis
        or "本地规则摘要" in report.ai_analysis
        or not structured_ai
        or bool(yearly_stages and yearly_stages.get("degraded"))
    )
    if workflow:
        context_commits = ai_context_commits
        ai_output = {
            "process": (
                "年报已完成项目分批分析和全局汇总，并校验逐项目结构化结果。"
                if yearly_stages
                else "AI 返回全局 Markdown 和逐项目结构化分析后进行校验；缺失项目使用证据不足降级项。"
            ),
            "characters": len(report.ai_analysis),
            "degraded": ai_degraded,
            "structured_response": structured_ai,
            "project_analyses": report.project_analyses,
            "project_analysis_count": len(report.project_analyses),
            "report_commits": report.total_commits,
            "context_commits": context_commits,
            "omitted_commits": max(0, report.total_commits - context_commits),
            "context_characters": len(ai_context),
            "analysis": report.ai_analysis,
        }
        if yearly_stages:
            ai_output["analysis_stages"] = {
                "strategy": yearly_stages.get("strategy"),
                "batch_size": yearly_stages.get("batch_size"),
                "batch_count": yearly_stages.get("batch_count"),
                "degraded": yearly_stages.get("degraded"),
                "batches": yearly_stages.get("batches", []),
                "synthesis": yearly_stages.get("synthesis", {}),
                "synthesis_prompt": yearly_stages.get("synthesis_prompt", ""),
            }
            ai_output["prompt_sources"] = yearly_stages.get("global_prompt_sources", [])
        if ai_degraded:
            workflow.warning("ai_analysis", ai_output)
        else:
            workflow.success("ai_analysis", ai_output)

    if workflow:
        workflow.start("render_report", {"process": "将报告对象渲染为 Markdown 和 HTML，并写入 Markdown 文件。", "template": "unified-period-v4", "report_type": report_type, "repository_count": report.scanned_repositories, "total_commits": report.total_commits})
    try:
        report.trend_chart_png = render_trend_chart(report)
        if isinstance(report, DailyReport):
            markdown = render_markdown(report)
            html = render_html(report)
        else:
            markdown = render_period_markdown(report)
            html = render_period_html(report)

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        suffix = f"{target_date.isoformat()}"
        if _end != target_date:
            suffix = f"{target_date.isoformat()}_{_end.isoformat()}"
        output_path = Path(output_dir) / f"{report_type}_{suffix}.md"
        output_path.write_text(markdown, encoding="utf-8")
        if workflow:
            workflow.success(
                "render_report",
                {
                    "markdown_characters": len(markdown),
                    "html_characters": len(html),
                    "output_path": str(output_path),
                    "sections": REPORT_TOP_LEVEL_SECTION_COUNT,
                    "repository_sections": len(report.repositories),
                    "trend_chart": bool(report.trend_chart_png),
                    "process": "报告内容已生成并持久化 Markdown 文件，HTML 同时写入报告历史。",
                },
            )
    except Exception as error:
        if workflow:
            workflow.fail("render_report", str(error))
        raise

    if dry_run:
        logger.info("dry-run 已完成，报告写入 %s", output_path)
        print(markdown)
        if workflow:
            workflow.skip("send_email", {"process": "dry_run 模式只保存报告，不建立 SMTP 连接。", "reason": "dry_run", "recipients": 0})
    else:
        to_list = recipients if recipients else list(config.email.recipients)
        if not to_list:
            logger.warning("未配置收件人，跳过邮件发送")
            if workflow:
                workflow.skip("send_email", {"process": "没有可用收件人，因此跳过 SMTP 发送。", "reason": "no_recipients", "recipients": 0})
        else:
            if workflow:
                workflow.start(
                    "send_email",
                    {"process": "建立 SMTP 连接，按收件人配置发送纯文本和 HTML 两种 MIME alternative。", "recipient_count": len(to_list), "smtp_host": config.email.host, "subject_prefix": config.subject_prefix},
                )
            total = report.total_commits
            subject = format_report_title(
                report_type,
                target_date,
                _end,
                config.github.organization if config.github else "",
            )
            from .config import EmailConfig
            email_cfg = config.email
            if recipients:
                email_cfg = EmailConfig(
                    host=config.email.host,
                    port=config.email.port,
                    username=config.email.username,
                    password=config.email.password,
                    sender=config.email.sender,
                    recipients=tuple(recipients),
                    use_tls=config.email.use_tls,
                    use_ssl=config.email.use_ssl,
                )
            try:
                send_email(
                    email_cfg,
                    subject,
                    markdown,
                    html,
                    inline_images={"trend-chart": report.trend_chart_png} if report.trend_chart_png else None,
                )
            except Exception as error:
                if workflow:
                    workflow.fail("send_email", str(error))
                raise
            if workflow:
                workflow.success("send_email", {"process": "SMTP 已成功接受邮件，报告历史随后记录 email_sent_at。", "recipient_count": len(to_list), "subject": subject})
            logger.info("报告邮件已发送至 %s", ", ".join(to_list))

    return report


def _next_run(config: AppConfig, timezone: ZoneInfo) -> datetime:
    hour, minute = (int(value) for value in config.run_at.split(":", 1))
    now = datetime.now(timezone)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def run_scheduler(config: AppConfig) -> None:
    timezone = ZoneInfo(config.timezone)
    logger.info("调度器启动，每天 %s (%s) 运行", config.run_at, config.timezone)
    _consecutive_failures = 0
    while True:
        next_run = _next_run(config, timezone)
        wait_seconds = max(1, (next_run - datetime.now(timezone)).total_seconds())
        logger.info("下次运行时间：%s", next_run.isoformat())
        time_module.sleep(wait_seconds)
        try:
            run_once(config, next_run.date() - timedelta(days=1))
            _consecutive_failures = 0
        except Exception:
            _consecutive_failures += 1
            logger.exception("日报运行失败（连续第 %d 次）", _consecutive_failures)
            if _consecutive_failures >= 3:
                logger.critical("日报已连续失败 %d 次，请检查配置和网络", _consecutive_failures)


def main() -> None:
    parser = argparse.ArgumentParser(description="Git 每日提交与 AI 分析日报")
    parser.add_argument("--config", default="config.toml", help="TOML 配置文件")
    parser.add_argument("--once", action="store_true", help="立即运行一次")
    parser.add_argument("--date", help="日报日期，格式 YYYY-MM-DD；默认昨天")
    parser.add_argument("--end-date", help="结束日期（用于周报/月报），格式 YYYY-MM-DD")
    parser.add_argument("--report-type", default="daily", choices=["daily", "weekly", "monthly", "yearly"], help="报告类型")
    parser.add_argument("--dry-run", action="store_true", help="不发邮件，仅输出日报")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    if args.once:
        config_today = datetime.now(ZoneInfo(config.timezone)).date()
        target_date = date.fromisoformat(args.date) if args.date else config_today - timedelta(days=1)
        end_date = date.fromisoformat(args.end_date) if args.end_date else None
        run_once(config, target_date, end_date=end_date, report_type=args.report_type, dry_run=args.dry_run)
    else:
        run_scheduler(config)


if __name__ == "__main__":
    main()
