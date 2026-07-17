from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.workflow import STEP_PLAN

from .database import get_session
from .db_models import ReportStep

logger = logging.getLogger("hlb-git-pm.report_steps")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


class DbWorkflowReporter:
    """Persist workflow state without letting observability break a report run."""

    def __init__(self, run_id: int):
        self.run_id = run_id
        self._started_at: dict[str, float] = {}
        self._ensure_plan()

    def _ensure_plan(self) -> None:
        session = get_session()
        try:
            existing = {row.step_key for row in session.query(ReportStep).filter(ReportStep.run_id == self.run_id).all()}
            for sequence, (step_key, step_name) in enumerate(STEP_PLAN, start=1):
                if step_key not in existing:
                    session.add(
                        ReportStep(
                            run_id=self.run_id,
                            step_key=step_key,
                            step_name=step_name,
                            sequence=sequence,
                            status="pending",
                            progress=0,
                        )
                    )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("初始化报告步骤失败 run_id=%s", self.run_id)
        finally:
            session.close()

    def _get(self, session, step_key: str) -> ReportStep:
        row = (
            session.query(ReportStep)
            .filter(ReportStep.run_id == self.run_id, ReportStep.step_key == step_key)
            .first()
        )
        if row is None:
            row = ReportStep(run_id=self.run_id, step_key=step_key, step_name=step_key, sequence=999, status="pending", progress=0)
            session.add(row)
            session.flush()
        return row

    def _update(
        self,
        step_key: str,
        *,
        status: str | None = None,
        input_summary: dict[str, Any] | None = None,
        output_summary: dict[str, Any] | None = None,
        error: str | None = None,
        progress: int | None = None,
    ) -> None:
        try:
            session = get_session()
            try:
                row = self._get(session, step_key)
                if status is not None:
                    row.status = status
                if input_summary is not None:
                    row.input_summary = _json(input_summary)
                if output_summary is not None:
                    row.output_summary = _json(output_summary)
                if error is not None:
                    row.error = error[:4000]
                if progress is not None:
                    row.progress = max(0, min(100, progress))
                if status == "running":
                    row.started_at = row.started_at or _now()
                if status in {"success", "warning", "failed", "skipped"}:
                    row.finished_at = _now()
                    if row.started_at:
                        try:
                            started = datetime.fromisoformat(row.started_at).timestamp()
                            row.duration_ms = max(0, int((time.time() - started) * 1000))
                        except ValueError:
                            pass
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception:
            logger.exception("更新报告步骤失败 run_id=%s step=%s", self.run_id, step_key)

    def start(self, step_key: str, input_summary: dict[str, Any] | None = None) -> None:
        self._started_at[step_key] = time.time()
        self._update(step_key, status="running", input_summary=input_summary, progress=0)

    def progress(self, step_key: str, output_summary: dict[str, Any]) -> None:
        progress = output_summary.get("progress")
        self._update(step_key, output_summary=output_summary, progress=int(progress) if isinstance(progress, int) else None)

    def success(self, step_key: str, output_summary: dict[str, Any] | None = None) -> None:
        self._update(step_key, status="success", output_summary=output_summary, progress=100)

    def warning(self, step_key: str, output_summary: dict[str, Any] | None = None) -> None:
        self._update(step_key, status="warning", output_summary=output_summary, progress=100)

    def skip(self, step_key: str, output_summary: dict[str, Any] | None = None) -> None:
        self._update(step_key, status="skipped", output_summary=output_summary, progress=100)

    def fail(self, step_key: str, error: str) -> None:
        self._update(step_key, status="failed", error=error, progress=100)

    def repository_progress(self, completed: int, total: int, last_repository: str, failed: int) -> None:
        progress = int(completed * 100 / total) if total else 100
        self.progress(
            "scan_repositories",
            {
                "progress": progress,
                "completed_repositories": completed,
                "total_repositories": total,
                "last_repository": last_repository,
                "failed_repositories": failed,
            },
        )
