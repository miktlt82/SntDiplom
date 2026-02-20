"""Tab manager for adding/removing/renaming custom tabs."""

from __future__ import annotations
from tkinter import messagebox, simpledialog
import customtkinter as ctk

from app.database.engine import db_session
from app.database.models.custom_tab import CustomTab
from app.gui.tabs.custom_tab import CustomTabView
from app.services.audit_service import log_action
from app.constants import AuditAction


class TabManager:
    """Manages creation and loading of custom tabs."""

    def __init__(self, app):
        self.app = app
        self._custom_tabs: dict[int, CustomTabView] = {}

    def load_custom_tabs(self):
        """Load all custom tabs from DB and add to app."""
        with db_session(readonly=True) as session:
            tabs = session.query(CustomTab).filter(
                CustomTab.is_visible == True
            ).order_by(CustomTab.sort_order).all()
            for tab in tabs:
                if tab.id not in self._custom_tabs:
                    self._add_custom_tab_to_app(tab.id, tab.name)

    def create_custom_tab(self):
        """Prompt user to create a new custom tab."""
        name = simpledialog.askstring("Новая вкладка", "Название вкладки:",
                                       parent=self.app)
        if not name or not name.strip():
            return

        try:
            with db_session() as session:
                max_order = session.query(CustomTab).count()
                tab = CustomTab(name=name.strip(), sort_order=max_order)
                session.add(tab)
                session.flush()
                tab_id = tab.id
                tab_name = tab.name
            log_action(AuditAction.CREATE.value, "custom_tab", tab_id, name)
            self._add_custom_tab_to_app(tab_id, tab_name)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _add_custom_tab_to_app(self, tab_id: int, name: str):
        view = CustomTabView(self.app, tab_db_id=tab_id)
        self.app.add_tab(name, view)
        self._custom_tabs[tab_id] = view

    def reload_all(self):
        """Called after database switch — custom tabs must be reloaded."""
        for tab_view in self._custom_tabs.values():
            tab_view.refresh_data()
