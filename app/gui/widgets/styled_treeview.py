"""Treeview with theme support, sorting, and row colors."""

from __future__ import annotations
import tkinter as tk
import tkinter.ttk as ttk
from typing import Any, Callable

from app.gui.theme import apply_treeview_theme, get_theme_colors
from app.event_bus import event_bus


class StyledTreeview(ttk.Treeview):
    """Treeview with sorting, theming, and color tags."""

    def __init__(
        self,
        parent,
        columns: list[dict],
        style_name: str = "Custom.Treeview",
        on_select: Callable | None = None,
        on_double_click: Callable | None = None,
        **kwargs,
    ):
        self._column_defs = columns
        col_ids = [c["id"] for c in columns]

        super().__init__(
            parent,
            columns=col_ids,
            show="headings",
            style=style_name,
            selectmode="browse",
            **kwargs,
        )

        self._style_name = style_name
        self._sort_col = None
        self._sort_reverse = False
        self._on_select = on_select

        # Scrollbars
        self._v_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.yview)
        self.configure(yscrollcommand=self._v_scroll.set)

        for col_def in columns:
            cid = col_def["id"]
            self.heading(
                cid,
                text=col_def.get("text", cid),
                command=lambda c=cid: self._sort_by(c),
            )
            self.column(
                cid,
                width=col_def.get("width", 100),
                minwidth=col_def.get("minwidth", 50),
                anchor=col_def.get("anchor", "w"),
                stretch=col_def.get("stretch", True),
            )

        apply_treeview_theme(self, style_name)
        event_bus.subscribe("theme_changed", self._on_theme_changed)

        if on_select:
            self.bind("<<TreeviewSelect>>", lambda e: on_select(self.get_selected_iid()))
        if on_double_click:
            self.bind("<Double-1>", lambda e: on_double_click(self.get_selected_iid()))

    def pack_with_scrollbar(self, **kwargs):
        frame = self.master
        self._v_scroll.pack(side="right", fill="y")
        self.pack(side="left", fill="both", expand=True, **kwargs)

    def grid_with_scrollbar(self, row=0, column=0, **kwargs):
        self.grid(row=row, column=column, sticky="nsew", **kwargs)
        self._v_scroll.grid(row=row, column=column + 1, sticky="ns")

    def get_selected_iid(self) -> str | None:
        sel = self.selection()
        return sel[0] if sel else None

    def get_selected_values(self) -> tuple | None:
        iid = self.get_selected_iid()
        if iid is None:
            return None
        return self.item(iid, "values")

    def load_data(self, rows: list[dict[str, Any]], id_key: str = "id", tag_key: str | None = "tag"):
        """Load data into the treeview. Each row is a dict with column ids as keys."""
        self.delete(*self.get_children())
        col_ids = [c["id"] for c in self._column_defs]

        for i, row in enumerate(rows):
            values = [row.get(cid, "") for cid in col_ids]
            tags = []
            if tag_key and tag_key in row:
                tags.append(row[tag_key])
            else:
                tags.append("even" if i % 2 == 0 else "odd")
            iid = str(row.get(id_key, i))
            self.insert("", "end", iid=iid, values=values, tags=tags)

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col
            self._sort_reverse = False

        items = [(self.set(k, col), k) for k in self.get_children("")]

        def sort_key(t):
            try:
                return (0, float(t[0]))
            except (ValueError, TypeError):
                return (1, str(t[0]).lower())

        try:
            items.sort(key=sort_key, reverse=self._sort_reverse)
        except Exception:
            pass

        for index, (_, iid) in enumerate(items):
            self.move(iid, "", index)

        # Update heading indicator
        for c in self._column_defs:
            text = c.get("text", c["id"])
            if c["id"] == col:
                arrow = " ▼" if self._sort_reverse else " ▲"
                text += arrow
            self.heading(c["id"], text=text)

    def destroy(self):
        event_bus.unsubscribe("theme_changed", self._on_theme_changed)
        super().destroy()

    def _on_theme_changed(self, **kwargs):
        apply_treeview_theme(self, self._style_name)
