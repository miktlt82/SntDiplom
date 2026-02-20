"""Status bar widget."""

from __future__ import annotations
import customtkinter as ctk

from app.event_bus import event_bus
from app.database.engine import get_current_db_path


class StatusBar(ctk.CTkFrame):
    """Status bar at the bottom of the application."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, height=25, **kwargs)

        self.message_label = ctk.CTkLabel(
            self, text="Готово", anchor="w", font=ctk.CTkFont(size=11)
        )
        self.message_label.pack(side="left", padx=10)

        self.db_label = ctk.CTkLabel(
            self, text="", anchor="e", font=ctk.CTkFont(size=11)
        )
        self.db_label.pack(side="right", padx=10)

        self._update_db_info()
        event_bus.subscribe("status_message", self._on_status_message)
        event_bus.subscribe("database_changed", lambda **kw: self._update_db_info())

    def _on_status_message(self, message: str = "", **kwargs):
        self.message_label.configure(text=message)

    def _update_db_info(self):
        path = get_current_db_path()
        name = path.name if path else "—"
        self.db_label.configure(text=f"БД: {name}")
