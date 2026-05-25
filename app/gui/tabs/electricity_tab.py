"""Electricity tab — readings, tariffs, SNT meter, payments."""

from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from tkinter import messagebox
import customtkinter as ctk

from app.gui.tabs.base_tab import BaseTab
from app.gui.widgets.styled_treeview import StyledTreeview
from app.gui.widgets.date_picker import DatePicker
from app.gui.widgets.modal_dialog import ModalDialog
from app.gui.tabs.fee_payment_history_dialog import FeePaymentHistoryDialog
from app.database.engine import db_session
from app.database.models.member import Member
from app.database.models.electricity import (
    ElectricityTariff, MeterReading, ElectricityPayment, SntMeterReading
)
from app.services.electricity_calculator import (
    calculate_consumption, create_monthly_electricity_readings,
    get_month_bounds, get_previous_reading,
    get_reading_for_month, record_electricity_payment
)
from app.services.audit_service import log_action
from app.constants import MemberStatus, AuditAction
from app.event_bus import event_bus


READING_COLUMNS = [
    {"id": "row_num", "text": "№", "width": 45, "anchor": "center", "stretch": False},
    {"id": "period", "text": "Месяц", "width": 100, "anchor": "center"},
    {"id": "plot_number", "text": "Участок", "width": 80, "anchor": "center"},
    {"id": "full_name", "text": "ФИО", "width": 200},
    {"id": "reading_date", "text": "Дата", "width": 100, "anchor": "center"},
    {"id": "previous_value", "text": "Пред.", "width": 80, "anchor": "e"},
    {"id": "value", "text": "Текущ.", "width": 80, "anchor": "e"},
    {"id": "consumption", "text": "Расход", "width": 80, "anchor": "e"},
    {"id": "rate", "text": "Тариф", "width": 80, "anchor": "e"},
    {"id": "amount_due", "text": "Начислено", "width": 100, "anchor": "e"},
    {"id": "amount_paid", "text": "Оплачено", "width": 100, "anchor": "e"},
    {"id": "remaining", "text": "Остаток", "width": 100, "anchor": "e"},
    {"id": "status", "text": "Статус", "width": 90, "anchor": "center"},
]

MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


class ElectricityTab(BaseTab):

    def _build_ui(self):
        # Month selector
        selector = ctk.CTkFrame(self.frame)
        selector.pack(fill="x", padx=5, pady=(5, 2))

        ctk.CTkLabel(selector, text="Расчётный месяц:").pack(side="left", padx=5)
        self.month_var = ctk.StringVar()
        self.month_menu = ctk.CTkOptionMenu(
            selector,
            variable=self.month_var,
            values=["—"],
            command=self._on_month_selected,
            width=220,
        )
        self.month_menu.pack(side="left", padx=5)

        # Actions
        toolbar = ctk.CTkFrame(self.frame)
        toolbar.pack(fill="x", padx=5, pady=(2, 5))

        ctk.CTkButton(toolbar, text="+ Месячный ввод", width=150,
                       command=self._add_monthly_readings).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Записать оплату", width=130,
                       command=self._record_payment).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="История оплат", width=120,
                       command=self._show_payment_history).pack(side="left", padx=5)
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

        self._months: dict[str, tuple[int, int]] = {}

    def refresh_data(self):
        self._load_months()

    def _format_month_label(self, year: int, month: int) -> str:
        return f"{MONTH_NAMES[month - 1]} {year}"

    def _load_months(self):
        today = date.today()
        month_values = {(today.year, today.month)}
        with db_session(readonly=True) as session:
            for (reading_date,) in session.query(MeterReading.reading_date).all():
                month_values.add((reading_date.year, reading_date.month))
            for (period_end,) in session.query(ElectricityPayment.period_end).all():
                month_values.add((period_end.year, period_end.month))

        ordered = sorted(month_values, reverse=True)
        self._months = {
            self._format_month_label(year, month): (year, month)
            for year, month in ordered
        }
        labels = list(self._months.keys())
        self.month_menu.configure(values=labels or ["—"])
        if labels and self.month_var.get() not in labels:
            self.month_var.set(labels[0])
        self._load_readings()

    def _on_month_selected(self, _):
        self._load_readings()

    def _get_current_month(self) -> tuple[int, int] | None:
        return self._months.get(self.month_var.get())

    def _load_readings(self):
        current = self._get_current_month()
        if not current:
            self.tree.load_data([])
            self.summary_label.configure(text="")
            return

        year, month = current
        period_start, period_end = get_month_bounds(year, month)
        with db_session(readonly=True) as session:
            results = session.query(MeterReading, Member, ElectricityPayment).join(
                Member, MeterReading.member_id == Member.id
            ).outerjoin(
                ElectricityPayment, ElectricityPayment.reading_id == MeterReading.id
            ).filter(
                MeterReading.reading_date >= period_start,
                MeterReading.reading_date <= period_end,
            ).order_by(
                Member.plot_number.asc(), MeterReading.reading_date.desc()
            ).all()

            rows = []
            total_consumption = Decimal("0")
            total_due = Decimal("0")
            total_paid = Decimal("0")
            total_remaining = Decimal("0")
            for row_num, (r, member, payment) in enumerate(results, start=1):
                row_id = f"reading:{r.id}"
                amount_due = "—"
                amount_paid = "—"
                remaining = "—"
                rate = "—"
                status = "База"
                tag = ""
                if payment:
                    row_id = f"payment:{payment.id}"
                    rate = f"{payment.rate_per_kwh:.4f}"
                    amount_due = f"{payment.amount_due:.2f}"
                    amount_paid = f"{payment.amount_paid:.2f}"
                    rest = payment.amount_due - payment.amount_paid
                    remaining = f"{rest:.2f}"
                    total_due += payment.amount_due
                    total_paid += payment.amount_paid
                    total_remaining += rest
                    st = payment.status
                    status = {
                        "paid": "Оплачено",
                        "partial": "Частично",
                        "not_paid": "Не оплачено",
                        "overpaid": "Переплата",
                    }.get(st, st)
                    tag = {
                        "paid": "paid",
                        "partial": "partial",
                        "not_paid": "not_paid",
                        "overpaid": "overpaid",
                    }.get(st, "")
                elif r.previous_value is not None:
                    status = "Нет начисления"
                if r.consumption is not None:
                    total_consumption += r.consumption

                rows.append({
                    "id": row_id,
                    "row_num": row_num,
                    "period": self._format_month_label(year, month),
                    "plot_number": member.plot_number,
                    "full_name": member.full_name,
                    "reading_date": str(r.reading_date),
                    "previous_value": str(r.previous_value) if r.previous_value is not None else "—",
                    "value": str(r.value),
                    "consumption": str(r.consumption) if r.consumption is not None else "—",
                    "rate": rate,
                    "amount_due": amount_due,
                    "amount_paid": amount_paid,
                    "remaining": remaining,
                    "status": status,
                    "tag": tag,
                })

            self.tree.load_data(rows)
            self.summary_label.configure(
                text=(
                    f"Месяц: {self._format_month_label(year, month)}  |  "
                    f"Показаний: {len(rows)}  |  Расход: {total_consumption:.2f} кВт·ч  |  "
                    f"Начислено: {total_due:.2f}  |  Оплачено: {total_paid:.2f}  |  "
                    f"Остаток: {total_remaining:.2f}"
                )
            )

    def _add_monthly_readings(self):
        current = self._get_current_month()
        today = date.today()
        year, month = current if current else (today.year, today.month)
        dialog = MonthlyReadingsDialog(self.app, year=year, month=month)
        if dialog.wait_for_result():
            self.refresh_data()
            event_bus.publish("fee_paid")

    def _record_payment(self):
        iid = self.tree.get_selected_iid()
        if not iid:
            messagebox.showwarning("Внимание", "Выберите запись")
            return

        if not iid.startswith("payment:"):
            messagebox.showinfo("Информация", "Для базового показания нет начисления")
            return
        payment_id = int(iid.split(":", 1)[1])

        dialog = ElecPaymentDialog(self.app, payment_id=payment_id)
        if dialog.wait_for_result():
            self.refresh_data()
            event_bus.publish("fee_paid")

    def _show_payment_history(self):
        iid = self.tree.get_selected_iid()
        if not iid:
            messagebox.showwarning("Внимание", "Выберите запись")
            return
        if not iid.startswith("payment:"):
            messagebox.showinfo("Информация", "Для базового показания нет оплат")
            return
        dialog = FeePaymentHistoryDialog(
            self.app,
            payment_type="electricity",
            payment_id=int(iid.split(":", 1)[1]),
        )
        dialog.wait_for_result()

    def _manage_tariffs(self):
        dialog = TariffDialog(self.app)
        dialog.wait_for_result()

    def _snt_meter(self):
        dialog = SntMeterDialog(self.app)
        dialog.wait_for_result()

    def _subscribe_events(self):
        super()._subscribe_events()
        self._subscribe("member_updated", lambda **kw: self.refresh_data())
        self._subscribe("fee_paid", lambda **kw: self._load_readings())


class MonthlyReadingsDialog(ModalDialog):
    def __init__(self, parent, year: int, month: int):
        self.year = year
        self.month = month
        self._entries: dict[int, ctk.CTkEntry] = {}
        super().__init__(parent, title="Месячный ввод электроэнергии", width=760, height=620)
        self._build_form()
        self._load_rows()

    def _build_form(self):
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(top, text="Месяц").pack(side="left", padx=(8, 4))
        self.month_var = ctk.StringVar(value=MONTH_NAMES[self.month - 1])
        self.month_menu = ctk.CTkOptionMenu(
            top,
            variable=self.month_var,
            values=MONTH_NAMES,
            width=140,
        )
        self.month_menu.pack(side="left", padx=4)

        ctk.CTkLabel(top, text="Год").pack(side="left", padx=(12, 4))
        self.year_entry = ctk.CTkEntry(top, width=80)
        self.year_entry.pack(side="left", padx=4)
        self.year_entry.insert(0, str(self.year))

        ctk.CTkButton(
            top, text="Загрузить месяц", width=140,
            command=self._load_rows,
        ).pack(side="left", padx=12)

        self.rows_frame = ctk.CTkScrollableFrame(self)
        self.rows_frame.pack(fill="both", expand=True, padx=10, pady=5)

        bottom = ctk.CTkFrame(self)
        bottom.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(bottom, text="Сохранить начисления", width=170,
                       command=self._save).pack(side="left", padx=5)
        ctk.CTkButton(bottom, text="Отмена", fg_color="gray",
                       command=self._on_cancel).pack(side="left", padx=5)

    def _read_period(self) -> tuple[int, int] | None:
        try:
            year = int(self.year_entry.get().strip())
            month = MONTH_NAMES.index(self.month_var.get()) + 1
        except (ValueError, IndexError):
            messagebox.showwarning("Внимание", "Проверьте месяц и год")
            return None
        if not (2000 <= year <= 2100):
            messagebox.showwarning("Внимание", "Год должен быть от 2000 до 2100")
            return None
        return year, month

    def _load_rows(self):
        period = self._read_period()
        if not period:
            return
        year, month = period
        period_start, period_end = get_month_bounds(year, month)

        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._entries = {}

        header = ctk.CTkFrame(self.rows_frame)
        header.pack(fill="x", pady=(0, 4))
        for text, width in [
            ("Участок", 80),
            ("ФИО", 230),
            ("Предыдущее", 130),
            ("Текущее", 120),
            ("Статус", 120),
        ]:
            ctk.CTkLabel(
                header,
                text=text,
                width=width,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=2)

        with db_session(readonly=True) as session:
            members = session.query(Member).filter(
                Member.status == MemberStatus.ACTIVE.value
            ).order_by(Member.plot_number).all()

            if not members:
                ctk.CTkLabel(self.rows_frame, text="Нет активных участников").pack(pady=20)
                return

            for member in members:
                previous = get_previous_reading(session, member.id, period_start)
                existing = get_reading_for_month(
                    session, member.id, period_start, period_end
                )
                previous_text = (
                    f"{previous.value} от {previous.reading_date}"
                    if previous else "нет, базовое"
                )
                status_text = "уже введено" if existing else "новое"

                row = ctk.CTkFrame(self.rows_frame)
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(row, text=member.plot_number, width=80).pack(side="left", padx=2)
                ctk.CTkLabel(row, text=member.full_name, width=230, anchor="w").pack(side="left", padx=2)
                ctk.CTkLabel(row, text=previous_text, width=130, anchor="w").pack(side="left", padx=2)
                entry = ctk.CTkEntry(row, width=120)
                entry.pack(side="left", padx=2)
                if existing:
                    entry.insert(0, str(existing.value))
                ctk.CTkLabel(row, text=status_text, width=120).pack(side="left", padx=2)
                self._entries[member.id] = entry

    def _save(self):
        period = self._read_period()
        if not period:
            return
        year, month = period

        values: dict[int, Decimal] = {}
        for member_id, entry in self._entries.items():
            raw = entry.get().strip()
            if not raw:
                continue
            try:
                value = Decimal(raw)
            except (ValueError, InvalidOperation):
                messagebox.showwarning("Внимание", "Проверьте введённые показания")
                return
            if value < 0:
                messagebox.showwarning("Внимание", "Показание не может быть отрицательным")
                return
            values[member_id] = value

        if not values:
            messagebox.showwarning("Внимание", "Введите хотя бы одно показание")
            return

        try:
            result = create_monthly_electricity_readings(year, month, values)
            message = (
                f"Показания: +{result['created_readings']} / обновлено {result['updated_readings']}\n"
                f"Начисления: +{result['created_payments']} / обновлено {result['updated_payments']}\n"
                f"Базовых показаний без начисления: {result['baseline_readings']}"
            )
            if result["missing_tariff"]:
                message += "\n\nДля части начислений нет тарифа на конец месяца."
            if result["anomalies"]:
                message += f"\n\nАномально высокий расход: {len(result['anomalies'])}"
            messagebox.showinfo("Электроэнергия", message)
            log_action(AuditAction.CREATE.value, "electricity_month",
                       None, f"{MONTH_NAMES[month - 1]} {year}: {len(values)} показаний")
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
            record_electricity_payment(self.payment_id, amount, pay_date)
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
                period = f"с {t.effective_from}"
                if t.effective_to:
                    period += f" по {t.effective_to}"
                self.tariff_list.insert(
                    "end",
                    f"[{active}] {t.name}: {t.rate_per_kwh} руб/кВт·ч, {period}\n"
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
                from sqlalchemy import or_

                session.query(ElectricityTariff).filter(
                    ElectricityTariff.effective_from == from_date
                ).update({"is_active": False})

                previous = session.query(ElectricityTariff).filter(
                    ElectricityTariff.is_active.is_(True),
                    ElectricityTariff.effective_from < from_date,
                    or_(
                        ElectricityTariff.effective_to.is_(None),
                        ElectricityTariff.effective_to >= from_date,
                    ),
                ).order_by(ElectricityTariff.effective_from.desc()).first()
                if previous:
                    previous.effective_to = from_date - timedelta(days=1)

                next_tariff = session.query(ElectricityTariff).filter(
                    ElectricityTariff.is_active.is_(True),
                    ElectricityTariff.effective_from > from_date,
                ).order_by(ElectricityTariff.effective_from.asc()).first()
                effective_to = (
                    next_tariff.effective_from - timedelta(days=1)
                    if next_tariff else None
                )

                tariff = ElectricityTariff(
                    name=name, rate_per_kwh=rate,
                    effective_from=from_date, effective_to=effective_to,
                    is_active=True,
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
                consumption = (
                    calculate_consumption(val, prev_val)
                    if prev_val is not None else None
                )

                reading = SntMeterReading(
                    reading_date=rd, value=val,
                    previous_value=prev_val, consumption=consumption,
                )
                session.add(reading)
            self._load_readings()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
