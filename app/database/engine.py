"""Database engine management and session factory."""

from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from app.config import DEFAULT_DB_PATH
from app.database.base import Base

_engine = None
_session_factory: sessionmaker[Session] | None = None


def _enable_foreign_keys(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine():
    global _engine
    if _engine is None:
        init_db(DEFAULT_DB_PATH)
    return _engine


def get_session() -> Session:
    global _session_factory
    if _session_factory is None:
        init_db(DEFAULT_DB_PATH)
    return _session_factory()


@contextmanager
def db_session(readonly: bool = False):
    """Context manager that commits/rollbacks/closes a session automatically."""
    session = get_session()
    try:
        yield session
        if not readonly:
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """Dispose the engine, releasing the DB file (needed for backup restore on Windows)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _session_factory = None


def init_db(db_path: Path | str) -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(f"sqlite:///{db_path}", echo=False)
    event.listen(_engine, "connect", _enable_foreign_keys)
    _session_factory = sessionmaker(bind=_engine)

    # Import all models to ensure they're registered
    import app.database.models  # noqa: F401

    Base.metadata.create_all(_engine)


def switch_database(db_path: Path | str) -> None:
    """Switch to a different database file."""
    init_db(db_path)
    from app.event_bus import event_bus
    event_bus.publish("database_changed")


def get_current_db_path() -> Path | None:
    if _engine is None:
        return None
    url = str(_engine.url)
    # sqlite:///path
    return Path(url.replace("sqlite:///", ""))
