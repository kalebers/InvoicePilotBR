from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.models import ExpenseRecord
from src.validator import ExpenseValidationError, normalize_document_date, validate_expense_record


def test_expense_record_accepts_decimal_and_valid_category():
    record = ExpenseRecord(
        source_filename="recibo.pdf",
        document_date=date(2025, 3, 15),
        amount=Decimal("125.90"),
        category="food",
    )
    assert record.amount == Decimal("125.90")
    assert record.currency == "BRL"


def test_expense_record_rejects_unknown_category_and_negative_amount():
    with pytest.raises(ValidationError):
        ExpenseRecord(source_filename="x.pdf", category="groceries")
    with pytest.raises(ValidationError):
        ExpenseRecord(source_filename="x.pdf", amount=Decimal("-1"))


@pytest.mark.parametrize(
    ("date_value", "expected"),
    [
        ("2025-03-15", date(2025, 3, 15)),
        ("15/03/2025", date(2025, 3, 15)),
        (None, None),
    ],
)
def test_date_normalization(date_value, expected):
    assert normalize_document_date(date_value) == expected


def test_invalid_or_ambiguous_date_is_rejected():
    with pytest.raises(ExpenseValidationError):
        normalize_document_date("31/02/2025")
    with pytest.raises(ExpenseValidationError):
        normalize_document_date("03/04/25")


@pytest.mark.parametrize("missing", ["supplier", "document_date", "amount"])
def test_missing_important_fields_require_review(missing):
    data = {
        "source_filename": "recibo.pdf",
        "supplier": "Mercado Exemplo",
        "document_date": "2025-03-15",
        "amount": "20.50",
    }
    data[missing] = None
    record = validate_expense_record(data)
    assert record.needs_review
    assert record.review_notes
