"""Theme management for ttk.Treeview and other widgets."""

from __future__ import annotations
import tkinter.ttk as ttk
import customtkinter as ctk


DARK_COLORS = {
    "tree_bg": "#2b2b2b",
    "tree_fg": "#dcdcdc",
    "tree_selected_bg": "#3a7ebf",
    "tree_selected_fg": "#ffffff",
    "tree_heading_bg": "#3c3c3c",
    "tree_heading_fg": "#dcdcdc",
    "tree_field_bg": "#2b2b2b",
    "row_paid": "#2d4a2d",
    "row_partial": "#4a4a2d",
    "row_not_paid": "#4a2d2d",
    "row_archived": "#3c3c3c",
}

LIGHT_COLORS = {
    "tree_bg": "#ffffff",
    "tree_fg": "#1a1a1a",
    "tree_selected_bg": "#0078d7",
    "tree_selected_fg": "#ffffff",
    "tree_heading_bg": "#e8e8e8",
    "tree_heading_fg": "#1a1a1a",
    "tree_field_bg": "#ffffff",
    "row_paid": "#d4edda",
    "row_partial": "#fff3cd",
    "row_not_paid": "#f8d7da",
    "row_archived": "#e2e3e5",
}


def get_theme_colors() -> dict[str, str]:
    mode = ctk.get_appearance_mode()
    return DARK_COLORS if mode == "Dark" else LIGHT_COLORS


def apply_treeview_theme(tree: ttk.Treeview, style_name: str = "Custom.Treeview") -> None:
    """Apply current theme colors to a treeview widget."""
    colors = get_theme_colors()
    style = ttk.Style()

    style.configure(
        style_name,
        background=colors["tree_bg"],
        foreground=colors["tree_fg"],
        fieldbackground=colors["tree_field_bg"],
        rowheight=28,
        font=("Segoe UI", 10),
    )
    style.configure(
        f"{style_name}.Heading",
        background=colors["tree_heading_bg"],
        foreground=colors["tree_heading_fg"],
        font=("Segoe UI", 10, "bold"),
    )
    style.map(
        style_name,
        background=[("selected", colors["tree_selected_bg"])],
        foreground=[("selected", colors["tree_selected_fg"])],
    )

    tree.tag_configure("paid", background=colors["row_paid"])
    tree.tag_configure("partial", background=colors["row_partial"])
    tree.tag_configure("not_paid", background=colors["row_not_paid"])
    tree.tag_configure("archived", background=colors["row_archived"])
    tree.tag_configure("even", background=colors["tree_bg"])
    tree.tag_configure("odd", background=colors.get("tree_field_bg", colors["tree_bg"]))
