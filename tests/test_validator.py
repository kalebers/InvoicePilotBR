from decimal import Decimal

import pytest

from src.validator import ExpenseValidationError, parse_amount


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("125,90", Decimal("125.90")),
        ("1.234,56", Decimal("1234.56")),
        ("125.90", Decimal("125.90")),
    ],
)
def test_parse_amount_as_decimal(text, expected):
    assert parse_amount(text) == expected


def test_parse_amount_rejects_float_and_invalid_values():
    with pytest.raises(ExpenseValidationError):
        parse_amount(12.5)
    with pytest.raises(ExpenseValidationError):
        parse_amount("not money")
