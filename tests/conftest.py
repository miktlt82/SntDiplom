"""Shared test fixtures — in-memory SQLite, patched session, seed data."""

from __future__ import annotations
import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from app.database.base import Base
import app.database.models  # noqa: register all models
from app.database.models.member import Member
from app.database.models.membership_fee import MembershipFeePeriod, MembershipFeePayment
from app.database.models.target_fee import TargetFeeCampaign, TargetFeePayment
from app.database.models.electricity import ElectricityTariff, MeterReading, ElectricityPayment
from app.constants import MemberStatus


def _enable_fk(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture()
def db_engine():
    """Create a fresh in-memory SQLite engine for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    event.listen(engine, "connect", _enable_fk)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session_factory(db_engine):
    """Session factory bound to the in-memory engine."""
    return sessionmaker(bind=db_engine)


@pytest.fixture()
def session(db_session_factory):
    """A single session that is rolled back after the test."""
    sess = db_session_factory()
    yield sess
    sess.close()


@pytest.fixture(autouse=True)
def _patch_engine(db_engine, db_session_factory):
    """Patch the engine module so services use the in-memory database."""
    with patch("app.database.engine._engine", db_engine), \
         patch("app.database.engine._session_factory", db_session_factory):
        yield


@pytest.fixture()
def seed_members(session):
    """Create 3 test members."""
    members = [
        Member(
            plot_number="001", last_name="Иванов", first_name="Иван",
            patronymic="Иванович", plot_area=Decimal("6"), status=MemberStatus.ACTIVE.value,
        ),
        Member(
            plot_number="002", last_name="Петров", first_name="Пётр",
            plot_area=Decimal("10"), status=MemberStatus.ACTIVE.value,
        ),
        Member(
            plot_number="003", last_name="Сидоров", first_name="Сидор",
            plot_area=Decimal("8"), status=MemberStatus.ARCHIVED.value,
        ),
    ]
    session.add_all(members)
    session.commit()
    return members


@pytest.fixture()
def seed_period(session):
    """Create a membership fee period."""
    period = MembershipFeePeriod(
        name="Взносы 2025", year=2025,
        rate_per_sotka=Decimal("500.00"),
        due_date=date(2025, 7, 1),
        penalty_daily_rate=Decimal("0.001"),
    )
    session.add(period)
    session.commit()
    return period


@pytest.fixture()
def seed_tariff(session):
    """Create an electricity tariff."""
    tariff = ElectricityTariff(
        name="Тариф 2025",
        rate_per_kwh=Decimal("5.50"),
        effective_from=date(2025, 1, 1),
        is_active=True,
    )
    session.add(tariff)
    session.commit()
    return tariff
