"""Database backup service with rotation."""

from __future__ import annotations
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import BACKUP_DIR, MAX_BACKUPS, DATA_DIR
from app.database.engine import get_current_db_path, dispose_engine, init_db
from app.services.audit_service import log_action
from app.constants import AuditAction
from app.logger import get_logger

logger = get_logger(__name__)


def _copy_sqlite_database(source: Path, destination: Path) -> None:
    """Create a transactionally consistent copy of a SQLite database."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_conn:
        with sqlite3.connect(destination) as dest_conn:
            source_conn.backup(dest_conn)


def create_backup() -> Path | None:
    """Create a backup of the current database. Returns path to backup file."""
    db_path = get_current_db_path()
    if not db_path or not db_path.exists():
        return None

    BACKUP_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"
    backup_path = BACKUP_DIR / backup_name

    _copy_sqlite_database(db_path, backup_path)

    # Rotation: keep only MAX_BACKUPS most recent
    _rotate_backups(db_path.stem)

    try:
        log_action(AuditAction.BACKUP.value, "database", None, str(backup_path))
    except Exception:
        logger.warning("Audit log failed for backup", exc_info=True)

    return backup_path


def _rotate_backups(db_stem: str):
    """Keep only MAX_BACKUPS most recent backups for a given DB name."""
    pattern = f"{db_stem}_backup_*"
    backups = sorted(BACKUP_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    for old in backups[MAX_BACKUPS:]:
        old.unlink(missing_ok=True)


def list_backups() -> list[dict]:
    """List all backup files."""
    BACKUP_DIR.mkdir(exist_ok=True)
    backups = sorted(BACKUP_DIR.glob("*_backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for b in backups:
        result.append({
            "name": b.name,
            "path": str(b),
            "size": b.stat().st_size,
            "modified": datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return result


def restore_backup(backup_path: Path) -> None:
    """Restore database from a backup file.

    1. Dispose engine to release the DB file (Windows lock)
    2. Copy backup over the current DB
    3. Re-init the database
    4. Publish database_changed event
    5. Log the restore action
    """
    db_path = get_current_db_path()
    if not db_path:
        raise RuntimeError("No active database to restore to")

    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    try:
        dispose_engine()
        shutil.copy2(backup_path, db_path)
        init_db(db_path)
    except Exception:
        init_db(db_path)
        raise

    from app.event_bus import event_bus
    event_bus.publish("database_changed")

    try:
        log_action(AuditAction.RESTORE.value, "database", None,
                   f"Restored from: {backup_path.name}")
    except Exception:
        logger.warning("Audit log failed for restore", exc_info=True)

    logger.info("Database restored from %s", backup_path.name)


def list_databases() -> list[dict]:
    """List all database files in the data directory."""
    DATA_DIR.mkdir(exist_ok=True)
    dbs = sorted(DATA_DIR.glob("*.db"))
    result = []
    for db in dbs:
        result.append({
            "name": db.name,
            "path": str(db),
            "size": db.stat().st_size,
        })
    return result
