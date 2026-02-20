"""Tests for electricity calculator service."""

from __future__ import annotations
from datetime import date
from decimal import Decimal

import pytest

from app.database.models.electricity import MeterReading, ElectricityPayment
from app.services.electricity_calculator import (
    calculate_consumption,
    detect_anomaly,
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
