"""Custom user-defined tab with EAV data."""

from __future__ import annotations
import json
from tkinter import messagebox
import customtkinter as ctk

from app.gui.tabs.base_tab import BaseTab
from app.gui.widgets.styled_treeview import StyledTreeview
from app.gui.widgets.modal_dialog import ModalDialog
from sqlalchemy.orm import joinedload
from app.database.engine import db_session
from app.database.models.custom_tab import CustomTab, CustomColumn, CustomRow, CustomCellValue
from app.constants import CustomColumnType
from app.logger import get_logger

logger = get_logger(__name__)


class CustomTabView(BaseTab):
    """Renders a custom tab backed by EAV data."""

    def __init__(self, app, tab_db_id: int):
        super().__init__(app)
        self.tab_db_id = tab_db_id

    def _build_ui(self):
        toolbar = ctk.CTkFrame(self.frame)
        toolbar.pack(fill="x", padx=5, pady=5)

        ctk.CTkButton(toolbar, text="+ Строка", width=100,
                       command=self._add_row).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Редактировать", width=120,
                       command=self._edit_row).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Удалить строку", width=120,
                       command=self._delete_row).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Столбцы", width=100,
                       command=self._manage_columns).pack(side="left", padx=5)

        self.table_frame = ctk.CTkFrame(self.frame)
        self.table_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.tree = None
        self._columns_cache: list[CustomColumn] = []

    def refresh_data(self):
        self._rebuild_tree()

    def _rebuild_tree(self):
        # Destroy old tree
        for w in self.table_frame.winfo_children():
            w.destroy()

        with db_session(readonly=True) as session:
            tab = session.get(CustomTab, self.tab_db_id)
            if not tab:
                return

            columns = session.query(CustomColumn).filter(
                CustomColumn.tab_id == self.tab_db_id
            ).order_by(CustomColumn.sort_order).all()
            self._columns_cache = [(c.id, c.name, c.column_type) for c in columns]

            if not columns:
                ctk.CTkLabel(self.table_frame, text="Добавьте столбцы").pack(pady=20)
                return

            col_defs = [{"id": f"col_{c.id}", "text": c.name, "width": 150} for c in columns]
            self.tree = StyledTreeview(
                self.table_frame, columns=col_defs,
                style_name=f"CT{self.tab_db_id}.Treeview",
            )
            self.tree.pack_with_scrollbar()

            # Load rows with eager-loaded values (avoid N+1)
            rows_db = session.query(CustomRow).options(
                joinedload(CustomRow.values)
            ).filter(
                CustomRow.tab_id == self.tab_db_id
            ).all()

            rows = []
            for row in rows_db:
                values = {cv.column_id: cv.value for cv in row.values}
                row_data = {"id": row.id}
                for col in columns:
                    row_data[f"col_{col.id}"] = values.get(col.id, "")
                rows.append(row_data)

            self.tree.load_data(rows)

    def _add_row(self):
        if not self._columns_cache:
            messagebox.showwarning("Внимание", "Сначала добавьте столбцы")
            return
        dialog = RowEditDialog(self.app, self.tab_db_id, self._columns_cache, row_id=None)
        if dialog.wait_for_result():
            self.refresh_data()

    def _edit_row(self):
        if not self.tree:
            return
        iid = self.tree.get_selected_iid()
        if not iid:
            messagebox.showwarning("Внимание", "Выберите строку")
            return
        dialog = RowEditDialog(self.app, self.tab_db_id, self._columns_cache, row_id=int(iid))
        if dialog.wait_for_result():
            self.refresh_data()

    def _delete_row(self):
        if not self.tree:
            return
        iid = self.tree.get_selected_iid()
        if not iid:
            messagebox.showwarning("Внимание", "Выберите строку")
            return
        if not messagebox.askyesno("Удаление", "Удалить строку?"):
            return

        try:
            with db_session() as session:
                row = session.get(CustomRow, int(iid))
                if row:
                    session.delete(row)
            self.refresh_data()
        except Exception as e:
            logger.error("Failed to delete row %s", iid, exc_info=True)
            messagebox.showerror("Ошибка", str(e))

    def _manage_columns(self):
        dialog = ColumnsDialog(self.app, self.tab_db_id)
        if dialog.wait_for_result():
            self.refresh_data()


class RowEditDialog(ModalDialog):
    def __init__(self, parent, tab_id: int,
                 columns: list[tuple[int, str, str]], row_id: int | None):
        self.tab_id = tab_id
        self.columns_info = columns
        self.row_id = row_id
        title = "Редактировать строку" if row_id else "Новая строка"
        height = max(200, 80 + len(columns) * 50)
        super().__init__(parent, title=title, width=450, height=min(height, 600))
        self._build_form()
        if row_id:
            self._load_values()

    def _build_form(self):
        form = ctk.CTkScrollableFrame(self)
        form.pack(fill="both", expand=True, padx=10, pady=10)

        self._entries: dict[int, ctk.CTkEntry | ctk.CTkCheckBox] = {}
        for col_id, col_name, col_type in self.columns_info:
            ctk.CTkLabel(form, text=col_name).pack(anchor="w", pady=(5, 0))
            if col_type == CustomColumnType.BOOLEAN.value:
                var = ctk.BooleanVar()
                cb = ctk.CTkCheckBox(form, text="", variable=var)
                cb.pack(anchor="w", pady=(0, 5))
                cb._variable = var
                self._entries[col_id] = cb
            else:
                entry = ctk.CTkEntry(form)
                entry.pack(fill="x", pady=(0, 5))
                self._entries[col_id] = entry

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(btn_frame, text="Сохранить", command=self._save).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Отмена", fg_color="gray",
                       command=self._on_cancel).pack(side="left", padx=5)

    def _load_values(self):
        with db_session(readonly=True) as session:
            row = session.query(CustomRow).options(
                joinedload(CustomRow.values)
            ).get(self.row_id)
            if not row:
                return
            values = {cv.column_id: cv.value for cv in row.values}
            for col_id, entry in self._entries.items():
                val = values.get(col_id, "")
                if isinstance(entry, ctk.CTkCheckBox):
                    if val and val.lower() in ("true", "1", "да"):
                        entry.select()
                else:
                    entry.delete(0, "end")
                    entry.insert(0, val or "")

    def _save(self):
        try:
            with db_session() as session:
                if self.row_id:
                    row = session.get(CustomRow, self.row_id)
                else:
                    row = CustomRow(tab_id=self.tab_id)
                    session.add(row)
                    session.flush()

                # Delete old values and insert new
                if self.row_id:
                    session.query(CustomCellValue).filter(
                        CustomCellValue.row_id == row.id
                    ).delete()

                for col_id, entry in self._entries.items():
                    if isinstance(entry, ctk.CTkCheckBox):
                        val = "true" if entry._variable.get() else "false"
                    else:
                        val = entry.get().strip()

                    cell = CustomCellValue(row_id=row.id, column_id=col_id, value=val)
                    session.add(cell)

            self._on_ok()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


class ColumnsDialog(ModalDialog):
    def __init__(self, parent, tab_id: int):
        super().__init__(parent, title="Управление столбцами", width=500, height=400)
        self.tab_id = tab_id
        self._build_form()
        self._load_columns()

    def _build_form(self):
        add_frame = ctk.CTkFrame(self)
        add_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(add_frame, text="Имя:").pack(side="left", padx=2)
        self.name_entry = ctk.CTkEntry(add_frame, width=150)
        self.name_entry.pack(side="left", padx=2)

        ctk.CTkLabel(add_frame, text="Тип:").pack(side="left", padx=2)
        self.type_var = ctk.StringVar(value="text")
        self.type_menu = ctk.CTkOptionMenu(
            add_frame, variable=self.type_var,
            values=["text", "number", "date", "boolean", "choice"], width=100
        )
        self.type_menu.pack(side="left", padx=2)

        ctk.CTkButton(add_frame, text="Добавить", width=80,
                       command=self._add_column).pack(side="left", padx=5)

        self.columns_list = ctk.CTkTextbox(self, state="disabled")
        self.columns_list.pack(fill="both", expand=True, padx=10, pady=5)

    def _load_columns(self):
        with db_session(readonly=True) as session:
            columns = session.query(CustomColumn).filter(
                CustomColumn.tab_id == self.tab_id
            ).order_by(CustomColumn.sort_order).all()
            self.columns_list.configure(state="normal")
            self.columns_list.delete("1.0", "end")
            for c in columns:
                self.columns_list.insert("end", f"{c.name} ({c.column_type})\n")
            if not columns:
                self.columns_list.insert("end", "Нет столбцов")
            self.columns_list.configure(state="disabled")

    def _add_column(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("Внимание", "Введите имя столбца")
            return

        try:
            with db_session() as session:
                max_order = session.query(CustomColumn).filter(
                    CustomColumn.tab_id == self.tab_id
                ).count()
                col = CustomColumn(
                    tab_id=self.tab_id,
                    name=name,
                    column_type=self.type_var.get(),
                    sort_order=max_order,
                )
                session.add(col)
            self.name_entry.delete(0, "end")
            self._load_columns()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
