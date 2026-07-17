from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, event
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
    logger.info("数据库已初始化: %s", path.resolve())

    _seed_default_admin()


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
