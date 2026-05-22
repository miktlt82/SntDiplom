"""Membership fee tab — periods, payments table."""

from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
from tkinter import messagebox
import customtkinter as ctk

from app.gui.tabs.base_tab import BaseTab
from app.gui.widgets.styled_treeview import StyledTreeview
from app.gui.widgets.date_picker import DatePicker
from app.gui.widgets.modal_dialog import ModalDialog
from app.database.engine import db_session
from app.database.models.member import Member
from app.database.models.membership_fee import MembershipFeePeriod, MembershipFeePayment
from app.services.fee_calculator import (
    calculate_fee_for_member, generate_payments_for_period, record_payment
)
from app.services.audit_service import log_action
from app.constants import AuditAction
from app.event_bus import event_bus
from app.gui.widgets.progress_dialog import ProgressDialog


PAYMENT_COLUMNS = [
    {"id": "id", "text": "ID", "width": 40, "anchor": "center", "stretch": False},
    {"id": "plot_number", "text": "Участок", "width": 80, "anchor": "center"},
    {"id": "full_name", "text": "ФИО", "width": 220},
    {"id": "area", "text": "Площадь", "width": 80, "anchor": "center"},
    {"id": "amount_due", "text": "Начислено", "width": 100, "anchor": "e"},
    {"id": "amount_paid", "text": "Оплачено", "width": 100, "anchor": "e"},
    {"id": "remaining", "text": "Остаток", "width": 100, "anchor": "e"},
    {"id": "status", "text": "Статус", "width": 100, "anchor": "center"},
]


class MembershipFeeTab(BaseTab):

    def _build_ui(self):
        # Period selector — row 1
        row1 = ctk.CTkFrame(self.frame)
        row1.pack(fill="x", padx=5, pady=(5, 2))

        ctk.CTkLabel(row1, text="Период:").pack(side="left", padx=5)
        self.period_var = ctk.StringVar()
        self.period_menu = ctk.CTkOptionMenu(
            row1, variable=self.period_var,
            values=["—"], command=self._on_period_selected, width=250
        )
        self.period_menu.pack(side="left", padx=5)

        # Action buttons — row 2
        row2 = ctk.CTkFrame(self.frame)
        row2.pack(fill="x", padx=5, pady=(2, 5))

        ctk.CTkButton(
            row2, text="+ Новый период", width=140,
            command=self._create_period
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            row2, text="Редактировать", width=120,
            command=self._edit_period
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            row2, text="Удалить", width=90,
            command=self._delete_period
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            row2, text="Сгенерировать", width=130,
            command=self._generate_payments
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            row2, text="Записать оплату", width=130,
            command=self._record_payment_dialog
        ).pack(side="left", padx=5)

        # Table
        table_frame = ctk.CTkFrame(self.frame)
        table_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.tree = StyledTreeview(
            table_frame, columns=PAYMENT_COLUMNS,
            style_name="MFee.Treeview",
        )
        self.tree.pack_with_scrollbar()

        # Summary
        self.summary_label = ctk.CTkLabel(self.frame, text="", font=ctk.CTkFont(size=11))
        self.summary_label.pack(fill="x", padx=10, pady=(0, 5))

        self._periods: dict[str, int] = {}

    def refresh_data(self):
        self._load_periods()

    def _load_periods(self):
        with db_session(readonly=True) as session:
            periods = session.query(MembershipFeePeriod).order_by(
                MembershipFeePeriod.year.desc(), MembershipFeePeriod.id.desc()
            ).all()
            self._periods = {}
            names = []
            for p in periods:
                label = f"{p.name} ({p.year})"
                self._periods[label] = p.id
                names.append(label)

            if names:
                self.period_menu.configure(values=names)
                if not self.period_var.get() or self.period_var.get() not in names:
                    self.period_var.set(names[0])
                self._load_payments()
            else:
                self.period_menu.configure(values=["—"])
                self.period_var.set("—")
                self.tree.load_data([])
                self.summary_label.configure(text="")

    def _on_period_selected(self, _):
        self._load_payments()

    def _get_current_period_id(self) -> int | None:
        label = self.period_var.get()
        return self._periods.get(label)

    def _load_payments(self):
        period_id = self._get_current_period_id()
        if not period_id:
            self.tree.load_data([])
            return

        with db_session(readonly=True) as session:
            period = session.get(MembershipFeePeriod, period_id)
            if not period:
                return

            results = session.query(MembershipFeePayment, Member).join(
                Member, MembershipFeePayment.member_id == Member.id
            ).filter(
                MembershipFeePayment.period_id == period_id
            ).all()

            rows = []
            total_due = Decimal("0")
            total_paid = Decimal("0")
            total_remaining = Decimal("0")

            status_text = {
                "paid": "Оплачено",
                "partial": "Частично",
                "not_paid": "Не оплачено",
                "overpaid": "Переплата",
            }

            for pay, member in results:
                status = pay.status
                tag = {
                    "paid": "paid",
                    "partial": "partial",
                    "not_paid": "not_paid",
                    "overpaid": "overpaid",
                }.get(status, "")
                remaining = pay.amount_due - pay.amount_paid

                total_due += pay.amount_due
                total_paid += pay.amount_paid
                total_remaining += remaining

                rows.append({
                    "id": pay.id,
                    "plot_number": member.plot_number,
                    "full_name": member.full_name,
                    "area": str(member.plot_area),
                    "amount_due": f"{pay.amount_due:.2f}",
                    "amount_paid": f"{pay.amount_paid:.2f}",
                    "remaining": f"{remaining:.2f}",
                    "status": status_text.get(status, status),
                    "tag": tag,
                })

            self.tree.load_data(rows)
            self.summary_label.configure(
                text=f"Начислено: {total_due:.2f}  |  Оплачено: {total_paid:.2f}  |  "
                     f"Остаток: {total_remaining:.2f}  |  Записей: {len(rows)}"
            )

    def _create_period(self):
        dialog = PeriodDialog(self.app)
        result = dialog.wait_for_result()
        if result:
            self.refresh_data()

    def _edit_period(self):
        period_id = self._get_current_period_id()
        if not period_id:
            messagebox.showwarning("Внимание", "Выберите период")
            return
        dialog = PeriodDialog(self.app, period_id=period_id)
        if dialog.wait_for_result():
            self.refresh_data()
            event_bus.publish("fee_paid")
            self.set_status("Период обновлён")

    def _delete_period(self):
        period_id = self._get_current_period_id()
        if not period_id:
            messagebox.showwarning("Внимание", "Выберите период")
            return

        with db_session(readonly=True) as session:
            period = session.get(MembershipFeePeriod, period_id)
            if not period:
                messagebox.showerror("Ошибка", "Период не найден")
                return
            payments_count = session.query(MembershipFeePayment).filter(
                MembershipFeePayment.period_id == period_id
            ).count()
            period_name = period.name

        if not messagebox.askyesno(
            "Удаление периода",
            f"Удалить период «{period_name}»?\n"
            f"Начисления будут удалены: {payments_count}",
        ):
            return

        try:
            with db_session() as session:
                period = session.get(MembershipFeePeriod, period_id)
                if period:
                    session.delete(period)
                    log_action(AuditAction.DELETE.value, "membership_fee_period",
                               period_id, period_name)
            self.refresh_data()
            event_bus.publish("fee_paid")
            self.set_status("Период удалён")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _generate_payments(self):
        period_id = self._get_current_period_id()
        if not period_id:
            messagebox.showwarning("Внимание", "Выберите период")
            return

        def _on_success(count):
            if count:
                log_action(AuditAction.CREATE.value, "membership_fee_payment", period_id,
                           f"Сгенерировано {count} записей")
                self.set_status(f"Сгенерировано {count} записей")
            else:
                self.set_status("Новых записей не создано")
            self._load_payments()
            event_bus.publish("fee_paid")

        ProgressDialog(
            self.app, "Генерация платежей...",
            target=lambda: generate_payments_for_period(period_id),
            on_success=_on_success,
            on_error=lambda e: messagebox.showerror("Ошибка", str(e)),
        )

    def _record_payment_dialog(self):
        iid = self.tree.get_selected_iid()
        if not iid:
            messagebox.showwarning("Внимание", "Выберите запись")
            return
        dialog = PaymentRecordDialog(self.app, payment_id=int(iid))
        result = dialog.wait_for_result()
        if result:
            self._load_payments()
            event_bus.publish("fee_paid")
            self.set_status("Оплата записана")

    def _subscribe_events(self):
        super()._subscribe_events()
        self._subscribe("member_updated", lambda **kw: self.refresh_data())
        self._subscribe("fee_paid", lambda **kw: self._load_payments())


class PeriodDialog(ModalDialog):
    def __init__(self, parent, period_id: int | None = None):
        self.period_id = period_id
        title = "Редактирование периода" if period_id else "Новый период"
        super().__init__(parent, title=title, width=420, height=360)
        self._build_form()
        if period_id:
            self._load_period()

    def _build_form(self):
        form = ctk.CTkFrame(self)
        form.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 0))

        ctk.CTkLabel(form, text="Название периода").pack(anchor="w", pady=(5, 0))
        self.name_entry = ctk.CTkEntry(form)
        self.name_entry.pack(fill="x", pady=(0, 5))
        self.name_entry.insert(0, f"Членские взносы {date.today().year}")

        ctk.CTkLabel(form, text="Год").pack(anchor="w", pady=(5, 0))
        self.year_entry = ctk.CTkEntry(form)
        self.year_entry.pack(fill="x", pady=(0, 5))
        self.year_entry.insert(0, str(date.today().year))

        ctk.CTkLabel(form, text="Ставка за сотку (руб.)").pack(anchor="w", pady=(5, 0))
        self.rate_entry = ctk.CTkEntry(form)
        self.rate_entry.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(form, text="Срок оплаты").pack(anchor="w", pady=(5, 0))
        self.due_date = DatePicker(form)
        self.due_date.pack(fill="x", pady=(0, 5))

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(side="bottom", fill="x", padx=10, pady=10)
        button_text = "Сохранить" if self.period_id else "Создать"
        ctk.CTkButton(btn_frame, text=button_text, command=self._save).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", fg_color="gray", command=self._on_cancel).pack(side="left", padx=5)

    def _load_period(self):
        with db_session(readonly=True) as session:
            period = session.get(MembershipFeePeriod, self.period_id)
            if not period:
                return
            self.name_entry.delete(0, "end")
            self.name_entry.insert(0, period.name)
            self.year_entry.delete(0, "end")
            self.year_entry.insert(0, str(period.year))
            self.rate_entry.delete(0, "end")
            self.rate_entry.insert(0, str(period.rate_per_sotka))
            self.due_date.set_date(period.due_date)

    def _save(self):
        name = self.name_entry.get().strip()
        try:
            year = int(self.year_entry.get().strip())
            rate = Decimal(self.rate_entry.get().strip()).quantize(Decimal("0.01"))
        except (ValueError, InvalidOperation):
            messagebox.showwarning("Внимание", "Проверьте числовые поля")
            return

        if rate <= 0:
            messagebox.showwarning("Внимание", "Ставка должна быть > 0")
            return
        if not (2000 <= year <= 2100):
            messagebox.showwarning("Внимание", "Год должен быть от 2000 до 2100")
            return

        due = self.due_date.get_date()
        if not due:
            messagebox.showwarning("Внимание", "Некорректная дата")
            return

        if not name:
            messagebox.showwarning("Внимание", "Введите название")
            return

        try:
            with db_session() as session:
                if self.period_id:
                    period = session.get(MembershipFeePeriod, self.period_id)
                    if not period:
                        messagebox.showerror("Ошибка", "Период не найден")
                        return
                    action = AuditAction.UPDATE.value
                else:
                    period = MembershipFeePeriod()
                    session.add(period)
                    action = AuditAction.CREATE.value

                period.name = name
                period.year = year
                period.rate_per_sotka = rate
                period.due_date = due
                session.flush()
                if self.period_id:
                    payments = session.query(MembershipFeePayment, Member).join(
                        Member, MembershipFeePayment.member_id == Member.id
                    ).filter(
                        MembershipFeePayment.period_id == period.id
                    ).all()
                    for payment, member in payments:
                        payment.amount_due = calculate_fee_for_member(period, member)
                log_action(action, "membership_fee_period", period.id, name)
            self._on_ok()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


class PaymentRecordDialog(ModalDialog):
    def __init__(self, parent, payment_id: int):
        super().__init__(parent, title="Записать оплату", width=350, height=250)
        self.payment_id = payment_id
        self._build_form()

    def _build_form(self):
        form = ctk.CTkFrame(self)
        form.pack(fill="both", expand=True, padx=10, pady=10)

        with db_session(readonly=True) as session:
            pay = session.get(MembershipFeePayment, self.payment_id)
            if pay:
                outstanding = pay.amount_due - pay.amount_paid
                member = session.get(Member, pay.member_id)
                info = f"{member.full_name if member else '?'} — Долг: {outstanding:.2f} руб."
                ctk.CTkLabel(form, text=info).pack(anchor="w", pady=5)

        ctk.CTkLabel(form, text="Сумма оплаты").pack(anchor="w", pady=(5, 0))
        self.amount_entry = ctk.CTkEntry(form)
        self.amount_entry.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(form, text="Дата оплаты").pack(anchor="w", pady=(5, 0))
        self.date_picker = DatePicker(form)
        self.date_picker.pack(fill="x", pady=(0, 5))

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(btn_frame, text="Записать", command=self._save).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", fg_color="gray", command=self._on_cancel).pack(side="left", padx=5)

    def _save(self):
        try:
            amount = Decimal(self.amount_entry.get().strip()).quantize(Decimal("0.01"))
            if amount <= 0:
                raise ValueError
        except (ValueError, InvalidOperation):
            messagebox.showwarning("Внимание", "Введите корректную сумму")
            return

        pay_date = self.date_picker.get_date()
        if not pay_date:
            messagebox.showwarning("Внимание", "Некорректная дата")
            return

        try:
            record_payment(self.payment_id, amount, pay_date)
            log_action(AuditAction.PAYMENT.value, "membership_fee_payment",
                       self.payment_id, f"Оплата {amount:.2f}")
            self._on_ok()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
