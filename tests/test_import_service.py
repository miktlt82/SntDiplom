"""Tests for CSV/Excel import service."""

from __future__ import annotations
import csv
import tempfile
from pathlib import Path
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.database.models.member import Member
from app.services.import_service import import_members_csv, import_members_excel


@pytest.fixture()
def csv_file(tmp_path):
    """Create a temporary CSV file with test data."""
    path = tmp_path / "members.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["участок", "фамилия", "имя", "отчество", "площадь", "телефон", "email"])
        writer.writerow(["101", "Козлов", "Алексей", "Петрович", "8", "+71234567890", "kozlov@test.ru"])
        writer.writerow(["102", "Волков", "Дмитрий", "", "12", "", ""])
    return path


@pytest.fixture()
def csv_file_missing_fields(tmp_path):
    """CSV where some rows are missing required fields."""
    path = tmp_path / "bad.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["участок", "фамилия", "имя"])
        writer.writerow(["201", "Орлов", "Олег"])
        writer.writerow(["", "Безучасток", "Иван"])  # missing plot_number
        writer.writerow(["203", "", ""])  # missing last_name and first_name
    return path


@pytest.fixture()
def excel_file(tmp_path):
    """Create a temporary Excel file with test data."""
    path = tmp_path / "members.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["участок", "фамилия", "имя", "отчество", "площадь", "телефон", "email"])
    ws.append(["301", "Лебедев", "Артём", "Сергеевич", 7, "+79001112233", "lebedev@test.ru"])
    ws.append(["302", "Новиков", "Виктор", None, 15, None, None])
    wb.save(path)
    return path


class TestImportCSV:
    def test_normal_import(self, session, csv_file):
        result = import_members_csv(csv_file)
        assert result["created"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == []

        members = session.query(Member).all()
        assert len(members) == 2
        m1 = session.query(Member).filter(Member.plot_number == "101").one()
        assert m1.last_name == "Козлов"
        assert m1.plot_area == Decimal("8")

    def test_skip_duplicates(self, session, csv_file):
        import_members_csv(csv_file)
        result = import_members_csv(csv_file)
        assert result["created"] == 0
        assert result["skipped"] == 2

    def test_missing_fields_error(self, session, csv_file_missing_fields):
        result = import_members_csv(csv_file_missing_fields)
        assert result["created"] == 1  # only row with plot=201
        assert len(result["errors"]) == 2  # rows with missing fields


class TestImportExcel:
    def test_normal_import(self, session, excel_file):
        result = import_members_excel(excel_file)
        assert result["created"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == []

        m = session.query(Member).filter(Member.plot_number == "301").one()
        assert m.last_name == "Лебедев"
        assert m.plot_area == Decimal("7")

    def test_skip_duplicates(self, session, excel_file):
        import_members_excel(excel_file)
        result = import_members_excel(excel_file)
        assert result["created"] == 0
        assert result["skipped"] == 2
