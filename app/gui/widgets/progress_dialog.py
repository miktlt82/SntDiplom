"""Progress dialog for running long operations in a background thread."""

from __future__ import annotations
import threading
from typing import Callable, Any
import customtkinter as ctk

from app.logger import get_logger

logger = get_logger(__name__)


class ProgressDialog(ctk.CTkToplevel):
    """Modal dialog with indeterminate progress bar.

    Runs `target` function in a background thread and closes when done.
    On success calls `on_success(result)`, on error calls `on_error(exception)`.
    """

    def __init__(
        self,
        parent,
        title: str,
        target: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ):
        super().__init__(parent)
        self.title(title)
        self.geometry("350x120")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._target = target
        self._on_success = on_success
        self._on_error = on_error
        self._result = None
        self._error: Exception | None = None
        self._finished = False

        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=13)).pack(
            padx=20, pady=(15, 5)
        )
        self._progress = ctk.CTkProgressBar(self, mode="indeterminate", width=300)
        self._progress.pack(padx=20, pady=10)
        self._progress.start()

        self._status_label = ctk.CTkLabel(self, text="Выполняется...")
        self._status_label.pack(pady=(0, 10))

        self.protocol("WM_DELETE_WINDOW", lambda: None)  # prevent close

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._poll()

    def _run(self):
        try:
            self._result = self._target()
        except Exception as e:
            self._error = e
            logger.error("Background task failed", exc_info=True)

    def _poll(self):
        if self._thread.is_alive():
            self.after(100, self._poll)
        else:
            self._finish()

    def _finish(self):
        if self._finished:
            return
        self._finished = True
        self._progress.stop()
        self.grab_release()
        self.destroy()

        if self._error:
            if self._on_error:
                self._on_error(self._error)
        else:
            if self._on_success:
                self._on_success(self._result)
