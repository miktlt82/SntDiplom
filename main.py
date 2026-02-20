"""Entry point for the SNT accounting application."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.application import Application
from app.gui.widgets.toolbar import Toolbar
from app.gui.widgets.status_bar import StatusBar
from app.gui.tabs.members_tab import MembersTab
from app.gui.tabs.membership_fee_tab import MembershipFeeTab
from app.gui.tabs.target_fee_tab import TargetFeeTab
from app.gui.tabs.electricity_tab import ElectricityTab
from app.gui.tabs.notes_tab import NotesTab
from app.gui.tabs.analytics_tab import AnalyticsTab
from app.gui.tabs.tab_manager import TabManager
from app.services.backup_service import create_backup
from app.logger import get_logger

logger = get_logger(__name__)


def main():
    app = Application()

    # Replace default toolbar with full Toolbar widget
    for child in app.toolbar_frame.winfo_children():
        child.destroy()
    toolbar = Toolbar(app.toolbar_frame, app)
    toolbar.pack(fill="both", expand=True)

    # Status bar
    status_bar = StatusBar(app.status_frame)
    status_bar.pack(fill="both", expand=True)

    # Add tabs
    app.add_tab("Участники", MembersTab(app))
    app.add_tab("Членские взносы", MembershipFeeTab(app))
    app.add_tab("Целевые взносы", TargetFeeTab(app))
    app.add_tab("Электроэнергия", ElectricityTab(app))
    app.add_tab("Заметки", NotesTab(app))
    app.add_tab("Аналитика", AnalyticsTab(app))

    # Load custom tabs from DB
    tab_manager = TabManager(app)
    tab_manager.load_custom_tabs()

    # Add "+" tab for creating custom tabs
    plus_frame = app.tabview.add("+")
    import customtkinter as ctk
    ctk.CTkButton(
        plus_frame, text="Создать пользовательскую вкладку",
        command=tab_manager.create_custom_tab,
    ).pack(padx=20, pady=20)

    # Auto-backup on startup
    try:
        backup_path = create_backup()
        if backup_path:
            app.set_status(f"Авто-бэкап: {backup_path.name}")
    except Exception:
        logger.error("Auto-backup failed", exc_info=True)

    app.mainloop()


if __name__ == "__main__":
    main()
