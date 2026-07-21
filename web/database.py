from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger("hlb-git-pm.database")

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    pass


def init_db(db_path: str = ".data/hlb-git-pm.db") -> None:
    global _engine, _SessionLocal
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path.resolve()}"
    _engine = create_engine(url, echo=False, connect_args={"check_same_thread": False})

    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)

    from . import db_models  # noqa: F401 — ensure tables are registered

    Base.metadata.create_all(bind=_engine)
    _ensure_compat_columns()
    logger.info("数据库已初始化: %s", path.resolve())

    _seed_default_admin()


def _ensure_compat_columns() -> None:
    """Add lightweight columns for installations initialized via create_all."""
    inspector = inspect(_engine)
    report_columns = {column["name"] for column in inspector.get_columns("report_history")}
    if "selection_snapshot_id" not in report_columns:
        with _engine.begin() as connection:
            connection.execute(text("ALTER TABLE report_history ADD COLUMN selection_snapshot_id INTEGER"))
        logger.info("已补充 report_history.selection_snapshot_id 列")
    if "project_analysis_json" not in report_columns:
        with _engine.begin() as connection:
            connection.execute(text("ALTER TABLE report_history ADD COLUMN project_analysis_json TEXT NOT NULL DEFAULT '[]'"))
        logger.info("已补充 report_history.project_analysis_json 列")
    if "trend_chart_png" not in report_columns:
        with _engine.begin() as connection:
            connection.execute(text("ALTER TABLE report_history ADD COLUMN trend_chart_png BLOB"))
        logger.info("已补充 report_history.trend_chart_png 列")
    if "email_recipients_json" not in report_columns:
        with _engine.begin() as connection:
            connection.execute(text("ALTER TABLE report_history ADD COLUMN email_recipients_json TEXT NOT NULL DEFAULT '[]'"))
        logger.info("已补充 report_history.email_recipients_json 列")

    sync_columns = {column["name"] for column in inspector.get_columns("sync_jobs")}
    if "details_json" not in sync_columns:
        with _engine.begin() as connection:
            connection.execute(text("ALTER TABLE sync_jobs ADD COLUMN details_json TEXT NOT NULL DEFAULT '{}'"))
        logger.info("已补充 sync_jobs.details_json 列")

    member_columns = {column["name"] for column in inspector.get_columns("members")}
    if "is_outsourced" not in member_columns:
        with _engine.begin() as connection:
            connection.execute(text("ALTER TABLE members ADD COLUMN is_outsourced BOOLEAN NOT NULL DEFAULT 0"))
            connection.execute(text("UPDATE members SET is_outsourced = 1 WHERE substr(lower(trim(real_name)), 1, 2) = 'v_'"))
        logger.info("已补充 members.is_outsourced 列，并按 v_ 姓名完成初始标记")


def get_engine():
    if _engine is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    return _engine


def get_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    return _SessionLocal()


def _seed_default_admin() -> None:
    from .db_models import User

    session = get_session()
    try:
        if session.query(User).count() == 0:
            import bcrypt as _bcrypt

            pw_hash = _bcrypt.hashpw(b"admin123", _bcrypt.gensalt()).decode("utf-8")
            admin = User(
                username="admin",
                password_hash=pw_hash,
                display_name="管理员",
                is_active=True,
            )
            session.add(admin)
            session.commit()
            logger.info("已创建默认管理员账号: admin / admin123")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
