"""Audit logging service."""

from __future__ import annotations
from app.database.engine import db_session, get_active_session
from app.database.models.audit_log import AuditLog
from app.logger import get_logger

logger = get_logger(__name__)


def log_action(
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    details: str | None = None,
) -> None:
    try:
        entry = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )

        active_session = get_active_session()
        if active_session is not None:
            active_session.add(entry)
            return

        with db_session() as session:
            session.add(entry)
    except Exception:
        logger.warning("Audit log failed: %s %s", action, entity_type, exc_info=True)
