"""Notes tab with rich text editing."""

from __future__ import annotations
from tkinter import messagebox
import customtkinter as ctk

from app.gui.tabs.base_tab import BaseTab
from app.logger import get_logger

logger = get_logger(__name__)
from app.gui.widgets.rich_text_editor import RichTextEditor
from app.database.engine import db_session
from app.database.models.note import Note
from app.services.audit_service import log_action
from app.constants import AuditAction


class NotesTab(BaseTab):

    def _build_ui(self):
        # Left panel: notes list
        paned = ctk.CTkFrame(self.frame)
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        left = ctk.CTkFrame(paned, width=250)
        left.pack(side="left", fill="y", padx=(0, 5))
        left.pack_propagate(False)

        btn_frame = ctk.CTkFrame(left)
        btn_frame.pack(fill="x", pady=5)
        ctk.CTkButton(btn_frame, text="+ Новая", width=80,
                       command=self._new_note).pack(side="left", padx=2)
        ctk.CTkButton(btn_frame, text="Удалить", width=80, fg_color="gray",
                       command=self._delete_note).pack(side="left", padx=2)
        ctk.CTkButton(btn_frame, text="Закрепить", width=80,
                       command=self._toggle_pin).pack(side="left", padx=2)

        self._note_ids: list[int] = []
        self._selected_note_id: int | None = None

        self.notes_list_frame = ctk.CTkScrollableFrame(left)
        self.notes_list_frame.pack(fill="both", expand=True)

        # Right panel: editor
        right = ctk.CTkFrame(paned)
        right.pack(side="left", fill="both", expand=True)

        title_frame = ctk.CTkFrame(right)
        title_frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(title_frame, text="Заголовок:").pack(side="left", padx=5)
        self.title_entry = ctk.CTkEntry(title_frame)
        self.title_entry.pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(title_frame, text="Сохранить", width=100,
                       command=self._save_note).pack(side="right", padx=5)

        self.editor = RichTextEditor(right)
        self.editor.pack(fill="both", expand=True, padx=5, pady=5)

    def refresh_data(self):
        self._load_notes_list()

    def _load_notes_list(self):
        # Clear existing buttons
        for widget in self.notes_list_frame.winfo_children():
            widget.destroy()

        with db_session(readonly=True) as session:
            notes = session.query(Note).order_by(
                Note.is_pinned.desc(), Note.updated_at.desc()
            ).all()
            self._note_ids = [n.id for n in notes]

            for note in notes:
                pin = "📌 " if note.is_pinned else ""
                btn = ctk.CTkButton(
                    self.notes_list_frame,
                    text=f"{pin}{note.title}",
                    anchor="w",
                    fg_color="transparent",
                    text_color=("gray10", "gray90"),
                    hover_color=("gray80", "gray30"),
                    command=lambda nid=note.id: self._select_note(nid),
                )
                btn.pack(fill="x", pady=1)

    def _select_note(self, note_id: int):
        self._selected_note_id = note_id
        with db_session(readonly=True) as session:
            note = session.get(Note, note_id)
            if note:
                self.title_entry.delete(0, "end")
                self.title_entry.insert(0, note.title)
                self.editor.set_content(note.content or "")

    def _new_note(self):
        try:
            with db_session() as session:
                note = Note(title="Новая заметка", content="", content_format="plain")
                session.add(note)
                session.flush()
                self._selected_note_id = note.id
                note_id = note.id
            log_action(AuditAction.CREATE.value, "note", note_id, "Новая заметка")
            self.refresh_data()
            self._select_note(note_id)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _save_note(self):
        if not self._selected_note_id:
            messagebox.showwarning("Внимание", "Выберите заметку")
            return

        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("Внимание", "Введите заголовок")
            return

        content = self.editor.get_content()

        try:
            with db_session() as session:
                note = session.get(Note, self._selected_note_id)
                if note:
                    note.title = title
                    note.content = content
            self.set_status("Заметка сохранена")
            self._load_notes_list()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _delete_note(self):
        if not self._selected_note_id:
            return
        if not messagebox.askyesno("Удаление", "Удалить заметку?"):
            return

        try:
            with db_session() as session:
                note = session.get(Note, self._selected_note_id)
                if note:
                    session.delete(note)
            log_action(AuditAction.DELETE.value, "note", self._selected_note_id)
            self._selected_note_id = None
            self.title_entry.delete(0, "end")
            self.editor.set_content("")
            self.refresh_data()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _toggle_pin(self):
        if not self._selected_note_id:
            return
        try:
            with db_session() as session:
                note = session.get(Note, self._selected_note_id)
                if note:
                    note.is_pinned = not note.is_pinned
            self._load_notes_list()
        except Exception:
            logger.error("Failed to toggle pin for note %s", self._selected_note_id, exc_info=True)
