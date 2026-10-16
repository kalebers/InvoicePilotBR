"""CSV export for explicitly user-approved records."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Iterable

from src.models import ExpenseRecord

CSV_COLUMNS = [
    "arquivo_origem",
    "fornecedor",
    "data",
    "valor",
    "moeda",
    "categoria",
    "descricao",
]
TEXT_FIELDS = {"arquivo_origem", "fornecedor", "moeda", "categoria", "descricao"}


def sanitize_spreadsheet_text(value: str | None) -> str:
    """Prefix spreadsheet formula initiators in untrusted text fields."""
    text = value or ""
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def export_approved_records(
    records: Iterable[ExpenseRecord], approved_ids: set[str]
) -> str:
    """Serialize only approved, schema-valid records as UTF-8 semicolon CSV."""
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, delimiter=";", lineterminator="\n")
    writer.writeheader()
    for record in records:
        if record.id not in approved_ids:
            continue
        values = {
            "arquivo_origem": record.source_filename,
            "fornecedor": record.supplier or "",
            "data": record.document_date.isoformat() if record.document_date else "",
            "valor": format(record.amount, "f") if record.amount is not None else "",
            "moeda": record.currency,
            "categoria": record.category,
            "descricao": record.description or "",
        }
        for field in TEXT_FIELDS:
            values[field] = sanitize_spreadsheet_text(values[field])
        writer.writerow(values)
    return output.getvalue()
