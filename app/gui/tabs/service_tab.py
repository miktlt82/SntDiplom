"""Service tab for import, export, backup, and database file operations."""

from __future__ import annotations
from pathlib import Path
import shutil
from tkinter import filedialog, messagebox, simpledialog
import customtkinter as ctk

from app.config import DATA_DIR
from app.database.engine import dispose_engine, get_current_db_path, switch_database
from app.event_bus import event_bus
from app.gui.tabs.base_tab import BaseTab
from app.gui.widgets.progress_dialog import ProgressDialog
from app.services.backup_service import (
    create_backup, list_backups, restore_backup
)
from app.services.export_service import (
    export_debtors_pdf, export_members_excel, export_members_pdf
)
from app.services.import_service import import_members_csv, import_members_excel


class ServiceTab(BaseTab):
    """Administrative data operations grouped away from the main toolbar."""

    def _build_ui(self):
        container = ctk.CTkScrollableFrame(self.frame)
        container.pack(fill="both", expand=True, padx=5, pady=5)

        self._build_backup_section(container)
        self._build_members_section(container)
        self._build_database_section(container)

    def _build_backup_section(self, parent):
        section = ctk.CTkFrame(parent)
        section.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(
            section, text="Резервные копии",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 5))

        buttons = ctk.CTkFrame(section)
        buttons.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(
            buttons, text="Создать бэкап", width=140,
            command=self._do_backup,
        ).pack(side="left", padx=(0, 5))
        ctk.CTkButton(
            buttons, text="Восстановить", width=140,
            command=self._do_restore,
        ).pack(side="left", padx=5)

        self.backups_text = ctk.CTkTextbox(section, height=110, state="disabled")
        self.backups_text.pack(fill="x", padx=10, pady=(5, 10))

    def _build_members_section(self, parent):
        section = ctk.CTkFrame(parent)
        section.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(
            section, text="Участники и отчёты",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 5))

        buttons = ctk.CTkFrame(section)
        buttons.pack(fill="x", padx=10, pady=(5, 10))
        ctk.CTkButton(
            buttons, text="Импорт участников", width=150,
            command=self._do_import_members,
        ).pack(side="left", padx=(0, 5))
        ctk.CTkButton(
            buttons, text="Участники Excel", width=140,
            command=self._export_members_excel,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            buttons, text="Участники PDF", width=130,
            command=self._export_members_pdf,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            buttons, text="Должники PDF", width=120,
            command=self._export_debtors_pdf,
        ).pack(side="left", padx=5)

    def _build_database_section(self, parent):
        section = ctk.CTkFrame(parent)
        section.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(
            section, text="Файл базы данных",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 5))

        buttons = ctk.CTkFrame(section)
        buttons.pack(fill="x", padx=10, pady=(5, 10))
        ctk.CTkButton(
            buttons, text="Экспорт БД", width=130,
            command=self._export_db,
        ).pack(side="left", padx=(0, 5))
        ctk.CTkButton(
            buttons, text="Импорт БД", width=130,
            command=self._import_db,
        ).pack(side="left", padx=5)

    def refresh_data(self):
        self._load_backups()

    def _load_backups(self):
        backups = list_backups()
        self.backups_text.configure(state="normal")
        self.backups_text.delete("1.0", "end")
        if backups:
            for backup in backups:
                size_kb = backup["size"] // 1024
                self.backups_text.insert(
                    "end",
                    f"{backup['name']}  |  {backup['modified']}  |  {size_kb} KB\n",
                )
        else:
            self.backups_text.insert("end", "Нет резервных копий")
        self.backups_text.configure(state="disabled")

    def _do_backup(self):
        def _on_success(path):
            if path:
                self._load_backups()
                self.set_status(f"Бэкап создан: {path.name}")
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

        names = [
            f"{b['name']}  ({b['modified']},  {b['size'] // 1024} KB)"
            for b in backups
        ]
        choice = simpledialog.askstring(
            "Восстановление из бэкапа",
            "Выберите номер бэкапа:\n" + "\n".join(
                f"{i + 1}. {name}" for i, name in enumerate(names)
            ),
            parent=self.app,
        )
        if not choice:
            return
        try:
            index = int(choice.strip()) - 1
            if not (0 <= index < len(backups)):
                raise ValueError
        except ValueError:
            messagebox.showwarning("Внимание", "Некорректный выбор")
            return

        backup = backups[index]
        if not messagebox.askyesno(
            "Подтверждение",
            f"Восстановить из бэкапа?\n{backup['name']}\n\n"
            "Текущие данные будут перезаписаны!",
        ):
            return

        try:
            restore_backup(Path(backup["path"]))
            self._load_backups()
            self.set_status(f"Восстановлено из: {backup['name']}")
            messagebox.showinfo("Восстановление", f"БД восстановлена из: {backup['name']}")
        except Exception as e:
            messagebox.showerror("Ошибка восстановления", str(e))

    def _do_import_members(self):
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

        lower_path = path.lower()
        if lower_path.endswith(".csv"):
            target = lambda: import_members_csv(path)
        elif lower_path.endswith(".xlsx"):
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
            self.set_status("Импорт участников завершён")

        ProgressDialog(
            self.app, "Импорт участников...",
            target=target,
            on_success=_on_success,
            on_error=lambda e: messagebox.showerror("Ошибка импорта", str(e)),
        )

    def _export_members_excel(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="участники.xlsx",
        )
        if path:
            self._run_export(
                "Экспорт участников...",
                lambda: export_members_excel(path),
                path,
            )

    def _export_members_pdf(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile="участники.pdf",
        )
        if path:
            self._run_export(
                "Экспорт участников...",
                lambda: export_members_pdf(path),
                path,
            )

    def _export_debtors_pdf(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile="должники.pdf",
        )
        if path:
            self._run_export(
                "Экспорт должников...",
                lambda: export_debtors_pdf(path),
                path,
            )

    def _run_export(self, title: str, target, path: str):
        ProgressDialog(
            self.app,
            title,
            target=target,
            on_success=lambda _: messagebox.showinfo("Экспорт", f"Сохранено: {path}"),
            on_error=lambda e: messagebox.showerror("Ошибка экспорта", str(e)),
        )

    def _export_db(self):
        current = get_current_db_path()
        if not current or not current.exists():
            messagebox.showwarning("Внимание", "Нет активной базы данных")
            return
        path = filedialog.asksaveasfilename(
            title="Экспорт базы данных",
            defaultextension=".db",
            filetypes=[("SQLite DB", "*.db"), ("Все файлы", "*.*")],
            initialfile=current.name,
        )
        if not path:
            return
        try:
            dispose_engine()
            shutil.copy2(current, path)
            switch_database(current)
            messagebox.showinfo("Экспорт БД", f"База данных экспортирована:\n{path}")
        except Exception as e:
            switch_database(current)
            messagebox.showerror("Ошибка экспорта", str(e))

    def _import_db(self):
        path = filedialog.askopenfilename(
            title="Импорт базы данных",
            filetypes=[("SQLite DB", "*.db"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        src = Path(path)
        if not src.exists():
            messagebox.showerror("Ошибка", "Файл не найден")
            return
        dest = DATA_DIR / src.name
        current = get_current_db_path()
        if dest.exists():
            if not messagebox.askyesno(
                "Подтверждение",
                f"Файл {src.name} уже существует в каталоге данных.\nПерезаписать?",
            ):
                return
        try:
            try:
                same_file = src.resolve() == dest.resolve()
            except OSError:
                same_file = False

            if not same_file:
                dispose_engine()
                shutil.copy2(src, dest)
            switch_database(dest)
            messagebox.showinfo("Импорт БД", f"База данных импортирована: {src.name}")
        except Exception as e:
            if current:
                try:
                    switch_database(current)
                except Exception:
                    pass
            messagebox.showerror("Ошибка импорта", str(e))
