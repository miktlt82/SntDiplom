"""Electricity calculation service."""

from __future__ import annotations
import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy import or_

from app.database.engine import db_session
from app.database.models.electricity import (
    ElectricityTariff, MeterReading, ElectricityPayment
)
from app.database.models.payment_history import PaymentHistory


def get_active_tariff(session, as_of: date | None = None) -> ElectricityTariff | None:
    if as_of is None:
        as_of = date.today()
    return session.query(ElectricityTariff).filter(
        ElectricityTariff.is_active.is_(True),
        ElectricityTariff.effective_from <= as_of,
        or_(
            ElectricityTariff.effective_to.is_(None),
            ElectricityTariff.effective_to >= as_of,
        ),
    ).order_by(ElectricityTariff.effective_from.desc()).first()


def get_previous_reading(session, member_id: int, before_date: date) -> MeterReading | None:
    return session.query(MeterReading).filter(
        MeterReading.member_id == member_id,
        MeterReading.reading_date < before_date,
    ).order_by(MeterReading.reading_date.desc()).first()


def get_month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return first and last day for a billing month."""
    if not (1 <= month <= 12):
        raise ValueError("Некорректный месяц")
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def get_reading_for_month(
    session,
    member_id: int,
    period_start: date,
    period_end: date,
) -> MeterReading | None:
    """Return the member reading already recorded inside the billing month."""
    return session.query(MeterReading).filter(
        MeterReading.member_id == member_id,
        MeterReading.reading_date >= period_start,
        MeterReading.reading_date <= period_end,
    ).order_by(MeterReading.reading_date.desc(), MeterReading.id.desc()).first()


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


def create_monthly_electricity_readings(
    year: int,
    month: int,
    readings_by_member: dict[int, Decimal],
) -> dict:
    """Create or update readings and monthly charges for a billing month."""
    period_start, period_end = get_month_bounds(year, month)
    result = {
        "created_readings": 0,
        "updated_readings": 0,
        "created_payments": 0,
        "updated_payments": 0,
        "baseline_readings": 0,
        "missing_tariff": False,
        "anomalies": [],
    }

    with db_session() as session:
        tariff = get_active_tariff(session, period_end)

        for member_id, raw_value in readings_by_member.items():
            value = Decimal(raw_value).quantize(Decimal("0.01"))
            previous = get_previous_reading(session, member_id, period_start)
            previous_value = previous.value if previous else None
            consumption = (
                calculate_consumption(value, previous_value)
                if previous_value is not None else None
            )

            reading = get_reading_for_month(
                session, member_id, period_start, period_end
            )
            if reading:
                reading.reading_date = period_end
                reading.value = value
                reading.previous_value = previous_value
                reading.consumption = consumption
                result["updated_readings"] += 1
            else:
                reading = MeterReading(
                    member_id=member_id,
                    reading_date=period_end,
                    value=value,
                    previous_value=previous_value,
                    consumption=consumption,
                )
                session.add(reading)
                session.flush()
                result["created_readings"] += 1

            payment = session.query(ElectricityPayment).filter(
                ElectricityPayment.reading_id == reading.id
            ).first()

            if consumption is None:
                result["baseline_readings"] += 1
                continue
            if not tariff:
                result["missing_tariff"] = True
                continue

            avg = get_average_consumption(session, member_id)
            if detect_anomaly(consumption, avg):
                result["anomalies"].append(member_id)

            amount = (consumption * tariff.rate_per_kwh).quantize(Decimal("0.01"))
            if payment:
                payment.member_id = member_id
                payment.period_start = period_start
                payment.period_end = period_end
                payment.consumption_kwh = consumption
                payment.rate_per_kwh = tariff.rate_per_kwh
                payment.amount_due = amount
                result["updated_payments"] += 1
            else:
                payment = ElectricityPayment(
                    member_id=member_id,
                    reading_id=reading.id,
                    period_start=period_start,
                    period_end=period_end,
                    consumption_kwh=consumption,
                    rate_per_kwh=tariff.rate_per_kwh,
                    amount_due=amount,
                    amount_paid=Decimal("0"),
                )
                session.add(payment)
                result["created_payments"] += 1

        return result


def record_electricity_payment(
    payment_id: int,
    amount: Decimal,
    payment_date: date,
) -> None:
    """Record an electricity payment and keep payment event history."""
    with db_session() as session:
        payment = session.get(ElectricityPayment, payment_id)
        if not payment:
            raise ValueError("Начисление не найдено")

        payment.amount_paid = payment.amount_paid + amount
        payment.payment_date = payment_date
        session.add(PaymentHistory(
            payment_type="electricity",
            payment_id=payment.id,
            member_id=payment.member_id,
            amount=amount,
            payment_date=payment_date,
        ))
