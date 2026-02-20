"""Aggregation service for analytics dashboard."""

from __future__ import annotations
from decimal import Decimal

from sqlalchemy import func

from app.database.engine import db_session
from app.database.models.member import Member
from app.database.models.membership_fee import MembershipFeePeriod, MembershipFeePayment
from app.database.models.target_fee import TargetFeeCampaign, TargetFeePayment
from app.database.models.electricity import ElectricityPayment
from app.constants import MemberStatus, PaymentStatus


def get_member_stats() -> dict:
    with db_session(readonly=True) as session:
        total = session.query(Member).count()
        active = session.query(Member).filter(
            Member.status == MemberStatus.ACTIVE.value
        ).count()
        archived = total - active
        return {"total": total, "active": active, "archived": archived}


def get_membership_fee_summary() -> dict:
    """Returns summary of all membership fee payments."""
    with db_session(readonly=True) as session:
        row = session.query(
            func.coalesce(func.sum(MembershipFeePayment.amount_due), 0),
            func.coalesce(func.sum(MembershipFeePayment.amount_paid), 0),
            func.count(MembershipFeePayment.id),
        ).first()
        total_due = Decimal(str(row[0]))
        total_paid = Decimal(str(row[1]))
        total_count = row[2]

        # Status is a computed property, so count via SQL conditions
        paid_count = session.query(func.count(MembershipFeePayment.id)).filter(
            MembershipFeePayment.amount_paid >= MembershipFeePayment.amount_due,
            MembershipFeePayment.amount_due > 0,
        ).scalar() or 0
        partial_count = session.query(func.count(MembershipFeePayment.id)).filter(
            MembershipFeePayment.amount_paid > 0,
            MembershipFeePayment.amount_paid < MembershipFeePayment.amount_due,
        ).scalar() or 0
        not_paid_count = session.query(func.count(MembershipFeePayment.id)).filter(
            MembershipFeePayment.amount_paid == 0,
        ).scalar() or 0

        return {
            "total_due": total_due,
            "total_paid": total_paid,
            "outstanding": total_due - total_paid,
            "paid_count": paid_count,
            "partial_count": partial_count,
            "not_paid_count": not_paid_count,
        }


def get_target_fee_summary() -> dict:
    with db_session(readonly=True) as session:
        row = session.query(
            func.coalesce(func.sum(TargetFeePayment.amount_due), 0),
            func.coalesce(func.sum(TargetFeePayment.amount_paid), 0),
        ).first()
        total_due = Decimal(str(row[0]))
        total_paid = Decimal(str(row[1]))
        return {
            "total_due": total_due,
            "total_paid": total_paid,
            "outstanding": total_due - total_paid,
        }


def get_electricity_summary() -> dict:
    with db_session(readonly=True) as session:
        row = session.query(
            func.coalesce(func.sum(ElectricityPayment.amount_due), 0),
            func.coalesce(func.sum(ElectricityPayment.amount_paid), 0),
        ).first()
        total_due = Decimal(str(row[0]))
        total_paid = Decimal(str(row[1]))
        return {
            "total_due": total_due,
            "total_paid": total_paid,
            "outstanding": total_due - total_paid,
        }


def get_debtors_list() -> list[dict]:
    """Get list of members with outstanding debts using SQL aggregation."""
    with db_session(readonly=True) as session:
        from sqlalchemy import literal_column
        from sqlalchemy.orm import aliased

        # Aggregate debt per member for each payment type
        mf_debt = session.query(
            MembershipFeePayment.member_id,
            func.sum(MembershipFeePayment.amount_due - MembershipFeePayment.amount_paid).label("debt"),
        ).filter(
            MembershipFeePayment.amount_due > MembershipFeePayment.amount_paid,
        ).group_by(MembershipFeePayment.member_id).subquery()

        tf_debt = session.query(
            TargetFeePayment.member_id,
            func.sum(TargetFeePayment.amount_due - TargetFeePayment.amount_paid).label("debt"),
        ).filter(
            TargetFeePayment.amount_due > TargetFeePayment.amount_paid,
        ).group_by(TargetFeePayment.member_id).subquery()

        ep_debt = session.query(
            ElectricityPayment.member_id,
            func.sum(ElectricityPayment.amount_due - ElectricityPayment.amount_paid).label("debt"),
        ).filter(
            ElectricityPayment.amount_due > ElectricityPayment.amount_paid,
        ).group_by(ElectricityPayment.member_id).subquery()

        results = session.query(
            Member.id,
            Member.plot_number,
            Member.last_name,
            Member.first_name,
            Member.patronymic,
            func.coalesce(mf_debt.c.debt, 0) + func.coalesce(tf_debt.c.debt, 0) + func.coalesce(ep_debt.c.debt, 0),
        ).outerjoin(
            mf_debt, Member.id == mf_debt.c.member_id
        ).outerjoin(
            tf_debt, Member.id == tf_debt.c.member_id
        ).outerjoin(
            ep_debt, Member.id == ep_debt.c.member_id
        ).filter(
            Member.status == MemberStatus.ACTIVE.value,
        ).having(
            func.coalesce(mf_debt.c.debt, 0) + func.coalesce(tf_debt.c.debt, 0) + func.coalesce(ep_debt.c.debt, 0) > 0
        ).group_by(Member.id).all()

        debtors = []
        for mid, plot_number, last_name, first_name, patronymic, total_debt in results:
            parts = [last_name, first_name]
            if patronymic:
                parts.append(patronymic)
            debtors.append({
                "member_id": mid,
                "plot_number": plot_number,
                "full_name": " ".join(parts),
                "total_debt": Decimal(str(total_debt)),
            })

        debtors.sort(key=lambda x: x["total_debt"], reverse=True)
        return debtors


def get_payments_by_period() -> list[dict]:
    """Get payment totals by membership fee period."""
    with db_session(readonly=True) as session:
        rows = session.query(
            MembershipFeePeriod.name,
            MembershipFeePeriod.year,
            func.coalesce(func.sum(MembershipFeePayment.amount_due), 0),
            func.coalesce(func.sum(MembershipFeePayment.amount_paid), 0),
        ).outerjoin(
            MembershipFeePayment,
            MembershipFeePayment.period_id == MembershipFeePeriod.id,
        ).group_by(
            MembershipFeePeriod.id,
        ).order_by(
            MembershipFeePeriod.year,
        ).all()

        return [
            {
                "period": f"{name} ({year})",
                "total_due": float(total_due),
                "total_paid": float(total_paid),
            }
            for name, year, total_due, total_paid in rows
        ]
