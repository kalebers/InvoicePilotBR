"""Business validation and normalization for extracted expense records."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from src.models import ExpenseRecord


class ExpenseValidationError(ValueError):
    """Raised when an edited expense cannot be validated."""


def normalize_document_date(value: str | date | None) -> date | None:
    """Parse ISO dates or unambiguous Brazilian DD/MM/YYYY dates."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    text = value.strip()
    for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    raise ExpenseValidationError("Data inválida. Use AAAA-MM-DD ou DD/MM/AAAA.")


def parse_amount(value: str | int | Decimal | None) -> Decimal | None:
    """Parse a decimal amount without using binary floating-point arithmetic."""
    if value is None or value == "":
        return None
    if isinstance(value, float):
        raise ExpenseValidationError("Valor monetário deve ser informado como texto decimal.")
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in text and "." in text:
        # Brazilian input commonly uses dots for thousands and comma for decimals.
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation as error:
        raise ExpenseValidationError("Valor monetário inválido.") from error
    if not amount.is_finite() or amount < 0:
        raise ExpenseValidationError("O valor deve ser um decimal finito e não negativo.")
    return amount


def validate_expense_record(data: dict, default_currency: str = "BRL") -> ExpenseRecord:
    """Validate one record and flag missing key information for human review."""
    values = dict(data)
    values.setdefault("currency", default_currency)
    try:
        values["document_date"] = normalize_document_date(values.get("document_date"))
        values["amount"] = parse_amount(values.get("amount"))
        record = ExpenseRecord.model_validate(values)
    except (ValidationError, ExpenseValidationError) as error:
        raise ExpenseValidationError("Os dados da despesa são inválidos.") from error

    missing = []
    for field, label in (
        ("supplier", "fornecedor"),
        ("document_date", "data"),
        ("amount", "valor"),
    ):
        if getattr(record, field) is None:
            missing.append(label)
    if missing:
        notes = record.review_notes.strip() if record.review_notes else ""
        missing_note = f"Campo(s) não identificado(s): {', '.join(missing)}."
        record.needs_review = True
        record.review_notes = f"{notes} {missing_note}".strip()
    return record
