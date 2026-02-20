"""Rich text editor with basic formatting."""

from __future__ import annotations
import tkinter as tk
import customtkinter as ctk


class RichTextEditor(ctk.CTkFrame):
    """Text editor with bold/italic/underline formatting."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        # Toolbar
        toolbar = ctk.CTkFrame(self)
        toolbar.pack(fill="x", pady=(0, 2))

        ctk.CTkButton(toolbar, text="B", width=30, font=ctk.CTkFont(weight="bold"),
                       command=self._toggle_bold).pack(side="left", padx=1)
        ctk.CTkButton(toolbar, text="I", width=30, font=ctk.CTkFont(slant="italic"),
                       command=self._toggle_italic).pack(side="left", padx=1)
        ctk.CTkButton(toolbar, text="U", width=30,
                       command=self._toggle_underline).pack(side="left", padx=1)

        # Text widget (using tk.Text for tag support)
        self.text = tk.Text(self, wrap="word", font=("Segoe UI", 11))
        scrollbar = tk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)

        self.text.tag_configure("bold", font=("Segoe UI", 11, "bold"))
        self.text.tag_configure("italic", font=("Segoe UI", 11, "italic"))
        self.text.tag_configure("underline", underline=True)

    def _toggle_tag(self, tag_name: str):
        try:
            sel_start = self.text.index("sel.first")
            sel_end = self.text.index("sel.last")
        except tk.TclError:
            return

        current_tags = self.text.tag_names(sel_start)
        if tag_name in current_tags:
            self.text.tag_remove(tag_name, sel_start, sel_end)
        else:
            self.text.tag_add(tag_name, sel_start, sel_end)

    def _toggle_bold(self):
        self._toggle_tag("bold")

    def _toggle_italic(self):
        self._toggle_tag("italic")

    def _toggle_underline(self):
        self._toggle_tag("underline")

    def get_content(self) -> str:
        return self.text.get("1.0", "end").strip()

    def set_content(self, content: str):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
