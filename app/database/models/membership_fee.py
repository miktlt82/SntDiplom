"""Membership fee models."""

from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    String, Integer, Numeric, Date, DateTime, Text, ForeignKey, Boolean, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class MembershipFeePeriod(TimestampMixin, Base):
    __tablename__ = "membership_fee_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_per_sotka: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    penalty_daily_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 5), nullable=False, default=Decimal("0.001")
    )
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    payments: Mapped[list[MembershipFeePayment]] = relationship(
        back_populates="period", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<MembershipFeePeriod {self.name} ({self.year})>"


class MembershipFeePayment(TimestampMixin, Base):
    __tablename__ = "membership_fee_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("membership_fee_periods.id", ondelete="CASCADE"),
        nullable=False
    )
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    amount_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    penalty_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    period: Mapped[MembershipFeePeriod] = relationship(back_populates="payments")

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
