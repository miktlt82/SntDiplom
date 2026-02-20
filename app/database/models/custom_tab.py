"""Custom tab EAV models."""

from __future__ import annotations
from sqlalchemy import String, Integer, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class CustomTab(TimestampMixin, Base):
    __tablename__ = "custom_tabs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    columns: Mapped[list[CustomColumn]] = relationship(
        back_populates="tab", cascade="all, delete-orphan",
        order_by="CustomColumn.sort_order"
    )
    rows: Mapped[list[CustomRow]] = relationship(
        back_populates="tab", cascade="all, delete-orphan"
    )


class CustomColumn(TimestampMixin, Base):
    __tablename__ = "custom_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tab_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("custom_tabs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    column_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    choices: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON for choice type

    tab: Mapped[CustomTab] = relationship(back_populates="columns")


class CustomRow(TimestampMixin, Base):
    __tablename__ = "custom_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tab_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("custom_tabs.id", ondelete="CASCADE"), nullable=False
    )

    tab: Mapped[CustomTab] = relationship(back_populates="rows")
    values: Mapped[list[CustomCellValue]] = relationship(
        back_populates="row", cascade="all, delete-orphan"
    )


class CustomCellValue(TimestampMixin, Base):
    __tablename__ = "custom_cell_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    row_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("custom_rows.id", ondelete="CASCADE"), nullable=False
    )
    column_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("custom_columns.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[str | None] = mapped_column(Text, nullable=True)

    row: Mapped[CustomRow] = relationship(back_populates="values")
