"""Tests for report/analytics service."""

from __future__ import annotations
from datetime import date
from decimal import Decimal

import pytest

from app.database.models.member import Member
from app.database.models.membership_fee import MembershipFeePeriod, MembershipFeePayment
from app.database.models.target_fee import TargetFeeCampaign, TargetFeePayment
from app.database.models.electricity import ElectricityPayment
from app.constants import MemberStatus, TargetFeeType
from app.services.report_service import (
    get_member_stats,
    get_membership_fee_summary,
    get_target_fee_summary,
    get_electricity_summary,
    get_debtors_list,
    get_payments_by_period,
    get_target_payments_by_campaign,
    get_electricity_payments_by_period,
)


class TestMemberStats:
    def test_empty_db(self, session):
        stats = get_member_stats()
        assert stats == {"total": 0, "active": 0, "archived": 0}

    def test_with_members(self, session, seed_members):
        stats = get_member_stats()
        assert stats["total"] == 3
        assert stats["active"] == 2
        assert stats["archived"] == 1


class TestMembershipFeeSummary:
    def test_empty(self, session):
        summary = get_membership_fee_summary()
        assert summary["total_due"] == Decimal("0")
        assert summary["total_paid"] == Decimal("0")

    def test_with_payments(self, session, seed_members, seed_period):
        m1, m2, _ = seed_members
        session.add_all([
            MembershipFeePayment(
                period_id=seed_period.id, member_id=m1.id,
                amount_due=Decimal("3000"), amount_paid=Decimal("3000"),
            ),
            MembershipFeePayment(
                period_id=seed_period.id, member_id=m2.id,
                amount_due=Decimal("5000"), amount_paid=Decimal("1000"),
            ),
        ])
        session.commit()

        summary = get_membership_fee_summary()
        assert summary["total_due"] == Decimal("8000")
        assert summary["total_paid"] == Decimal("4000")
        assert summary["outstanding"] == Decimal("4000")
        assert summary["paid_count"] == 1
        assert summary["partial_count"] == 1
        assert summary["not_paid_count"] == 0

    def test_overpayment_is_not_counted_as_debt(self, session, seed_members, seed_period):
        m1 = seed_members[0]
        session.add(MembershipFeePayment(
            period_id=seed_period.id, member_id=m1.id,
            amount_due=Decimal("3000"), amount_paid=Decimal("3500"),
        ))
        session.commit()

        summary = get_membership_fee_summary()
        assert summary["outstanding"] == Decimal("0")
        assert summary["overpaid_count"] == 1


class TestTargetFeeSummary:
    def test_with_status_counts(self, session, seed_members):
        m1, m2, _ = seed_members
        campaign = TargetFeeCampaign(
            name="Ремонт дороги",
            fee_type=TargetFeeType.FIXED.value,
            amount=Decimal("2000"),
            due_date=date(2025, 8, 1),
        )
        session.add(campaign)
        session.commit()

        session.add_all([
            TargetFeePayment(
                campaign_id=campaign.id, member_id=m1.id,
                amount_due=Decimal("2000"), amount_paid=Decimal("2000"),
            ),
            TargetFeePayment(
                campaign_id=campaign.id, member_id=m2.id,
                amount_due=Decimal("2000"), amount_paid=Decimal("500"),
            ),
        ])
        session.commit()

        summary = get_target_fee_summary()
        assert summary["total_due"] == Decimal("4000")
        assert summary["total_paid"] == Decimal("2500")
        assert summary["outstanding"] == Decimal("1500")
        assert summary["paid_count"] == 1
        assert summary["partial_count"] == 1
        assert summary["not_paid_count"] == 0


class TestElectricitySummary:
    def test_with_status_counts(self, session, seed_members):
        m1, m2, _ = seed_members
        session.add_all([
            ElectricityPayment(
                member_id=m1.id,
                period_start=date(2025, 1, 1),
                period_end=date(2025, 1, 31),
                consumption_kwh=Decimal("100"),
                rate_per_kwh=Decimal("5"),
                amount_due=Decimal("500"),
                amount_paid=Decimal("500"),
            ),
            ElectricityPayment(
                member_id=m2.id,
                period_start=date(2025, 1, 1),
                period_end=date(2025, 1, 31),
                consumption_kwh=Decimal("120"),
                rate_per_kwh=Decimal("5"),
                amount_due=Decimal("600"),
                amount_paid=Decimal("0"),
            ),
        ])
        session.commit()

        summary = get_electricity_summary()
        assert summary["total_due"] == Decimal("1100")
        assert summary["total_paid"] == Decimal("500")
        assert summary["outstanding"] == Decimal("600")
        assert summary["paid_count"] == 1
        assert summary["not_paid_count"] == 1


class TestDebtorsList:
    def test_empty(self, session):
        debtors = get_debtors_list()
        assert debtors == []

    def test_debtor_detected(self, session, seed_members, seed_period):
        m1, m2, _ = seed_members
        session.add_all([
            MembershipFeePayment(
                period_id=seed_period.id, member_id=m1.id,
                amount_due=Decimal("3000"), amount_paid=Decimal("3000"),
            ),
            MembershipFeePayment(
                period_id=seed_period.id, member_id=m2.id,
                amount_due=Decimal("5000"), amount_paid=Decimal("1000"),
            ),
        ])
        session.commit()

        debtors = get_debtors_list()
        assert len(debtors) == 1
        assert debtors[0]["plot_number"] == "002"
        assert debtors[0]["total_debt"] == Decimal("4000")

    def test_archived_not_included(self, session, seed_members, seed_period):
        """Archived members should not appear in debtors list."""
        archived = seed_members[2]  # status=archived
        session.add(MembershipFeePayment(
            period_id=seed_period.id, member_id=archived.id,
            amount_due=Decimal("1000"), amount_paid=Decimal("0"),
        ))
        session.commit()

        debtors = get_debtors_list()
        assert len(debtors) == 0


class TestPaymentsByPeriod:
    def test_empty(self, session):
        result = get_payments_by_period()
        assert result == []

    def test_with_data(self, session, seed_members, seed_period):
        m1 = seed_members[0]
        session.add(MembershipFeePayment(
            period_id=seed_period.id, member_id=m1.id,
            amount_due=Decimal("3000"), amount_paid=Decimal("2000"),
        ))
        session.commit()

        result = get_payments_by_period()
        assert len(result) == 1
        assert result[0]["period"] == "Взносы 2025 (2025)"
        assert result[0]["total_due"] == 3000.0
        assert result[0]["total_paid"] == 2000.0


class TestTargetPaymentsByCampaign:
    def test_with_data(self, session, seed_members):
        m1 = seed_members[0]
        campaign = TargetFeeCampaign(
            name="Ворота",
            fee_type=TargetFeeType.FIXED.value,
            amount=Decimal("1000"),
            due_date=date(2025, 9, 1),
        )
        session.add(campaign)
        session.commit()
        session.add(TargetFeePayment(
            campaign_id=campaign.id, member_id=m1.id,
            amount_due=Decimal("1000"), amount_paid=Decimal("700"),
        ))
        session.commit()

        result = get_target_payments_by_campaign()
        assert result == [{
            "period": "Ворота",
            "total_due": 1000.0,
            "total_paid": 700.0,
        }]


class TestElectricityPaymentsByPeriod:
    def test_with_data(self, session, seed_members):
        m1 = seed_members[0]
        session.add_all([
            ElectricityPayment(
                member_id=m1.id,
                period_start=date(2025, 1, 1),
                period_end=date(2025, 1, 31),
                consumption_kwh=Decimal("100"),
                rate_per_kwh=Decimal("5"),
                amount_due=Decimal("500"),
                amount_paid=Decimal("200"),
            ),
            ElectricityPayment(
                member_id=m1.id,
                period_start=date(2025, 2, 1),
                period_end=date(2025, 2, 28),
                consumption_kwh=Decimal("80"),
                rate_per_kwh=Decimal("5"),
                amount_due=Decimal("400"),
                amount_paid=Decimal("400"),
            ),
        ])
        session.commit()

        result = get_electricity_payments_by_period()
        assert result == [
            {"period": "2025-01", "total_due": 500.0, "total_paid": 200.0},
            {"period": "2025-02", "total_due": 400.0, "total_paid": 400.0},
        ]
