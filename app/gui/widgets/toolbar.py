"""Toolbar with theme and database selection."""

from __future__ import annotations
from tkinter import messagebox, simpledialog
import customtkinter as ctk

from app.config import DATA_DIR
from app.database.engine import switch_database, get_current_db_path
from app.services.backup_service import list_databases
from app.event_bus import event_bus


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

        self._refresh_db_list()
        event_bus.subscribe("database_changed", lambda **kw: self._refresh_db_list())

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
