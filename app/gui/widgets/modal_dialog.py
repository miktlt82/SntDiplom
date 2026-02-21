"""Base modal dialog using CTkToplevel."""

from __future__ import annotations
import customtkinter as ctk


class ModalDialog(ctk.CTkToplevel):
    """Base modal dialog window."""

    def __init__(self, parent, title: str = "Диалог", width: int = 500, height: int = 400):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.minsize(width, height)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.result = None

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        self.geometry(f"+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _on_ok(self):
        self.result = True
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()

    def wait_for_result(self):
        self.wait_window()
        return self.result
