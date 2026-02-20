"""Matplotlib chart wrapper for embedding in CTk."""

from __future__ import annotations
from typing import Any
import customtkinter as ctk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class ChartFrame(ctk.CTkFrame):
    """Frame that embeds a matplotlib figure."""

    def __init__(self, parent, figsize=(5, 3.5), **kwargs):
        super().__init__(parent, **kwargs)
        self.figure = Figure(figsize=figsize, dpi=100)
        self.figure.patch.set_facecolor("none")
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def clear(self):
        self.figure.clear()

    def draw(self):
        self.figure.tight_layout()
        self.canvas.draw()

    def pie_chart(self, labels: list[str], values: list[float],
                  title: str = "", colors: list[str] | None = None):
        self.clear()
        ax = self.figure.add_subplot(111)
        if sum(values) == 0:
            ax.text(0.5, 0.5, "Нет данных", ha="center", va="center", fontsize=14)
        else:
            ax.pie(values, labels=labels, colors=colors, autopct="%1.1f%%", startangle=90)
        ax.set_title(title)
        self.draw()

    def bar_chart(self, labels: list[str], values: list[float],
                  title: str = "", color: str = "#3a7ebf", ylabel: str = ""):
        self.clear()
        ax = self.figure.add_subplot(111)
        if values:
            bars = ax.bar(range(len(values)), values, color=color, tick_label=labels)
            ax.set_ylabel(ylabel)
        else:
            ax.text(0.5, 0.5, "Нет данных", ha="center", va="center", fontsize=14)
        ax.set_title(title)
        self.draw()
