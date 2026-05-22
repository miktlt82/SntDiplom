"""Tab manager for adding/removing/renaming custom tabs."""

from __future__ import annotations
from tkinter import messagebox, simpledialog
import customtkinter as ctk

from app.database.engine import db_session
from app.database.models.custom_tab import CustomTab
from app.gui.tabs.custom_tab import CustomTabView
from app.services.audit_service import log_action
from app.constants import AuditAction
from app.event_bus import event_bus
from app.logger import get_logger


logger = get_logger(__name__)


class TabManager:
    """Manages creation and loading of custom tabs."""

    def __init__(self, app):
        self.app = app
        self._custom_tabs: dict[int, CustomTabView] = {}
        self._custom_tab_names: dict[int, str] = {}
        event_bus.subscribe("database_changed", lambda **kw: self.reload_all())

    def load_custom_tabs(self):
        """Load all custom tabs from DB and add to app."""
        with db_session(readonly=True) as session:
            tabs = session.query(CustomTab).filter(
                CustomTab.is_visible.is_(True)
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
        display_name = self._unique_tab_name(name)
        view = CustomTabView(self.app, tab_db_id=tab_id)
        self.app.add_tab(display_name, view)
        self._custom_tabs[tab_id] = view
        self._custom_tab_names[tab_id] = display_name

    def reload_all(self):
        """Called after database switch — custom tabs must be reloaded."""
        self._remove_loaded_tabs()
        self.load_custom_tabs()

    def _remove_loaded_tabs(self):
        for tab_id, name in list(self._custom_tab_names.items()):
            try:
                self.app.remove_tab(name)
            except Exception:
                logger.warning("Failed to remove custom tab '%s'", name, exc_info=True)
            finally:
                self._custom_tabs.pop(tab_id, None)
                self._custom_tab_names.pop(tab_id, None)

    def _unique_tab_name(self, name: str) -> str:
        if not self._tab_name_exists(name):
            return name
        index = 2
        while self._tab_name_exists(f"{name} ({index})"):
            index += 1
        return f"{name} ({index})"

    def _tab_name_exists(self, name: str) -> bool:
        try:
            self.app.get_tab_frame(name)
            return True
        except Exception:
            return False
