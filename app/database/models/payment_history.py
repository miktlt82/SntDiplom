"""Payment history model — records every payment event."""

from __future__ import annotations
from datetime import date
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class PaymentHistory(TimestampMixin, Base):
    __tablename__ = "payment_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "membership" | "target"
    payment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
