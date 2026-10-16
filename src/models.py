"""Validated expense data structures."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExpenseCategory = Literal[
    "food",
    "transportation",
    "software",
    "office_supplies",
    "utilities",
    "healthcare",
    "taxes",
    "other",
    "unknown",
]


class ExpenseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    source_filename: str
    supplier: Optional[str] = None
    document_date: Optional[date] = None
    amount: Optional[Decimal] = None
    currency: str = "BRL"
    category: ExpenseCategory = "unknown"
    description: Optional[str] = None
    needs_review: bool = False
    review_notes: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_finite_and_nonnegative(
        cls, value: Optional[Decimal]
    ) -> Optional[Decimal]:
        if value is not None and (not value.is_finite() or value < 0):
            raise ValueError("O valor deve ser um decimal finito e não negativo.")
        return value

    @field_validator("currency")
    @classmethod
    def currency_must_be_iso_code(cls, value: str) -> str:
        normalized = value.upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("A moeda deve ser um código de três letras.")
        return normalized
