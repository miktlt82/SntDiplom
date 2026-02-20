"""Electricity calculation service."""

from __future__ import annotations
from datetime import date
from decimal import Decimal

from app.database.engine import db_session
from app.database.models.electricity import (
    ElectricityTariff, MeterReading, ElectricityPayment
)


def get_active_tariff(session, as_of: date | None = None) -> ElectricityTariff | None:
    if as_of is None:
        as_of = date.today()
    return session.query(ElectricityTariff).filter(
        ElectricityTariff.is_active == True,
        ElectricityTariff.effective_from <= as_of,
    ).order_by(ElectricityTariff.effective_from.desc()).first()


def get_previous_reading(session, member_id: int, before_date: date) -> MeterReading | None:
    return session.query(MeterReading).filter(
        MeterReading.member_id == member_id,
        MeterReading.reading_date < before_date,
    ).order_by(MeterReading.reading_date.desc()).first()


def calculate_consumption(current: Decimal, previous: Decimal) -> Decimal:
    diff = current - previous
    return max(diff, Decimal("0"))


def detect_anomaly(consumption: Decimal, avg_consumption: Decimal,
                   threshold_factor: Decimal = Decimal("3")) -> bool:
    """Return True if consumption is anomalously high."""
    if avg_consumption <= 0:
        return False
    return consumption > avg_consumption * threshold_factor


def get_average_consumption(session, member_id: int, last_n: int = 6) -> Decimal:
    readings = session.query(MeterReading).filter(
        MeterReading.member_id == member_id,
        MeterReading.consumption.isnot(None),
        MeterReading.consumption > 0,
    ).order_by(MeterReading.reading_date.desc()).limit(last_n).all()

    if not readings:
        return Decimal("0")
    total = sum(r.consumption for r in readings)
    return (total / len(readings)).quantize(Decimal("0.01"))


def create_reading_and_payment(
    member_id: int,
    reading_date: date,
    value: Decimal,
) -> dict:
    """Create a meter reading, auto-fill previous, calculate consumption and payment.
    Returns dict with info about the operation.
    """
    with db_session() as session:
        prev = get_previous_reading(session, member_id, reading_date)
        previous_value = prev.value if prev else None
        consumption = calculate_consumption(value, previous_value) if previous_value is not None else None

        reading = MeterReading(
            member_id=member_id,
            reading_date=reading_date,
            value=value,
            previous_value=previous_value,
            consumption=consumption,
        )
        session.add(reading)
        session.flush()

        result = {
            "reading_id": reading.id,
            "previous_value": previous_value,
            "consumption": consumption,
            "anomaly": False,
            "payment_id": None,
            "amount_due": None,
        }

        if consumption is not None and consumption > 0:
            avg = get_average_consumption(session, member_id)
            result["anomaly"] = detect_anomaly(consumption, avg)

            tariff = get_active_tariff(session, reading_date)
            if tariff:
                amount = (consumption * tariff.rate_per_kwh).quantize(Decimal("0.01"))
                period_start = prev.reading_date if prev else reading_date
                payment = ElectricityPayment(
                    member_id=member_id,
                    reading_id=reading.id,
                    period_start=period_start,
                    period_end=reading_date,
                    consumption_kwh=consumption,
                    rate_per_kwh=tariff.rate_per_kwh,
                    amount_due=amount,
                    amount_paid=Decimal("0"),
                )
                session.add(payment)
                session.flush()
                result["payment_id"] = payment.id
                result["amount_due"] = amount

        return result
