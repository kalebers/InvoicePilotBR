import csv
from datetime import date
from decimal import Decimal
from io import StringIO

from src.exporter import CSV_COLUMNS, export_approved_records
from src.models import ExpenseRecord


def make_record(**values):
    defaults = {
        "id": "record-1",
        "source_filename": "recibo.pdf",
        "supplier": "Mercado Exemplo",
        "document_date": date(2025, 3, 15),
        "amount": Decimal("125.90"),
        "currency": "BRL",
        "category": "food",
        "description": "Compra",
    }
    defaults.update(values)
    return ExpenseRecord(**defaults)


def test_csv_headers_delimiter_utf8_and_values():
    csv_text = export_approved_records([make_record(supplier="Café São José")], {"record-1"})
    rows = list(csv.reader(StringIO(csv_text), delimiter=";"))
    assert rows[0] == CSV_COLUMNS
    assert rows[1] == [
        "recibo.pdf", "Café São José", "2025-03-15", "125.90", "BRL", "food", "Compra"
    ]
    assert "Café".encode("utf-8") in csv_text.encode("utf-8")


def test_export_excludes_unapproved_and_protects_formulas():
    records = [
        make_record(id="approved", source_filename="=HYPERLINK(\"bad\")", supplier="@SUM(1,1)"),
        make_record(id="not-approved", amount=Decimal("99.00")),
    ]
    csv_text = export_approved_records(records, {"approved"})
    rows = list(csv.reader(StringIO(csv_text), delimiter=";"))
    assert len(rows) == 2
    assert rows[1][0].startswith("'=")
    assert rows[1][1].startswith("'@")
    assert rows[1][3] == "125.90"


def test_formula_like_negative_text_sanitized_but_amount_stays_numeric():
    record = make_record(description="-1+1")
    rows = list(csv.reader(StringIO(export_approved_records([record], {record.id})), delimiter=";"))
    assert rows[1][3] == "125.90"
    assert rows[1][6] == "'-1+1"
