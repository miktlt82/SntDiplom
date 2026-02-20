"""Toolbar with theme, DB selection, backup controls."""

from __future__ import annotations
from tkinter import messagebox, filedialog, simpledialog
from pathlib import Path
import customtkinter as ctk

from app.config import DATA_DIR
from app.database.engine import switch_database, get_current_db_path
from app.services.backup_service import create_backup, list_databases, list_backups, restore_backup
from app.services.import_service import import_members_csv, import_members_excel
from app.services.export_service import (
    export_members_excel, export_members_pdf, export_debtors_pdf
)
from app.event_bus import event_bus
from app.gui.widgets.progress_dialog import ProgressDialog


class Toolbar(ctk.CTkFrame):
    """Application toolbar with common actions."""

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, height=40, **kwargs)
        self.app = app

        # Theme switch
        self.theme_label = ctk.CTkLabel(self, text="Тема:")
        self.theme_label.pack(side="left", padx=(10, 5))

        self.theme_switch = ctk.CTkSwitch(
            self, text="Тёмная", command=self._toggle_theme
        )
        self.theme_switch.pack(side="left", padx=5)
        if ctk.get_appearance_mode() == "Dark":
            self.theme_switch.select()

        # Separator
        ctk.CTkLabel(self, text="|").pack(side="left", padx=10)

        # DB selector
        ctk.CTkLabel(self, text="БД:").pack(side="left", padx=5)
        self.db_var = ctk.StringVar()
        self.db_menu = ctk.CTkOptionMenu(
            self, variable=self.db_var, values=["—"],
            command=self._on_db_selected, width=200,
        )
        self.db_menu.pack(side="left", padx=5)

        ctk.CTkButton(self, text="Новая БД", width=80,
                       command=self._create_db).pack(side="left", padx=5)

        ctk.CTkLabel(self, text="|").pack(side="left", padx=10)

        # Backup / Restore
        ctk.CTkButton(self, text="Бэкап", width=80,
                       command=self._do_backup).pack(side="left", padx=5)
        ctk.CTkButton(self, text="Восстановить", width=110,
                       command=self._do_restore).pack(side="left", padx=5)

        # Import/Export
        ctk.CTkLabel(self, text="|").pack(side="left", padx=10)

        ctk.CTkButton(self, text="Импорт", width=80,
                       command=self._do_import).pack(side="left", padx=5)

        self.export_menu_btn = ctk.CTkButton(
            self, text="Экспорт", width=80, command=self._do_export
        )
        self.export_menu_btn.pack(side="left", padx=5)

        self._refresh_db_list()

    def _toggle_theme(self):
        if self.theme_switch.get():
            ctk.set_appearance_mode("dark")
        else:
            ctk.set_appearance_mode("light")
        event_bus.publish("theme_changed")

    def _refresh_db_list(self):
        dbs = list_databases()
        names = [d["name"] for d in dbs]
        if not names:
            names = ["—"]
        self.db_menu.configure(values=names)

        current = get_current_db_path()
        if current:
            self.db_var.set(current.name)

    def _on_db_selected(self, name: str):
        if name == "—":
            return
        db_path = DATA_DIR / name
        if not db_path.exists():
            messagebox.showerror("Ошибка", f"Файл не найден: {db_path}")
            return
        switch_database(db_path)
        event_bus.publish("status_message", message=f"БД переключена на: {name}")

    def _create_db(self):
        name = simpledialog.askstring("Новая БД", "Имя файла (без .db):", parent=self.app)
        if not name or not name.strip():
            return
        name = name.strip()
        if not name.endswith(".db"):
            name += ".db"
        db_path = DATA_DIR / name
        if db_path.exists():
            messagebox.showwarning("Внимание", "Файл уже существует")
            return
        switch_database(db_path)
        self._refresh_db_list()
        event_bus.publish("status_message", message=f"Создана БД: {name}")

    def _do_backup(self):
        def _on_success(path):
            if path:
                event_bus.publish("status_message", message=f"Бэкап создан: {path.name}")
                messagebox.showinfo("Бэкап", f"Создан: {path}")
            else:
                messagebox.showwarning("Бэкап", "Не удалось создать бэкап")

        ProgressDialog(
            self.app, "Создание бэкапа...",
            target=create_backup,
            on_success=_on_success,
            on_error=lambda e: messagebox.showerror("Ошибка бэкапа", str(e)),
        )

    def _do_restore(self):
        backups = list_backups()
        if not backups:
            messagebox.showinfo("Восстановление", "Нет доступных бэкапов")
            return

        names = [f"{b['name']}  ({b['modified']},  {b['size'] // 1024} KB)" for b in backups]
        choice = simpledialog.askstring(
            "Восстановление из бэкапа",
            "Выберите номер бэкапа:\n" + "\n".join(
                f"{i + 1}. {n}" for i, n in enumerate(names)
            ),
            parent=self.app,
        )
        if not choice:
            return
        try:
            idx = int(choice.strip()) - 1
            if not (0 <= idx < len(backups)):
                raise ValueError
        except ValueError:
            messagebox.showwarning("Внимание", "Некорректный выбор")
            return

        backup = backups[idx]
        if not messagebox.askyesno(
            "Подтверждение",
            f"Восстановить из бэкапа?\n{backup['name']}\n\n"
            "Текущие данные будут перезаписаны!"
        ):
            return

        try:
            restore_backup(Path(backup["path"]))
            event_bus.publish("status_message", message=f"Восстановлено из: {backup['name']}")
            messagebox.showinfo("Восстановление", f"БД восстановлена из: {backup['name']}")
        except Exception as e:
            messagebox.showerror("Ошибка восстановления", str(e))

    def _do_import(self):
        path = filedialog.askopenfilename(
            title="Импорт участников",
            filetypes=[
                ("CSV файлы", "*.csv"),
                ("Excel файлы", "*.xlsx"),
                ("Все файлы", "*.*"),
            ],
        )
        if not path:
            return

        if path.lower().endswith(".csv"):
            target = lambda: import_members_csv(path)
        elif path.lower().endswith(".xlsx"):
            target = lambda: import_members_excel(path)
        else:
            messagebox.showwarning("Внимание", "Неподдерживаемый формат")
            return

        def _on_success(result):
            msg = f"Создано: {result['created']}, Пропущено: {result['skipped']}"
            if result["errors"]:
                msg += f"\nОшибки ({len(result['errors'])}):\n" + "\n".join(result["errors"][:5])
            messagebox.showinfo("Импорт", msg)
            event_bus.publish("member_updated")

        ProgressDialog(
            self.app, "Импорт данных...",
            target=target,
            on_success=_on_success,
            on_error=lambda e: messagebox.showerror("Ошибка импорта", str(e)),
        )

    def _do_export(self):
        # Simple export menu via dialog
        choice = simpledialog.askstring(
            "Экспорт",
            "Что экспортировать?\n1 - Участники (Excel)\n2 - Участники (PDF)\n3 - Должники (PDF)",
            parent=self.app,
        )
        if not choice:
            return

        if choice.strip() == "1":
            path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel", "*.xlsx")],
                initialfile="participants.xlsx",
            )
            if path:
                ProgressDialog(
                    self.app, "Экспорт в Excel...",
                    target=lambda: export_members_excel(path),
                    on_success=lambda _: messagebox.showinfo("Экспорт", f"Сохранено: {path}"),
                    on_error=lambda e: messagebox.showerror("Ошибка экспорта", str(e)),
                )

        elif choice.strip() == "2":
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile="participants.pdf",
            )
            if path:
                ProgressDialog(
                    self.app, "Экспорт в PDF...",
                    target=lambda: export_members_pdf(path),
                    on_success=lambda _: messagebox.showinfo("Экспорт", f"Сохранено: {path}"),
                    on_error=lambda e: messagebox.showerror("Ошибка экспорта", str(e)),
                )

        elif choice.strip() == "3":
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile="debtors.pdf",
            )
            if path:
                ProgressDialog(
                    self.app, "Экспорт должников...",
                    target=lambda: export_debtors_pdf(path),
                    on_success=lambda _: messagebox.showinfo("Экспорт", f"Сохранено: {path}"),
                    on_error=lambda e: messagebox.showerror("Ошибка экспорта", str(e)),
                )
