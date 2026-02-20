"""Target fee models."""

from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    String, Integer, Numeric, Date, DateTime, Text, ForeignKey, Boolean, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.constants import TargetFeeType


class TargetFeeCampaign(TimestampMixin, Base):
    __tablename__ = "target_fee_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fee_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TargetFeeType.FIXED.value
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    payments: Mapped[list[TargetFeePayment]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    documents: Mapped[list[TargetFeeDocument]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class TargetFeePayment(TimestampMixin, Base):
    __tablename__ = "target_fee_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("target_fee_campaigns.id", ondelete="CASCADE"),
        nullable=False
    )
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    amount_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    campaign: Mapped[TargetFeeCampaign] = relationship(back_populates="payments")

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


class TargetFeeDocument(TimestampMixin, Base):
    __tablename__ = "target_fee_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("target_fee_campaigns.id", ondelete="CASCADE"),
        nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    campaign: Mapped[TargetFeeCampaign] = relationship(back_populates="documents")
