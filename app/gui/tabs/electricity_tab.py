"""Electricity tab — readings, tariffs, SNT meter, payments."""

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
from app.database.models.electricity import (
    ElectricityTariff, MeterReading, ElectricityPayment, SntMeterReading
)
from app.services.electricity_calculator import create_reading_and_payment
from app.services.audit_service import log_action
from app.constants import MemberStatus, AuditAction, PaymentStatus
from app.event_bus import event_bus


READING_COLUMNS = [
    {"id": "id", "text": "ID", "width": 40, "anchor": "center", "stretch": False},
    {"id": "plot_number", "text": "Участок", "width": 80, "anchor": "center"},
    {"id": "full_name", "text": "ФИО", "width": 200},
    {"id": "reading_date", "text": "Дата", "width": 100, "anchor": "center"},
    {"id": "previous_value", "text": "Пред.", "width": 80, "anchor": "e"},
    {"id": "value", "text": "Текущ.", "width": 80, "anchor": "e"},
    {"id": "consumption", "text": "Расход", "width": 80, "anchor": "e"},
    {"id": "amount_due", "text": "К оплате", "width": 100, "anchor": "e"},
    {"id": "status", "text": "Статус", "width": 90, "anchor": "center"},
]


class ElectricityTab(BaseTab):

    def _build_ui(self):
        # Toolbar
        toolbar = ctk.CTkFrame(self.frame)
        toolbar.pack(fill="x", padx=5, pady=5)

        ctk.CTkButton(toolbar, text="+ Показание", width=130,
                       command=self._add_reading).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Записать оплату", width=130,
                       command=self._record_payment).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Тарифы", width=100,
                       command=self._manage_tariffs).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Общий счётчик", width=130,
                       command=self._snt_meter).pack(side="left", padx=5)

        # Table
        table_frame = ctk.CTkFrame(self.frame)
        table_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.tree = StyledTreeview(
            table_frame, columns=READING_COLUMNS,
            style_name="Elec.Treeview",
        )
        self.tree.pack_with_scrollbar()

        self.summary_label = ctk.CTkLabel(self.frame, text="", font=ctk.CTkFont(size=11))
        self.summary_label.pack(fill="x", padx=10, pady=(0, 5))

    def refresh_data(self):
        self._load_readings()

    def _load_readings(self):
        with db_session(readonly=True) as session:
            results = session.query(MeterReading, Member, ElectricityPayment).join(
                Member, MeterReading.member_id == Member.id
            ).outerjoin(
                ElectricityPayment, ElectricityPayment.reading_id == MeterReading.id
            ).order_by(
                MeterReading.reading_date.desc(), MeterReading.id.desc()
            ).all()

            rows = []
            for r, member, payment in results:
                amount_due = ""
                status = ""
                tag = ""
                if payment:
                    amount_due = f"{payment.amount_due:.2f}"
                    st = payment.status
                    status = {"paid": "Оплачено", "partial": "Частично", "not_paid": "Не оплачено"}.get(st, st)
                    tag = {"paid": "paid", "partial": "partial", "not_paid": "not_paid"}.get(st, "")

                rows.append({
                    "id": r.id,
                    "plot_number": member.plot_number,
                    "full_name": member.full_name,
                    "reading_date": str(r.reading_date),
                    "previous_value": str(r.previous_value) if r.previous_value is not None else "—",
                    "value": str(r.value),
                    "consumption": str(r.consumption) if r.consumption is not None else "—",
                    "amount_due": amount_due,
                    "status": status,
                    "tag": tag,
                })

            self.tree.load_data(rows)
            self.summary_label.configure(text=f"Показаний: {len(rows)}")

    def _add_reading(self):
        dialog = ReadingDialog(self.app)
        if dialog.wait_for_result():
            self.refresh_data()

    def _record_payment(self):
        iid = self.tree.get_selected_iid()
        if not iid:
            messagebox.showwarning("Внимание", "Выберите запись")
            return

        reading_id = int(iid)
        with db_session(readonly=True) as session:
            payment = session.query(ElectricityPayment).filter(
                ElectricityPayment.reading_id == reading_id
            ).first()
            if not payment:
                messagebox.showinfo("Информация", "Нет начислений для этого показания")
                return
            payment_id = payment.id

        dialog = ElecPaymentDialog(self.app, payment_id=payment_id)
        if dialog.wait_for_result():
            self.refresh_data()
            event_bus.publish("fee_paid")

    def _manage_tariffs(self):
        dialog = TariffDialog(self.app)
        dialog.wait_for_result()

    def _snt_meter(self):
        dialog = SntMeterDialog(self.app)
        dialog.wait_for_result()

    def _subscribe_events(self):
        super()._subscribe_events()
        self._subscribe("member_updated", lambda **kw: self.refresh_data())


class ReadingDialog(ModalDialog):
    def __init__(self, parent):
        super().__init__(parent, title="Новое показание", width=450, height=400)
        self._build_form()

    def _build_form(self):
        form = ctk.CTkFrame(self)
        form.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(form, text="Участник").pack(anchor="w", pady=(5, 0))
        with db_session(readonly=True) as session:
            members = session.query(Member).filter(
                Member.status == MemberStatus.ACTIVE.value
            ).order_by(Member.plot_number).all()
            self._member_map = {f"{m.plot_number} — {m.full_name}": m.id for m in members}
            member_names = list(self._member_map.keys())

        self.member_var = ctk.StringVar(value=member_names[0] if member_names else "")
        self.member_menu = ctk.CTkOptionMenu(form, variable=self.member_var,
                                              values=member_names or ["—"], width=350,
                                              command=self._on_member_selected)
        self.member_menu.pack(fill="x", pady=(0, 5))

        self.prev_reading_label = ctk.CTkLabel(
            form, text="Предыдущее показание: —",
            font=ctk.CTkFont(size=11), text_color="gray"
        )
        self.prev_reading_label.pack(anchor="w", pady=(0, 5))

        ctk.CTkLabel(form, text="Дата показания").pack(anchor="w", pady=(5, 0))
        self.date_picker = DatePicker(form)
        self.date_picker.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(form, text="Показание счётчика").pack(anchor="w", pady=(5, 0))
        self.value_entry = ctk.CTkEntry(form)
        self.value_entry.pack(fill="x", pady=(0, 5))

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(btn_frame, text="Сохранить", command=self._save).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", fg_color="gray",
                       command=self._on_cancel).pack(side="left", padx=5)

        # Load previous reading for initial member
        if member_names:
            self._on_member_selected(member_names[0])

    def _on_member_selected(self, choice):
        member_id = self._member_map.get(choice)
        if not member_id:
            self.prev_reading_label.configure(text="Предыдущее показание: —")
            return
        with db_session(readonly=True) as session:
            last = session.query(MeterReading).filter(
                MeterReading.member_id == member_id
            ).order_by(MeterReading.reading_date.desc(), MeterReading.id.desc()).first()
            if last:
                self.prev_reading_label.configure(
                    text=f"Предыдущее показание: {last.value} (от {last.reading_date})"
                )
            else:
                self.prev_reading_label.configure(text="Предыдущее показание: нет данных")

    def _save(self):
        member_id = self._member_map.get(self.member_var.get())
        if not member_id:
            messagebox.showwarning("Внимание", "Выберите участника")
            return
        reading_date = self.date_picker.get_date()
        if not reading_date:
            messagebox.showwarning("Внимание", "Некорректная дата")
            return
        try:
            value = Decimal(self.value_entry.get().strip())
        except (ValueError, InvalidOperation):
            messagebox.showwarning("Внимание", "Некорректное показание")
            return

        try:
            result = create_reading_and_payment(member_id, reading_date, value)
            msg = f"Показание записано. Расход: {result['consumption'] or '—'}"
            if result["anomaly"]:
                msg += "\n⚠ Аномально высокое потребление!"
            if result["amount_due"]:
                msg += f"\nК оплате: {result['amount_due']:.2f} руб."
            messagebox.showinfo("Результат", msg)
            log_action(AuditAction.CREATE.value, "meter_reading", result["reading_id"],
                       f"Показание: {value}")
            self._on_ok()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


class ElecPaymentDialog(ModalDialog):
    def __init__(self, parent, payment_id: int):
        super().__init__(parent, title="Оплата электроэнергии", width=350, height=230)
        self.payment_id = payment_id
        self._build_form()

    def _build_form(self):
        form = ctk.CTkFrame(self)
        form.pack(fill="both", expand=True, padx=10, pady=10)

        with db_session(readonly=True) as session:
            pay = session.get(ElectricityPayment, self.payment_id)
            if pay:
                outstanding = pay.amount_due - pay.amount_paid
                ctk.CTkLabel(form, text=f"Долг: {outstanding:.2f} руб.").pack(anchor="w", pady=5)

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
            with db_session() as session:
                pay = session.get(ElectricityPayment, self.payment_id)
                if pay:
                    pay.amount_paid = pay.amount_paid + amount
                    pay.payment_date = pay_date
            log_action(AuditAction.PAYMENT.value, "electricity_payment",
                       self.payment_id, f"Оплата {amount:.2f}")
            self._on_ok()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


class TariffDialog(ModalDialog):
    def __init__(self, parent):
        super().__init__(parent, title="Тарифы электроэнергии", width=500, height=400)
        self._build_form()
        self._load_tariffs()

    def _build_form(self):
        add_frame = ctk.CTkFrame(self)
        add_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(add_frame, text="Название:").pack(side="left", padx=2)
        self.name_entry = ctk.CTkEntry(add_frame, width=100)
        self.name_entry.pack(side="left", padx=2)

        ctk.CTkLabel(add_frame, text="Руб/кВт·ч:").pack(side="left", padx=2)
        self.rate_entry = ctk.CTkEntry(add_frame, width=80)
        self.rate_entry.pack(side="left", padx=2)

        ctk.CTkLabel(add_frame, text="С:").pack(side="left", padx=2)
        self.from_date = DatePicker(add_frame)
        self.from_date.pack(side="left", padx=2)

        ctk.CTkButton(add_frame, text="Добавить", width=80,
                       command=self._add_tariff).pack(side="left", padx=5)

        self.tariff_list = ctk.CTkTextbox(self, state="disabled")
        self.tariff_list.pack(fill="both", expand=True, padx=10, pady=5)

        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(bottom_frame, text="Закрыть", fg_color="gray",
                       command=self._on_cancel).pack(side="right", padx=5)

    def _load_tariffs(self):
        with db_session(readonly=True) as session:
            tariffs = session.query(ElectricityTariff).order_by(
                ElectricityTariff.effective_from.desc()
            ).all()
            self.tariff_list.configure(state="normal")
            self.tariff_list.delete("1.0", "end")
            for t in tariffs:
                active = "✓" if t.is_active else "✗"
                self.tariff_list.insert(
                    "end",
                    f"[{active}] {t.name}: {t.rate_per_kwh} руб/кВт·ч, с {t.effective_from}\n"
                )
            if not tariffs:
                self.tariff_list.insert("end", "Нет тарифов")
            self.tariff_list.configure(state="disabled")

    def _add_tariff(self):
        name = self.name_entry.get().strip()
        try:
            rate = Decimal(self.rate_entry.get().strip())
        except (ValueError, InvalidOperation):
            messagebox.showwarning("Внимание", "Некорректная ставка")
            return
        if rate <= 0:
            messagebox.showwarning("Внимание", "Ставка должна быть > 0")
            return
        from_date = self.from_date.get_date()
        if not from_date or not name:
            messagebox.showwarning("Внимание", "Заполните все поля")
            return

        try:
            with db_session() as session:
                session.query(ElectricityTariff).update({"is_active": False})
                tariff = ElectricityTariff(
                    name=name, rate_per_kwh=rate,
                    effective_from=from_date, is_active=True
                )
                session.add(tariff)
            self._load_tariffs()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


class SntMeterDialog(ModalDialog):
    def __init__(self, parent):
        super().__init__(parent, title="Общий счётчик СНТ", width=500, height=400)
        self._build_form()
        self._load_readings()

    def _build_form(self):
        ctk.CTkLabel(
            self, text="Общий счётчик фиксирует показания для всего СНТ",
            font=ctk.CTkFont(size=11), text_color="gray"
        ).pack(padx=10, pady=(5, 0))

        add_frame = ctk.CTkFrame(self)
        add_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(add_frame, text="Дата:").pack(side="left", padx=2)
        self.date_picker = DatePicker(add_frame)
        self.date_picker.pack(side="left", padx=2)

        ctk.CTkLabel(add_frame, text="Показание:").pack(side="left", padx=2)
        self.value_entry = ctk.CTkEntry(add_frame, width=100)
        self.value_entry.pack(side="left", padx=2)

        ctk.CTkButton(add_frame, text="Добавить", width=80,
                       command=self._add_reading).pack(side="left", padx=5)

        self.readings_list = ctk.CTkTextbox(self, state="disabled")
        self.readings_list.pack(fill="both", expand=True, padx=10, pady=5)

        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(bottom_frame, text="Закрыть", fg_color="gray",
                       command=self._on_cancel).pack(side="right", padx=5)

    def _load_readings(self):
        with db_session(readonly=True) as session:
            readings = session.query(SntMeterReading).order_by(
                SntMeterReading.reading_date.desc()
            ).all()
            self.readings_list.configure(state="normal")
            self.readings_list.delete("1.0", "end")
            for r in readings:
                cons = f", расход: {r.consumption}" if r.consumption else ""
                self.readings_list.insert(
                    "end", f"{r.reading_date}: {r.value}{cons}\n"
                )
            if not readings:
                self.readings_list.insert("end", "Нет показаний")
            self.readings_list.configure(state="disabled")

    def _add_reading(self):
        rd = self.date_picker.get_date()
        try:
            val = Decimal(self.value_entry.get().strip())
        except (ValueError, InvalidOperation):
            messagebox.showwarning("Внимание", "Некорректное показание")
            return
        if not rd:
            messagebox.showwarning("Внимание", "Некорректная дата")
            return

        try:
            with db_session() as session:
                prev = session.query(SntMeterReading).order_by(
                    SntMeterReading.reading_date.desc()
                ).first()
                prev_val = prev.value if prev else None
                consumption = (val - prev_val) if prev_val is not None else None

                reading = SntMeterReading(
                    reading_date=rd, value=val,
                    previous_value=prev_val, consumption=consumption,
                )
                session.add(reading)
            self._load_readings()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
