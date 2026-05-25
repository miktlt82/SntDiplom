"""Tests for electricity calculator service."""

from __future__ import annotations
from datetime import date
from decimal import Decimal

import pytest

from app.database.models.electricity import (
    ElectricityTariff, MeterReading, ElectricityPayment
)
from app.database.models.payment_history import PaymentHistory
from app.services.electricity_calculator import (
    calculate_consumption,
    create_monthly_electricity_readings,
    detect_anomaly,
    get_active_tariff,
    get_month_bounds,
    record_electricity_payment,
    create_reading_and_payment,
)


class TestCalculateConsumption:
    def test_normal(self):
        assert calculate_consumption(Decimal("200"), Decimal("100")) == Decimal("100")

    def test_zero_difference(self):
        assert calculate_consumption(Decimal("100"), Decimal("100")) == Decimal("0")

    def test_negative_clipped_to_zero(self):
        """If current < previous (meter reset), consumption should be 0."""
        assert calculate_consumption(Decimal("50"), Decimal("100")) == Decimal("0")


class TestDetectAnomaly:
    def test_normal_consumption(self):
        assert detect_anomaly(Decimal("100"), Decimal("90")) is False

    def test_anomaly_detected(self):
        # 300 > 90 * 3 = 270
        assert detect_anomaly(Decimal("300"), Decimal("90")) is True

    def test_exactly_threshold(self):
        # 270 is not > 270
        assert detect_anomaly(Decimal("270"), Decimal("90")) is False

    def test_zero_average(self):
        assert detect_anomaly(Decimal("100"), Decimal("0")) is False

    def test_custom_threshold(self):
        assert detect_anomaly(Decimal("200"), Decimal("90"), Decimal("2")) is True
        assert detect_anomaly(Decimal("180"), Decimal("90"), Decimal("2")) is False


class TestActiveTariff:
    def test_uses_tariff_effective_for_reading_date(self, session):
        old = ElectricityTariff(
            name="Старый",
            rate_per_kwh=Decimal("5.00"),
            effective_from=date(2025, 1, 1),
            effective_to=date(2025, 3, 31),
            is_active=True,
        )
        new = ElectricityTariff(
            name="Новый",
            rate_per_kwh=Decimal("6.00"),
            effective_from=date(2025, 4, 1),
            is_active=True,
        )
        session.add_all([old, new])
        session.commit()

        assert get_active_tariff(session, date(2025, 2, 15)).id == old.id
        assert get_active_tariff(session, date(2025, 4, 15)).id == new.id


class TestMonthBounds:
    def test_regular_month(self):
        assert get_month_bounds(2025, 4) == (date(2025, 4, 1), date(2025, 4, 30))

    def test_leap_february(self):
        assert get_month_bounds(2024, 2) == (date(2024, 2, 1), date(2024, 2, 29))


class TestCreateReadingAndPayment:
    def test_first_reading_no_payment(self, session, seed_members, seed_tariff):
        """First reading has no previous — no consumption, no payment."""
        member = seed_members[0]
        result = create_reading_and_payment(member.id, date(2025, 1, 15), Decimal("100"))

        assert result["reading_id"] is not None
        assert result["previous_value"] is None
        assert result["consumption"] is None
        assert result["payment_id"] is None

    def test_second_reading_creates_payment(self, session, seed_members, seed_tariff):
        """Second reading calculates consumption and creates payment."""
        member = seed_members[0]
        create_reading_and_payment(member.id, date(2025, 1, 15), Decimal("100"))
        result = create_reading_and_payment(member.id, date(2025, 2, 15), Decimal("250"))

        assert result["previous_value"] == Decimal("100")
        assert result["consumption"] == Decimal("150")
        assert result["payment_id"] is not None
        # 150 kWh * 5.50 = 825.00
        assert result["amount_due"] == Decimal("825.00")

    def test_payment_amount_due(self, session, seed_members, seed_tariff):
        """Verify the ElectricityPayment record is created correctly."""
        member = seed_members[0]
        create_reading_and_payment(member.id, date(2025, 1, 1), Decimal("0"))
        result = create_reading_and_payment(member.id, date(2025, 2, 1), Decimal("200"))

        payment = session.get(ElectricityPayment, result["payment_id"])
        assert payment is not None
        assert payment.consumption_kwh == Decimal("200")
        assert payment.rate_per_kwh == Decimal("5.50")
        assert payment.amount_due == Decimal("1100.00")
        assert payment.amount_paid == Decimal("0")

    def test_zero_consumption_no_payment(self, session, seed_members, seed_tariff):
        """Zero consumption should not create a payment."""
        member = seed_members[0]
        create_reading_and_payment(member.id, date(2025, 1, 1), Decimal("100"))
        result = create_reading_and_payment(member.id, date(2025, 2, 1), Decimal("100"))

        assert result["consumption"] == Decimal("0")
        assert result["payment_id"] is None


class TestMonthlyElectricityReadings:
    def test_first_month_creates_baseline_without_payment(self, session, seed_members, seed_tariff):
        member = seed_members[0]

        result = create_monthly_electricity_readings(
            2025, 1, {member.id: Decimal("100")}
        )

        readings = session.query(MeterReading).filter(
            MeterReading.member_id == member.id
        ).all()
        payments = session.query(ElectricityPayment).filter(
            ElectricityPayment.member_id == member.id
        ).all()
        assert result["created_readings"] == 1
        assert result["baseline_readings"] == 1
        assert len(readings) == 1
        assert readings[0].reading_date == date(2025, 1, 31)
        assert payments == []

    def test_second_month_creates_monthly_charge(self, session, seed_members, seed_tariff):
        member = seed_members[0]
        create_monthly_electricity_readings(2025, 1, {member.id: Decimal("100")})

        result = create_monthly_electricity_readings(
            2025, 2, {member.id: Decimal("250")}
        )

        payment = session.query(ElectricityPayment).filter(
            ElectricityPayment.member_id == member.id
        ).one()
        assert result["created_payments"] == 1
        assert payment.period_start == date(2025, 2, 1)
        assert payment.period_end == date(2025, 2, 28)
        assert payment.consumption_kwh == Decimal("150.00")
        assert payment.amount_due == Decimal("825.00")

    def test_reentering_month_updates_charge_and_preserves_paid(self, session, seed_members, seed_tariff):
        member = seed_members[0]
        create_monthly_electricity_readings(2025, 1, {member.id: Decimal("100")})
        create_monthly_electricity_readings(2025, 2, {member.id: Decimal("250")})
        payment = session.query(ElectricityPayment).filter(
            ElectricityPayment.member_id == member.id
        ).one()
        payment.amount_paid = Decimal("100")
        session.commit()

        result = create_monthly_electricity_readings(
            2025, 2, {member.id: Decimal("260")}
        )

        updated = session.get(ElectricityPayment, payment.id)
        assert result["updated_readings"] == 1
        assert result["updated_payments"] == 1
        assert updated.consumption_kwh == Decimal("160.00")
        assert updated.amount_due == Decimal("880.00")
        assert updated.amount_paid == Decimal("100.00")

    def test_record_payment_writes_history(self, session, seed_members, seed_tariff):
        member = seed_members[0]
        create_monthly_electricity_readings(2025, 1, {member.id: Decimal("100")})
        create_monthly_electricity_readings(2025, 2, {member.id: Decimal("250")})
        payment = session.query(ElectricityPayment).filter(
            ElectricityPayment.member_id == member.id
        ).one()

        record_electricity_payment(payment.id, Decimal("300"), date(2025, 3, 5))

        session.expire_all()
        updated = session.get(ElectricityPayment, payment.id)
        history = session.query(PaymentHistory).filter(
            PaymentHistory.payment_type == "electricity",
            PaymentHistory.payment_id == payment.id,
        ).one()
        assert updated.amount_paid == Decimal("300.00")
        assert updated.payment_date == date(2025, 3, 5)
        assert history.amount == Decimal("300.00")

    def test_missing_tariff_only_blocks_charge_not_baseline(self, session, seed_members):
        member = seed_members[0]

        baseline = create_monthly_electricity_readings(
            2025, 1, {member.id: Decimal("100")}
        )
        charge = create_monthly_electricity_readings(
            2025, 2, {member.id: Decimal("250")}
        )

        assert baseline["missing_tariff"] is False
        assert charge["missing_tariff"] is True
        assert session.query(ElectricityPayment).count() == 0
