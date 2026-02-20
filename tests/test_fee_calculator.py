"""Tests for membership fee calculator service."""

from __future__ import annotations
from datetime import date
from decimal import Decimal

import pytest

from app.database.models.membership_fee import MembershipFeePeriod, MembershipFeePayment
from app.database.models.member import Member
from app.services.fee_calculator import (
    calculate_fee_for_member,
    calculate_penalty,
    generate_payments_for_period,
    record_payment,
)
from app.constants import MemberStatus


class TestCalculateFee:
    def test_basic_fee(self, session, seed_period, seed_members):
        """Fee = rate_per_sotka * plot_area."""
        period = seed_period
        member = seed_members[0]  # plot_area=6
        fee = calculate_fee_for_member(period, member)
        assert fee == Decimal("3000.00")  # 500 * 6

    def test_larger_area(self, session, seed_period, seed_members):
        member = seed_members[1]  # plot_area=10
        fee = calculate_fee_for_member(seed_period, member)
        assert fee == Decimal("5000.00")  # 500 * 10


class TestCalculatePenalty:
    def test_no_penalty_before_due_date(self, session, seed_period):
        payment = MembershipFeePayment(
            period_id=seed_period.id, member_id=1,
            amount_due=Decimal("3000"), amount_paid=Decimal("0"),
        )
        penalty = calculate_penalty(payment, seed_period, as_of=date(2025, 6, 30))
        assert penalty == Decimal("0.00")

    def test_no_penalty_on_due_date(self, session, seed_period):
        payment = MembershipFeePayment(
            period_id=seed_period.id, member_id=1,
            amount_due=Decimal("3000"), amount_paid=Decimal("0"),
        )
        penalty = calculate_penalty(payment, seed_period, as_of=date(2025, 7, 1))
        assert penalty == Decimal("0.00")

    def test_penalty_after_due_date(self, session, seed_period):
        payment = MembershipFeePayment(
            period_id=seed_period.id, member_id=1,
            amount_due=Decimal("3000"), amount_paid=Decimal("0"),
        )
        # 10 days overdue: 3000 * 0.001 * 10 = 30.00
        penalty = calculate_penalty(payment, seed_period, as_of=date(2025, 7, 11))
        assert penalty == Decimal("30.00")

    def test_no_penalty_if_fully_paid(self, session, seed_period):
        payment = MembershipFeePayment(
            period_id=seed_period.id, member_id=1,
            amount_due=Decimal("3000"), amount_paid=Decimal("3000"),
        )
        penalty = calculate_penalty(payment, seed_period, as_of=date(2025, 8, 1))
        assert penalty == Decimal("0.00")

    def test_partial_payment_penalty(self, session, seed_period):
        payment = MembershipFeePayment(
            period_id=seed_period.id, member_id=1,
            amount_due=Decimal("3000"), amount_paid=Decimal("1000"),
        )
        # Outstanding=2000, 5 days: 2000 * 0.001 * 5 = 10.00
        penalty = calculate_penalty(payment, seed_period, as_of=date(2025, 7, 6))
        assert penalty == Decimal("10.00")


class TestGeneratePayments:
    def test_generates_for_active_members(self, session, seed_period, seed_members):
        count = generate_payments_for_period(seed_period.id)
        assert count == 2  # only 2 active, 1 archived

        payments = session.query(MembershipFeePayment).filter(
            MembershipFeePayment.period_id == seed_period.id
        ).all()
        assert len(payments) == 2

    def test_skips_existing(self, session, seed_period, seed_members):
        # First generation
        generate_payments_for_period(seed_period.id)
        # Second — should not create duplicates
        count = generate_payments_for_period(seed_period.id)
        assert count == 0

    def test_correct_amounts(self, session, seed_period, seed_members):
        generate_payments_for_period(seed_period.id)
        payments = session.query(MembershipFeePayment).all()
        amounts = {p.amount_due for p in payments}
        # Member 1: 500*6=3000, Member 2: 500*10=5000
        assert amounts == {Decimal("3000.00"), Decimal("5000.00")}

    def test_nonexistent_period(self, session):
        count = generate_payments_for_period(9999)
        assert count == 0


class TestRecordPayment:
    def test_record_full_payment(self, session, seed_period, seed_members):
        generate_payments_for_period(seed_period.id)
        payment = session.query(MembershipFeePayment).first()
        payment_id = payment.id

        record_payment(payment_id, Decimal("3000.00"), date(2025, 6, 15))

        session.expire_all()
        updated = session.get(MembershipFeePayment, payment_id)
        assert updated.amount_paid == Decimal("3000.00")
        assert updated.payment_date == date(2025, 6, 15)
        assert updated.status == "paid"

    def test_record_partial_payment(self, session, seed_period, seed_members):
        generate_payments_for_period(seed_period.id)
        payment = session.query(MembershipFeePayment).first()
        payment_id = payment.id

        record_payment(payment_id, Decimal("1000.00"), date(2025, 6, 15))

        session.expire_all()
        updated = session.get(MembershipFeePayment, payment_id)
        assert updated.amount_paid == Decimal("1000.00")
        assert updated.status == "partial"

    def test_record_nonexistent_payment(self, session):
        # Should not raise
        record_payment(9999, Decimal("100"), date(2025, 1, 1))
