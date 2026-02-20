"""Simple date picker widget."""

from __future__ import annotations
from datetime import date, datetime
import customtkinter as ctk


class DatePicker(ctk.CTkFrame):
    """Date entry with day/month/year fields."""

    def __init__(self, parent, initial_date: date | None = None, **kwargs):
        super().__init__(parent, **kwargs)

        if initial_date is None:
            initial_date = date.today()

        self.day_var = ctk.StringVar(value=str(initial_date.day).zfill(2))
        self.month_var = ctk.StringVar(value=str(initial_date.month).zfill(2))
        self.year_var = ctk.StringVar(value=str(initial_date.year))

        self.day_entry = ctk.CTkEntry(self, textvariable=self.day_var, width=40, justify="center")
        self.day_entry.pack(side="left")
        ctk.CTkLabel(self, text=".").pack(side="left")

        self.month_entry = ctk.CTkEntry(self, textvariable=self.month_var, width=40, justify="center")
        self.month_entry.pack(side="left")
        ctk.CTkLabel(self, text=".").pack(side="left")

        self.year_entry = ctk.CTkEntry(self, textvariable=self.year_var, width=60, justify="center")
        self.year_entry.pack(side="left")

    def get_date(self) -> date | None:
        try:
            d = int(self.day_var.get())
            m = int(self.month_var.get())
            y = int(self.year_var.get())
            return date(y, m, d)
        except (ValueError, TypeError):
            return None

    def set_date(self, d: date):
        self.day_var.set(str(d.day).zfill(2))
        self.month_var.set(str(d.month).zfill(2))
        self.year_var.set(str(d.year))
