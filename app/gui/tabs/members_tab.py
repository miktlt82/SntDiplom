"""Members management tab."""

from __future__ import annotations
from decimal import Decimal
import customtkinter as ctk
from tkinter import messagebox

from app.gui.tabs.base_tab import BaseTab
from app.gui.widgets.styled_treeview import StyledTreeview
from app.gui.widgets.search_bar import SearchBar
from app.gui.widgets.modal_dialog import ModalDialog
from app.database.engine import db_session
from app.database.models.member import Member, MemberStatusHistory
from app.database.models.payment_history import PaymentHistory
from app.database.models.membership_fee import MembershipFeePeriod, MembershipFeePayment
from app.database.models.target_fee import TargetFeeCampaign, TargetFeePayment
from app.constants import MemberStatus, AuditAction
from app.services.audit_service import log_action
from app.event_bus import event_bus


MEMBER_COLUMNS = [
    {"id": "id", "text": "ID", "width": 50, "anchor": "center", "stretch": False},
    {"id": "plot_number", "text": "Участок", "width": 80, "anchor": "center"},
    {"id": "full_name", "text": "ФИО", "width": 250},
    {"id": "plot_area", "text": "Площадь (сот.)", "width": 100, "anchor": "center"},
    {"id": "phone", "text": "Телефон", "width": 130},
    {"id": "email", "text": "Email", "width": 150},
    {"id": "status", "text": "Статус", "width": 100, "anchor": "center"},
]


class MembersTab(BaseTab):

    def _build_ui(self):
        # Toolbar
        toolbar = ctk.CTkFrame(self.frame)
        toolbar.pack(fill="x", padx=5, pady=5)

        ctk.CTkButton(
            toolbar, text="+ Добавить", width=120, command=self._add_member
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            toolbar, text="Редактировать", width=120, command=self._edit_member
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            toolbar, text="Архивировать", width=120, command=self._archive_member
        ).pack(side="left", padx=5)

        # Search
        self.search_bar = SearchBar(
            self.frame,
            on_search=self._on_search,
            filter_options=["Активные", "Архивные"],
            placeholder="Поиск по ФИО или участку...",
        )
        self.search_bar.pack(fill="x", padx=5, pady=(0, 5))

        # Table frame
        table_frame = ctk.CTkFrame(self.frame)
        table_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.tree = StyledTreeview(
            table_frame,
            columns=MEMBER_COLUMNS,
            style_name="Members.Treeview",
            on_double_click=self._on_double_click,
        )
        self.tree.pack_with_scrollbar()

        # Count label
        self.count_label = ctk.CTkLabel(self.frame, text="", font=ctk.CTkFont(size=11))
        self.count_label.pack(fill="x", padx=10, pady=(0, 5))

    def refresh_data(self):
        query = self.search_bar.get_query() if hasattr(self, "search_bar") else ""
        filter_val = self.search_bar.get_filter() if hasattr(self, "search_bar") else "Все"
        self._load_members(query, filter_val)

    def _load_members(self, search: str = "", filter_val: str = "Все"):
        with db_session(readonly=True) as session:
            q = session.query(Member)

            if filter_val == "Активные":
                q = q.filter(Member.status == MemberStatus.ACTIVE.value)
            elif filter_val == "Архивные":
                q = q.filter(Member.status == MemberStatus.ARCHIVED.value)

            if search:
                search_like = f"%{search}%"
                q = q.filter(
                    (Member.last_name.ilike(search_like))
                    | (Member.first_name.ilike(search_like))
                    | (Member.patronymic.ilike(search_like))
                    | (Member.plot_number.ilike(search_like))
                )

            members = q.order_by(Member.plot_number).all()

            rows = []
            for m in members:
                tag = "archived" if m.status == MemberStatus.ARCHIVED.value else ""
                rows.append({
                    "id": m.id,
                    "plot_number": m.plot_number,
                    "full_name": m.full_name,
                    "plot_area": str(m.plot_area),
                    "phone": m.phone or "",
                    "email": m.email or "",
                    "status": "Активный" if m.status == MemberStatus.ACTIVE.value else "Архивный",
                    "tag": tag,
                })

            self.tree.load_data(rows)
            self.count_label.configure(text=f"Всего: {len(rows)}")

    def _on_search(self, search: str, filter_val: str):
        self._load_members(search, filter_val)

    def _on_double_click(self, iid: str | None):
        if iid:
            dialog = PaymentHistoryDialog(self.app, member_id=int(iid))
            dialog.wait_for_result()

    def _add_member(self):
        from app.gui.tabs.member_card import MemberCardDialog
        dialog = MemberCardDialog(self.app, member_id=None)
        result = dialog.wait_for_result()
        if result:
            self.refresh_data()
            event_bus.publish("member_updated")
            self.set_status("Участник добавлен")

    def _edit_member(self):
        iid = self.tree.get_selected_iid()
        if not iid:
            messagebox.showwarning("Внимание", "Выберите участника")
            return
        from app.gui.tabs.member_card import MemberCardDialog
        dialog = MemberCardDialog(self.app, member_id=int(iid))
        result = dialog.wait_for_result()
        if result:
            self.refresh_data()
            event_bus.publish("member_updated")
            self.set_status("Данные участника обновлены")

    def _archive_member(self):
        iid = self.tree.get_selected_iid()
        if not iid:
            messagebox.showwarning("Внимание", "Выберите участника")
            return

        member_id = int(iid)
        try:
            with db_session() as session:
                member = session.get(Member, member_id)
                if not member:
                    return

                if member.status == MemberStatus.ARCHIVED.value:
                    if messagebox.askyesno("Восстановление", "Восстановить участника?"):
                        old = member.status
                        member.status = MemberStatus.ACTIVE.value
                        session.add(MemberStatusHistory(
                            member_id=member.id, old_status=old,
                            new_status=MemberStatus.ACTIVE.value, reason="Восстановлен"
                        ))
                        session.flush()
                        log_action(AuditAction.RESTORE.value, "member", member.id,
                                   f"Восстановлен: {member.full_name}")
                else:
                    if messagebox.askyesno("Архивирование", f"Архивировать {member.full_name}?"):
                        old = member.status
                        member.status = MemberStatus.ARCHIVED.value
                        session.add(MemberStatusHistory(
                            member_id=member.id, old_status=old,
                            new_status=MemberStatus.ARCHIVED.value, reason="Архивирован"
                        ))
                        session.flush()
                        log_action(AuditAction.ARCHIVE.value, "member", member.id,
                                   f"Архивирован: {member.full_name}")

            self.refresh_data()
            event_bus.publish("member_updated")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _subscribe_events(self):
        super()._subscribe_events()
        self._subscribe("member_updated", lambda **kw: self.refresh_data())


HISTORY_COLUMNS = [
    {"id": "period", "text": "Период / Кампания", "width": 220},
    {"id": "date", "text": "Дата", "width": 100, "anchor": "center"},
    {"id": "amount", "text": "Сумма", "width": 100, "anchor": "e"},
    {"id": "total_paid", "text": "Всего оплачено", "width": 120, "anchor": "e"},
]


class PaymentHistoryDialog(ModalDialog):
    def __init__(self, parent, member_id: int):
        self.member_id = member_id
        self._member_name = ""
        with db_session(readonly=True) as session:
            member = session.get(Member, member_id)
            if member:
                self._member_name = member.full_name
        super().__init__(
            parent,
            title=f"История оплат — {self._member_name}",
            width=600, height=500,
        )
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        # Member name header
        ctk.CTkLabel(
            self, text=self._member_name,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=10, pady=(10, 5))

        # Tabview for membership / target
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=5)

        self.tabview.add("Членские взносы")
        self.tabview.add("Целевые взносы")

        # Membership fees tree
        self.membership_tree = StyledTreeview(
            self.tabview.tab("Членские взносы"),
            columns=HISTORY_COLUMNS,
            style_name="MHist.Treeview",
        )
        self.membership_tree.pack_with_scrollbar()

        # Target fees tree
        self.target_tree = StyledTreeview(
            self.tabview.tab("Целевые взносы"),
            columns=HISTORY_COLUMNS,
            style_name="THist.Treeview",
        )
        self.target_tree.pack_with_scrollbar()

        # Close button
        ctk.CTkButton(self, text="Закрыть", command=self._on_cancel).pack(pady=10)

    def _load_data(self):
        with db_session(readonly=True) as session:
            # Membership fee history
            m_rows = []
            m_history = session.query(PaymentHistory).filter(
                PaymentHistory.member_id == self.member_id,
                PaymentHistory.payment_type == "membership",
            ).order_by(PaymentHistory.payment_date.desc()).all()

            for h in m_history:
                period_name = "—"
                total_paid = Decimal("0")
                pay = session.get(MembershipFeePayment, h.payment_id)
                if pay:
                    total_paid = pay.amount_paid
                    period = session.get(MembershipFeePeriod, pay.period_id)
                    if period:
                        period_name = f"{period.name} ({period.year})"
                m_rows.append({
                    "id": h.id,
                    "period": period_name,
                    "date": str(h.payment_date),
                    "amount": f"{h.amount:.2f}",
                    "total_paid": f"{total_paid:.2f}",
                })
            self.membership_tree.load_data(m_rows)

            # Target fee history
            t_rows = []
            t_history = session.query(PaymentHistory).filter(
                PaymentHistory.member_id == self.member_id,
                PaymentHistory.payment_type == "target",
            ).order_by(PaymentHistory.payment_date.desc()).all()

            for h in t_history:
                campaign_name = "—"
                total_paid = Decimal("0")
                pay = session.get(TargetFeePayment, h.payment_id)
                if pay:
                    total_paid = pay.amount_paid
                    campaign = session.get(TargetFeeCampaign, pay.campaign_id)
                    if campaign:
                        campaign_name = campaign.name
                t_rows.append({
                    "id": h.id,
                    "period": campaign_name,
                    "date": str(h.payment_date),
                    "amount": f"{h.amount:.2f}",
                    "total_paid": f"{total_paid:.2f}",
                })
            self.target_tree.load_data(t_rows)
