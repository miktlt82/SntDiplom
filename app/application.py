"""Main application window with CTkTabview."""

from __future__ import annotations
import customtkinter as ctk

from app.config import APP_TITLE, WINDOW_SIZE, MIN_WINDOW_SIZE
from app.database.engine import init_db
from app.config import DEFAULT_DB_PATH
from app.event_bus import event_bus


class Application(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW_SIZE)

        init_db(DEFAULT_DB_PATH)

        self._build_ui()
        self._subscribe_events()

    def _build_ui(self):
        # Toolbar (will be replaced by full Toolbar widget in main.py)
        self.toolbar_frame = ctk.CTkFrame(self, height=40)
        self.toolbar_frame.pack(fill="x", padx=5, pady=(5, 0))

        # Tabview
        self.tabview = ctk.CTkTabview(self, anchor="nw")
        self.tabview.pack(fill="both", expand=True, padx=5, pady=5)

        # Status bar frame
        self.status_frame = ctk.CTkFrame(self, height=25)
        self.status_frame.pack(fill="x", padx=5, pady=(0, 5))

        self._tabs = {}

    def _subscribe_events(self):
        event_bus.subscribe("database_changed", self._on_db_changed)

    def _on_db_changed(self, **kwargs):
        pass  # Handled by individual tabs and status bar

    def set_status(self, message: str):
        event_bus.publish("status_message", message=message)

    def add_tab(self, name: str, tab_instance=None):
        """Add a tab to the tabview and optionally associate a tab instance."""
        tab_frame = self.tabview.add(name)
        if tab_instance is not None:
            self._tabs[name] = tab_instance
            tab_instance.build(tab_frame)
        return tab_frame

    def remove_tab(self, name: str):
        """Remove a tab and clean up its event subscriptions."""
        tab_instance = self._tabs.pop(name, None)
        if tab_instance is not None and hasattr(tab_instance, "destroy"):
            tab_instance.destroy()
        self.tabview.delete(name)

    def destroy(self):
        """Clean up all tabs before destroying the window."""
        for tab_instance in self._tabs.values():
            if hasattr(tab_instance, "destroy"):
                tab_instance.destroy()
        self._tabs.clear()
        super().destroy()

    def get_tab_frame(self, name: str):
        return self.tabview.tab(name)
