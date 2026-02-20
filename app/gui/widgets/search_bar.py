"""Search bar with filter options."""

from __future__ import annotations
from typing import Callable
import customtkinter as ctk


class SearchBar(ctk.CTkFrame):
    """Search entry with optional filter dropdown."""

    def __init__(
        self,
        parent,
        on_search: Callable[[str, str], None],
        filter_options: list[str] | None = None,
        placeholder: str = "Поиск...",
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._on_search = on_search

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._trigger_search())

        self.search_entry = ctk.CTkEntry(
            self, textvariable=self.search_var, placeholder_text=placeholder, width=300
        )
        self.search_entry.pack(side="left", padx=(0, 5), fill="x", expand=True)

        self.filter_var = ctk.StringVar(value="Все")
        if filter_options:
            self.filter_menu = ctk.CTkOptionMenu(
                self,
                values=["Все"] + filter_options,
                variable=self.filter_var,
                command=lambda _: self._trigger_search(),
                width=150,
            )
            self.filter_menu.pack(side="left", padx=5)

        self.clear_btn = ctk.CTkButton(
            self, text="✕", width=30, command=self._clear
        )
        self.clear_btn.pack(side="left", padx=5)

    def _trigger_search(self):
        self._on_search(self.search_var.get(), self.filter_var.get())

    def _clear(self):
        self.search_var.set("")
        self.filter_var.set("Все")
        self._trigger_search()

    def get_query(self) -> str:
        return self.search_var.get()

    def get_filter(self) -> str:
        return self.filter_var.get()
