"""Membership fee calculation service."""

from __future__ import annotations
from datetime import date
from decimal import Decimal

from app.database.engine import db_session
from app.database.models.member import Member
from app.database.models.membership_fee import MembershipFeePeriod, MembershipFeePayment
from app.constants import MemberStatus, PaymentStatus


def calculate_fee_for_member(period: MembershipFeePeriod, member: Member) -> Decimal:
    """Calculate membership fee: rate_per_sotka * plot_area."""
    return (period.rate_per_sotka * member.plot_area).quantize(Decimal("0.01"))


def generate_payments_for_period(period_id: int) -> int:
    """Generate payment records for all active members for a given period.
    Returns the number of created records.
    """
    with db_session() as session:
        period = session.get(MembershipFeePeriod, period_id)
        if not period:
            return 0

        members = session.query(Member).filter(
            Member.status == MemberStatus.ACTIVE.value
        ).all()

        existing_member_ids = {
            p.member_id for p in
            session.query(MembershipFeePayment.member_id).filter(
                MembershipFeePayment.period_id == period_id
            ).all()
        }

        count = 0
        for member in members:
            if member.id in existing_member_ids:
                continue
            amount = calculate_fee_for_member(period, member)
            payment = MembershipFeePayment(
                period_id=period_id,
                member_id=member.id,
                amount_due=amount,
                amount_paid=Decimal("0"),
            )
            session.add(payment)
            count += 1

        return count


def record_payment(payment_id: int, amount: Decimal, payment_date: date | None = None) -> None:
    """Record a payment (or partial payment)."""
    from app.database.models.payment_history import PaymentHistory

    if payment_date is None:
        payment_date = date.today()

    with db_session() as session:
        payment = session.get(MembershipFeePayment, payment_id)
        if not payment:
            return
        payment.amount_paid = payment.amount_paid + amount
        payment.payment_date = payment_date

        session.add(PaymentHistory(
            payment_type="membership",
            payment_id=payment.id,
            member_id=payment.member_id,
            amount=amount,
            payment_date=payment_date,
        ))
