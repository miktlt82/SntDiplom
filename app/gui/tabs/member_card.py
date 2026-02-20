"""Member card dialog for adding/editing members."""

from __future__ import annotations
import re
from decimal import Decimal, InvalidOperation
from tkinter import messagebox
import customtkinter as ctk

from app.gui.widgets.modal_dialog import ModalDialog
from app.database.engine import db_session
from app.database.models.member import Member, MemberStatusHistory
from app.constants import MemberStatus, AuditAction
from app.services.audit_service import log_action


class MemberCardDialog(ModalDialog):
    def __init__(self, parent, member_id: int | None = None):
        title = "Редактирование участника" if member_id else "Новый участник"
        super().__init__(parent, title=title, width=500, height=520)
        self.member_id = member_id
        self._build_form()
        if member_id:
            self._load_member()

    def _build_form(self):
        form = ctk.CTkScrollableFrame(self)
        form.pack(fill="both", expand=True, padx=10, pady=10)

        fields = [
            ("Фамилия *", "last_name"),
            ("Имя *", "first_name"),
            ("Отчество", "patronymic"),
            ("Номер участка *", "plot_number"),
            ("Площадь (сот.) *", "plot_area"),
            ("Телефон", "phone"),
            ("Email", "email"),
            ("Адрес", "address"),
        ]

        self._entries = {}
        for label_text, field_name in fields:
            ctk.CTkLabel(form, text=label_text).pack(anchor="w", pady=(5, 0))
            if field_name == "address":
                entry = ctk.CTkTextbox(form, height=60)
                entry.pack(fill="x", pady=(0, 5))
            else:
                entry = ctk.CTkEntry(form)
                entry.pack(fill="x", pady=(0, 5))
            self._entries[field_name] = entry

        ctk.CTkLabel(form, text="Заметки").pack(anchor="w", pady=(5, 0))
        self._entries["notes"] = ctk.CTkTextbox(form, height=60)
        self._entries["notes"].pack(fill="x", pady=(0, 5))

        # Buttons
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkButton(btn_frame, text="Сохранить", command=self._save).pack(
            side="left", padx=5
        )
        ctk.CTkButton(
            btn_frame, text="Отмена", fg_color="gray", command=self._on_cancel
        ).pack(side="left", padx=5)

    def _load_member(self):
        with db_session(readonly=True) as session:
            member = session.get(Member, self.member_id)
            if not member:
                return
            self._set_field("last_name", member.last_name)
            self._set_field("first_name", member.first_name)
            self._set_field("patronymic", member.patronymic or "")
            self._set_field("plot_number", member.plot_number)
            self._set_field("plot_area", str(member.plot_area))
            self._set_field("phone", member.phone or "")
            self._set_field("email", member.email or "")
            self._set_textbox("address", member.address or "")
            self._set_textbox("notes", member.notes or "")

    def _set_field(self, name: str, value: str):
        entry = self._entries[name]
        if isinstance(entry, ctk.CTkEntry):
            entry.delete(0, "end")
            entry.insert(0, value)

    def _set_textbox(self, name: str, value: str):
        entry = self._entries[name]
        if isinstance(entry, ctk.CTkTextbox):
            entry.delete("1.0", "end")
            entry.insert("1.0", value)

    def _get_field(self, name: str) -> str:
        entry = self._entries[name]
        if isinstance(entry, ctk.CTkTextbox):
            return entry.get("1.0", "end").strip()
        return entry.get().strip()

    def _save(self):
        last_name = self._get_field("last_name")
        first_name = self._get_field("first_name")
        plot_number = self._get_field("plot_number")
        plot_area_str = self._get_field("plot_area")

        if not last_name or not first_name or not plot_number or not plot_area_str:
            messagebox.showwarning("Внимание", "Заполните обязательные поля (*)")
            return

        try:
            plot_area = Decimal(plot_area_str)
            if plot_area <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messagebox.showwarning("Внимание", "Площадь должна быть положительным числом")
            return

        email = self._get_field("email")
        if email and not re.match(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$", email):
            messagebox.showwarning("Внимание", "Некорректный email")
            return

        phone = self._get_field("phone")
        if phone:
            digits = re.sub(r"[^\d]", "", phone)
            if not (7 <= len(digits) <= 15):
                messagebox.showwarning("Внимание", "Телефон должен содержать от 7 до 15 цифр")
                return

        try:
            with db_session() as session:
                if self.member_id:
                    member = session.get(Member, self.member_id)
                    if not member:
                        messagebox.showerror("Ошибка", "Участник не найден")
                        return
                    action = AuditAction.UPDATE.value
                else:
                    member = Member()
                    session.add(member)
                    action = AuditAction.CREATE.value

                member.last_name = last_name
                member.first_name = first_name
                member.patronymic = self._get_field("patronymic") or None
                member.plot_number = plot_number
                member.plot_area = plot_area
                member.phone = self._get_field("phone") or None
                member.email = self._get_field("email") or None
                member.address = self._get_field("address") or None
                member.notes = self._get_field("notes") or None

                session.flush()
                log_action(action, "member", member.id,
                           f"{member.full_name}, уч. {member.plot_number}")
            self._on_ok()

        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
