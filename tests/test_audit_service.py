"""Tests for audit logging."""

from __future__ import annotations

from app.database.engine import db_session
from app.database.models.audit_log import AuditLog
from app.services.audit_service import log_action


def test_log_action_without_active_session(session):
    log_action("create", "member", 1, "standalone")

    entry = session.query(AuditLog).filter_by(details="standalone").one()
    assert entry.action == "create"
    assert entry.entity_type == "member"


def test_log_action_reuses_active_session(session, monkeypatch):
    def fail_db_session(*args, **kwargs):
        raise AssertionError("log_action opened a second session")

    monkeypatch.setattr("app.services.audit_service.db_session", fail_db_session)

    with db_session() as outer:
        log_action("create", "member", 2, "same transaction")
        assert outer.query(AuditLog).filter_by(details="same transaction").count() == 1

    entry = session.query(AuditLog).filter_by(details="same transaction").one()
    assert entry.entity_id == 2
