"""Payment history dialog for a selected fee payment row."""

from __future__ import annotations
from decimal import Decimal

import customtkinter as ctk

from app.database.engine import db_session
from app.database.models.member import Member
from app.database.models.electricity import ElectricityPayment
from app.database.models.membership_fee import MembershipFeePayment, MembershipFeePeriod
from app.database.models.payment_history import PaymentHistory
from app.database.models.target_fee import TargetFeeCampaign, TargetFeePayment
from app.gui.widgets.modal_dialog import ModalDialog
from app.gui.widgets.styled_treeview import StyledTreeview


HISTORY_COLUMNS = [
    {"id": "date", "text": "Дата", "width": 120, "anchor": "center"},
    {"id": "amount", "text": "Сумма", "width": 120, "anchor": "e"},
]


class FeePaymentHistoryDialog(ModalDialog):
    """Shows payment events for one membership or target fee payment."""

    def __init__(self, parent, payment_type: str, payment_id: int):
        self.payment_type = payment_type
        self.payment_id = payment_id
        self._context = self._load_context()
        super().__init__(
            parent,
            title=f"История оплат — {self._context['member_name']}",
            width=540,
            height=420,
        )
        self._build_ui()
        self._load_history()

    def _build_ui(self):
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            header,
            text=self._context["member_name"],
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(
            header,
            text=self._context["subject"],
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=10, pady=(0, 2))
        ctk.CTkLabel(
            header,
            text=(
                f"Начислено: {self._context['amount_due']:.2f}  |  "
                f"Оплачено: {self._context['amount_paid']:.2f}  |  "
                f"Остаток: {self._context['remaining']:.2f}"
            ),
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=10, pady=(0, 8))

        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree = StyledTreeview(
            table_frame,
            columns=HISTORY_COLUMNS,
            style_name="PaymentEvents.Treeview",
        )
        self.tree.pack_with_scrollbar()

        ctk.CTkButton(self, text="Закрыть", command=self._on_cancel).pack(pady=10)

    def _load_context(self) -> dict:
        empty = {
            "member_name": "Запись не найдена",
            "subject": "—",
            "amount_due": Decimal("0"),
            "amount_paid": Decimal("0"),
            "remaining": Decimal("0"),
        }

        with db_session(readonly=True) as session:
            if self.payment_type == "membership":
                payment = session.get(MembershipFeePayment, self.payment_id)
                if not payment:
                    return empty
                member = session.get(Member, payment.member_id)
                period = session.get(MembershipFeePeriod, payment.period_id)
                subject = "Членские взносы"
                if period:
                    subject = f"{period.name} ({period.year})"
            elif self.payment_type == "target":
                payment = session.get(TargetFeePayment, self.payment_id)
                if not payment:
                    return empty
                member = session.get(Member, payment.member_id)
                campaign = session.get(TargetFeeCampaign, payment.campaign_id)
                subject = campaign.name if campaign else "Целевой взнос"
            else:
                payment = session.get(ElectricityPayment, self.payment_id)
                if not payment:
                    return empty
                member = session.get(Member, payment.member_id)
                subject = (
                    f"Электроэнергия: {payment.period_start} — "
                    f"{payment.period_end}, {payment.consumption_kwh:.2f} кВт·ч"
                )

            amount_due = payment.amount_due or Decimal("0")
            amount_paid = payment.amount_paid or Decimal("0")
            return {
                "member_name": member.full_name if member else "Участник не найден",
                "subject": subject,
                "amount_due": amount_due,
                "amount_paid": amount_paid,
                "remaining": amount_due - amount_paid,
            }

    def _load_history(self):
        with db_session(readonly=True) as session:
            history = session.query(PaymentHistory).filter(
                PaymentHistory.payment_type == self.payment_type,
                PaymentHistory.payment_id == self.payment_id,
            ).order_by(
                PaymentHistory.payment_date.desc(),
                PaymentHistory.id.desc(),
            ).all()

            rows = [
                {
                    "id": item.id,
                    "date": str(item.payment_date),
                    "amount": f"{item.amount:.2f}",
                }
                for item in history
            ]
            self.tree.load_data(rows)
