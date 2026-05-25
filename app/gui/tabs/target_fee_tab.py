"""Target fee tab — campaigns, payments, documents."""

from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
from tkinter import messagebox, filedialog
import shutil
import customtkinter as ctk

from app.gui.tabs.base_tab import BaseTab
from app.gui.widgets.styled_treeview import StyledTreeview
from app.gui.widgets.date_picker import DatePicker
from app.gui.widgets.modal_dialog import ModalDialog
from app.gui.tabs.fee_payment_history_dialog import FeePaymentHistoryDialog
from app.database.engine import db_session
from app.database.models.member import Member
from app.database.models.target_fee import (
    TargetFeeCampaign, TargetFeePayment, TargetFeeDocument
)
from app.constants import MemberStatus, TargetFeeType, AuditAction
from app.services.audit_service import log_action
from app.event_bus import event_bus
from app.gui.widgets.progress_dialog import ProgressDialog
from app.config import DATA_DIR


TARGET_PAYMENT_COLUMNS = [
    {"id": "row_num", "text": "№", "width": 45, "anchor": "center", "stretch": False},
    {"id": "plot_number", "text": "Участок", "width": 80, "anchor": "center"},
    {"id": "full_name", "text": "ФИО", "width": 220},
    {"id": "amount_due", "text": "Начислено", "width": 100, "anchor": "e"},
    {"id": "amount_paid", "text": "Оплачено", "width": 100, "anchor": "e"},
    {"id": "remaining", "text": "Осталось", "width": 100, "anchor": "e"},
    {"id": "payment_date", "text": "Дата оплаты", "width": 100, "anchor": "center"},
    {"id": "status", "text": "Статус", "width": 100, "anchor": "center"},
]


class TargetFeeTab(BaseTab):

    def _build_ui(self):
        # Campaign selector — row 1
        row1 = ctk.CTkFrame(self.frame)
        row1.pack(fill="x", padx=5, pady=(5, 2))

        ctk.CTkLabel(row1, text="Кампания:").pack(side="left", padx=5)
        self.campaign_var = ctk.StringVar()
        self.campaign_menu = ctk.CTkOptionMenu(
            row1, variable=self.campaign_var,
            values=["—"], command=self._on_campaign_selected, width=300
        )
        self.campaign_menu.pack(side="left", padx=5)

        # Action buttons — row 2
        row2 = ctk.CTkFrame(self.frame)
        row2.pack(fill="x", padx=5, pady=(2, 5))

        ctk.CTkButton(row2, text="+ Новая кампания", width=150,
                       command=self._create_campaign).pack(side="left", padx=5)
        ctk.CTkButton(row2, text="Редактировать", width=120,
                       command=self._edit_campaign).pack(side="left", padx=5)
        ctk.CTkButton(row2, text="Удалить", width=90,
                       command=self._delete_campaign).pack(side="left", padx=5)
        ctk.CTkButton(row2, text="Сгенерировать", width=130,
                       command=self._generate_payments).pack(side="left", padx=5)
        ctk.CTkButton(row2, text="Записать оплату", width=130,
                       command=self._record_payment_dialog).pack(side="left", padx=5)
        ctk.CTkButton(row2, text="История оплат", width=120,
                       command=self._show_payment_history).pack(side="left", padx=5)
        ctk.CTkButton(row2, text="Документы", width=100,
                       command=self._manage_documents).pack(side="left", padx=5)

        # Table
        table_frame = ctk.CTkFrame(self.frame)
        table_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.tree = StyledTreeview(
            table_frame, columns=TARGET_PAYMENT_COLUMNS,
            style_name="TFee.Treeview",
        )
        self.tree.pack_with_scrollbar()

        self.summary_label = ctk.CTkLabel(self.frame, text="", font=ctk.CTkFont(size=11))
        self.summary_label.pack(fill="x", padx=10, pady=(0, 5))

        self._campaigns: dict[str, int] = {}

    def refresh_data(self):
        self._load_campaigns()

    def _load_campaigns(self):
        with db_session(readonly=True) as session:
            campaigns = session.query(TargetFeeCampaign).order_by(
                TargetFeeCampaign.id.desc()
            ).all()
            self._campaigns = {}
            names = []
            for c in campaigns:
                type_text = "за сот." if c.fee_type == TargetFeeType.PER_SOTKA.value else "фикс."
                label = f"{c.name} ({type_text}, {c.amount:.2f} руб.)"
                self._campaigns[label] = c.id
                names.append(label)
            if names:
                self.campaign_menu.configure(values=names)
                if not self.campaign_var.get() or self.campaign_var.get() not in names:
                    self.campaign_var.set(names[0])
                self._load_payments()
            else:
                self.campaign_menu.configure(values=["—"])
                self.campaign_var.set("—")
                self.tree.load_data([])
                self.summary_label.configure(text="")

    def _on_campaign_selected(self, _):
        self._load_payments()

    def _get_current_campaign_id(self) -> int | None:
        return self._campaigns.get(self.campaign_var.get())

    def _load_payments(self):
        cid = self._get_current_campaign_id()
        if not cid:
            self.tree.load_data([])
            return

        with db_session(readonly=True) as session:
            results = session.query(TargetFeePayment, Member).join(
                Member, TargetFeePayment.member_id == Member.id
            ).filter(
                TargetFeePayment.campaign_id == cid
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

            for row_num, (pay, member) in enumerate(results, start=1):
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
                    "row_num": row_num,
                    "plot_number": member.plot_number,
                    "full_name": member.full_name,
                    "amount_due": f"{pay.amount_due:.2f}",
                    "amount_paid": f"{pay.amount_paid:.2f}",
                    "remaining": f"{remaining:.2f}",
                    "payment_date": str(pay.payment_date) if pay.payment_date else "—",
                    "status": status_text.get(status, status),
                    "tag": tag,
                })

            self.tree.load_data(rows)
            self.summary_label.configure(
                text=f"Начислено: {total_due:.2f}  |  Оплачено: {total_paid:.2f}  |  Осталось: {total_remaining:.2f}  |  Записей: {len(rows)}"
            )

    def _create_campaign(self):
        dialog = CampaignDialog(self.app)
        if dialog.wait_for_result():
            self.refresh_data()

    def _edit_campaign(self):
        cid = self._get_current_campaign_id()
        if not cid:
            messagebox.showwarning("Внимание", "Выберите кампанию")
            return
        dialog = CampaignDialog(self.app, campaign_id=cid)
        if dialog.wait_for_result():
            self.refresh_data()
            event_bus.publish("fee_paid")
            self.set_status("Кампания обновлена")

    def _delete_campaign(self):
        cid = self._get_current_campaign_id()
        if not cid:
            messagebox.showwarning("Внимание", "Выберите кампанию")
            return

        with db_session(readonly=True) as session:
            campaign = session.get(TargetFeeCampaign, cid)
            if not campaign:
                messagebox.showerror("Ошибка", "Кампания не найдена")
                return
            payments_count = session.query(TargetFeePayment).filter(
                TargetFeePayment.campaign_id == cid
            ).count()
            docs_count = session.query(TargetFeeDocument).filter(
                TargetFeeDocument.campaign_id == cid
            ).count()
            campaign_name = campaign.name

        if not messagebox.askyesno(
            "Удаление кампании",
            f"Удалить кампанию «{campaign_name}»?\n"
            f"Начисления будут удалены: {payments_count}\n"
            f"Документы в записи кампании: {docs_count}",
        ):
            return

        try:
            with db_session() as session:
                campaign = session.get(TargetFeeCampaign, cid)
                if campaign:
                    session.delete(campaign)
                    log_action(AuditAction.DELETE.value, "target_fee_campaign",
                               cid, campaign_name)
            self.refresh_data()
            event_bus.publish("fee_paid")
            self.set_status("Кампания удалена")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _generate_payments(self):
        cid = self._get_current_campaign_id()
        if not cid:
            messagebox.showwarning("Внимание", "Выберите кампанию")
            return

        def _do_generate():
            with db_session() as session:
                campaign = session.get(TargetFeeCampaign, cid)
                if not campaign:
                    return 0

                members = session.query(Member).filter(
                    Member.status == MemberStatus.ACTIVE.value
                ).all()
                existing = {
                    p.member_id for p in
                    session.query(TargetFeePayment.member_id).filter(
                        TargetFeePayment.campaign_id == cid
                    ).all()
                }
                count = 0
                for m in members:
                    if m.id in existing:
                        continue
                    if campaign.fee_type == TargetFeeType.PER_SOTKA.value:
                        amount = (campaign.amount * m.plot_area).quantize(Decimal("0.01"))
                    else:
                        amount = campaign.amount
                    session.add(TargetFeePayment(
                        campaign_id=cid, member_id=m.id,
                        amount_due=amount, amount_paid=Decimal("0")
                    ))
                    count += 1
            return count

        def _on_success(count):
            self.set_status(f"Сгенерировано {count} записей")
            self._load_payments()
            event_bus.publish("fee_paid")

        ProgressDialog(
            self.app, "Генерация платежей...",
            target=_do_generate,
            on_success=_on_success,
            on_error=lambda e: messagebox.showerror("Ошибка", str(e)),
        )

    def _record_payment_dialog(self):
        iid = self.tree.get_selected_iid()
        if not iid:
            messagebox.showwarning("Внимание", "Выберите запись")
            return
        dialog = TargetPaymentRecordDialog(self.app, payment_id=int(iid))
        if dialog.wait_for_result():
            self._load_payments()
            event_bus.publish("fee_paid")
            self.set_status("Оплата записана")

    def _show_payment_history(self):
        iid = self.tree.get_selected_iid()
        if not iid:
            messagebox.showwarning("Внимание", "Выберите запись")
            return
        dialog = FeePaymentHistoryDialog(
            self.app,
            payment_type="target",
            payment_id=int(iid),
        )
        dialog.wait_for_result()

    def _manage_documents(self):
        cid = self._get_current_campaign_id()
        if not cid:
            messagebox.showwarning("Внимание", "Выберите кампанию")
            return
        dialog = DocumentsDialog(self.app, campaign_id=cid)
        dialog.wait_for_result()

    def _subscribe_events(self):
        super()._subscribe_events()
        self._subscribe("member_updated", lambda **kw: self.refresh_data())


class CampaignDialog(ModalDialog):
    def __init__(self, parent, campaign_id: int | None = None):
        self.campaign_id = campaign_id
        title = "Редактирование кампании" if campaign_id else "Новая кампания"
        super().__init__(parent, title=title, width=500, height=430)
        self._build_form()
        if campaign_id:
            self._load_campaign()

    def _build_form(self):
        form = ctk.CTkFrame(self)
        form.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(form, text="Название").pack(anchor="w", pady=(5, 0))
        self.name_entry = ctk.CTkEntry(form)
        self.name_entry.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(form, text="Описание").pack(anchor="w", pady=(5, 0))
        self.desc_entry = ctk.CTkTextbox(form, height=60)
        self.desc_entry.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(form, text="Тип").pack(anchor="w", pady=(5, 0))
        self.type_var = ctk.StringVar(value="fixed")
        type_frame = ctk.CTkFrame(form)
        type_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkRadioButton(type_frame, text="Фиксированная", variable=self.type_var,
                            value="fixed").pack(side="left", padx=10)
        ctk.CTkRadioButton(type_frame, text="За сотку", variable=self.type_var,
                            value="per_sotka").pack(side="left", padx=10)

        ctk.CTkLabel(form, text="Сумма (руб.)").pack(anchor="w", pady=(5, 0))
        self.amount_entry = ctk.CTkEntry(form)
        self.amount_entry.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(form, text="Срок оплаты").pack(anchor="w", pady=(5, 0))
        self.due_date = DatePicker(form)
        self.due_date.pack(fill="x", pady=(0, 5))

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)
        button_text = "Сохранить" if self.campaign_id else "Создать"
        ctk.CTkButton(btn_frame, text=button_text, command=self._save).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", fg_color="gray",
                       command=self._on_cancel).pack(side="left", padx=5)

    def _load_campaign(self):
        with db_session(readonly=True) as session:
            campaign = session.get(TargetFeeCampaign, self.campaign_id)
            if not campaign:
                return
            self.name_entry.delete(0, "end")
            self.name_entry.insert(0, campaign.name)
            self.desc_entry.delete("1.0", "end")
            self.desc_entry.insert("1.0", campaign.description or "")
            self.type_var.set(campaign.fee_type)
            self.amount_entry.delete(0, "end")
            self.amount_entry.insert(0, str(campaign.amount))
            self.due_date.set_date(campaign.due_date)

    def _save(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("Внимание", "Введите название")
            return
        try:
            amount = Decimal(self.amount_entry.get().strip()).quantize(Decimal("0.01"))
        except (ValueError, InvalidOperation):
            messagebox.showwarning("Внимание", "Некорректная сумма")
            return
        if amount <= 0:
            messagebox.showwarning("Внимание", "Сумма должна быть > 0")
            return
        due = self.due_date.get_date()
        if not due:
            messagebox.showwarning("Внимание", "Некорректная дата")
            return

        try:
            with db_session() as session:
                if self.campaign_id:
                    campaign = session.get(TargetFeeCampaign, self.campaign_id)
                    if not campaign:
                        messagebox.showerror("Ошибка", "Кампания не найдена")
                        return
                    action = AuditAction.UPDATE.value
                else:
                    campaign = TargetFeeCampaign()
                    session.add(campaign)
                    action = AuditAction.CREATE.value

                campaign.name = name
                campaign.description = self.desc_entry.get("1.0", "end").strip() or None
                campaign.fee_type = self.type_var.get()
                campaign.amount = amount
                campaign.due_date = due
                session.flush()
                if self.campaign_id:
                    payments = session.query(TargetFeePayment, Member).join(
                        Member, TargetFeePayment.member_id == Member.id
                    ).filter(
                        TargetFeePayment.campaign_id == campaign.id
                    ).all()
                    for payment, member in payments:
                        if campaign.fee_type == TargetFeeType.PER_SOTKA.value:
                            payment.amount_due = (campaign.amount * member.plot_area).quantize(Decimal("0.01"))
                        else:
                            payment.amount_due = campaign.amount
                log_action(action, "target_fee_campaign", campaign.id, name)
            self._on_ok()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


class TargetPaymentRecordDialog(ModalDialog):
    def __init__(self, parent, payment_id: int):
        super().__init__(parent, title="Записать оплату", width=400, height=280)
        self.payment_id = payment_id
        self._build_form()

    def _build_form(self):
        form = ctk.CTkFrame(self)
        form.pack(fill="both", expand=True, padx=10, pady=10)

        with db_session(readonly=True) as session:
            pay = session.get(TargetFeePayment, self.payment_id)
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
        ctk.CTkButton(btn_frame, text="Отмена", fg_color="gray",
                       command=self._on_cancel).pack(side="left", padx=5)

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
            from app.database.models.payment_history import PaymentHistory
            with db_session() as session:
                pay = session.get(TargetFeePayment, self.payment_id)
                if pay:
                    pay.amount_paid = pay.amount_paid + amount
                    pay.payment_date = pay_date
                    session.add(PaymentHistory(
                        payment_type="target",
                        payment_id=pay.id,
                        member_id=pay.member_id,
                        amount=amount,
                        payment_date=pay_date,
                    ))
            log_action(AuditAction.PAYMENT.value, "target_fee_payment",
                       self.payment_id, f"Оплата {amount:.2f}")
            self._on_ok()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


class DocumentsDialog(ModalDialog):
    def __init__(self, parent, campaign_id: int):
        super().__init__(parent, title="Документы кампании", width=500, height=350)
        self.campaign_id = campaign_id
        self._build_form()
        self._load_docs()

    def _build_form(self):
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(btn_frame, text="Прикрепить файл", command=self._attach).pack(side="left", padx=5)

        self.docs_list = ctk.CTkTextbox(self, state="disabled")
        self.docs_list.pack(fill="both", expand=True, padx=10, pady=5)

    def _load_docs(self):
        with db_session(readonly=True) as session:
            docs = session.query(TargetFeeDocument).filter(
                TargetFeeDocument.campaign_id == self.campaign_id
            ).all()
            self.docs_list.configure(state="normal")
            self.docs_list.delete("1.0", "end")
            for d in docs:
                self.docs_list.insert("end", f"{d.file_name} — {d.file_path}\n")
            if not docs:
                self.docs_list.insert("end", "Нет документов")
            self.docs_list.configure(state="disabled")

    def _attach(self):
        file_path = filedialog.askopenfilename(title="Выберите файл")
        if not file_path:
            return
        import os
        file_name = os.path.basename(file_path)

        # Copy to data dir
        docs_dir = DATA_DIR / "documents"
        docs_dir.mkdir(exist_ok=True)
        dest = docs_dir / file_name
        try:
            shutil.copy2(file_path, dest)
        except Exception as e:
            messagebox.showerror("Ошибка копирования", str(e))
            return

        try:
            with db_session() as session:
                doc = TargetFeeDocument(
                    campaign_id=self.campaign_id,
                    file_name=file_name,
                    file_path=str(dest),
                )
                session.add(doc)
            self._load_docs()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
