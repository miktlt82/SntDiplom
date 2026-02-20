"""Electricity models."""

from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    String, Integer, Numeric, Date, DateTime, Text, ForeignKey, Boolean, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class ElectricityTariff(TimestampMixin, Base):
    __tablename__ = "electricity_tariffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rate_per_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MeterReading(TimestampMixin, Base):
    __tablename__ = "meter_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    reading_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    previous_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    consumption: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ElectricityPayment(TimestampMixin, Base):
    __tablename__ = "electricity_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    reading_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("meter_readings.id", ondelete="SET NULL"), nullable=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    consumption_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    rate_per_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def status(self) -> str:
        from app.constants import PaymentStatus
        try:
            if self.amount_paid >= self.amount_due:
                return PaymentStatus.PAID.value
            elif self.amount_paid > 0:
                return PaymentStatus.PARTIAL.value
            else:
                return PaymentStatus.NOT_PAID.value
        except (TypeError, AttributeError):
            return PaymentStatus.NOT_PAID.value


class SntMeterReading(TimestampMixin, Base):
    __tablename__ = "snt_meter_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    previous_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    consumption: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
