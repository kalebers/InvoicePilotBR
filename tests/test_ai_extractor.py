import json
from decimal import Decimal
from types import SimpleNamespace

import httpx
import ollama
import pytest

from src.ai_extractor import ExtractionError, check_ollama_connection, extract_expense


def response_with(content: str):
    return SimpleNamespace(message=SimpleNamespace(content=content))


def model_payload(**values):
    payload = {
        "supplier": None,
        "document_date": None,
        "amount": None,
        "currency": "BRL",
        "category": "unknown",
        "description": None,
        "needs_review": True,
        "review_notes": None,
    }
    payload.update(values)
    return payload


def test_local_extraction_returns_validated_record(monkeypatch):
    payload = {
        "supplier": "Mercado Exemplo",
        "document_date": "2025-03-15",
        "amount": 42.9,
        "currency": "BRL",
        "category": "food",
        "description": "Compra",
        "needs_review": False,
        "review_notes": None,
    }
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

        def chat(self, **kwargs):
            captured.update(kwargs)
            return response_with(json.dumps(payload))

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    record = extract_expense("Total pago R$ 42,90", "recibo.pdf")
    assert record.source_filename == "recibo.pdf"
    assert record.amount == Decimal("42.9")
    assert captured["options"]["temperature"] == 0
    assert captured["options"]["num_predict"] == 256
    assert captured["think"] is False
    assert captured["format"]["properties"]["amount"]
    assert set(captured["format"]["required"]) == {
        "supplier",
        "document_date",
        "amount",
        "currency",
        "category",
        "description",
        "needs_review",
        "review_notes",
    }
    assert "source_filename" not in captured["format"]["properties"]
    assert "id" not in captured["format"]["properties"]
    assert captured["messages"][1]["content"] == "Total pago R$ 42,90"
    assert "recibo.pdf" not in captured["messages"][1]["content"]


def test_malformed_model_response_is_reported(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass

        def chat(self, **kwargs):
            return response_with("not JSON")

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    with pytest.raises(ExtractionError, match="não é JSON válido"):
        extract_expense("texto", "recibo.pdf")


@pytest.mark.parametrize(
    ("payload", "expected_category", "expected_review_text"),
    [
        (
            model_payload(supplier="ISP Exemplo", document_date="2026-01-09",
                          amount=125.90, needs_review=False, category="internet"),
            "utilities",
            None,
        ),
        (
            model_payload(supplier="ISP Exemplo", document_date="2026-02-31",
                          amount=125.90, needs_review=False, category="utilities"),
            "utilities",
            "Data não pôde ser normalizada",
        ),
    ],
)
def test_model_fields_are_normalized_and_uncertainty_flagged(
    monkeypatch, payload, expected_category, expected_review_text
):
    class Client:
        def __init__(self, **kwargs):
            pass

        def chat(self, **kwargs):
            return response_with(json.dumps(payload))

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    record = extract_expense("dados sintéticos", "recibo-sintetico.pdf")
    assert record.category == expected_category
    if expected_review_text:
        assert record.needs_review
        assert expected_review_text in record.review_notes


def test_localized_amount_string_is_normalized_to_decimal(monkeypatch):
    payload = model_payload(
        supplier="ISP Exemplo",
        document_date="2026-01-09",
        amount="R$ 1.234,56",
        currency="R$",
        category="utilities",
        description="Internet",
        needs_review=False,
    )

    class Client:
        def __init__(self, **kwargs):
            pass

        def chat(self, **kwargs):
            return response_with(json.dumps(payload))

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    record = extract_expense("dados sintéticos", "recibo-sintetico.pdf")
    assert record.amount == Decimal("1234.56")
    assert record.currency == "BRL"
    assert not record.needs_review


def test_unrecognized_category_is_unknown_and_requires_review(monkeypatch):
    payload = model_payload(
        supplier="ISP Exemplo",
        document_date="2026-01-09",
        amount=125.90,
        category="connectivity",
    )

    class Client:
        def __init__(self, **kwargs):
            pass

        def chat(self, **kwargs):
            return response_with(json.dumps(payload))

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    record = extract_expense("dados sintéticos", "recibo-sintetico.pdf")
    assert record.category == "unknown"
    assert record.needs_review
    assert "Categoria não reconhecida" in record.review_notes


def test_model_response_missing_required_fields_is_actionable(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass

        def chat(self, **kwargs):
            return response_with('{"amount": 10.50}')

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    with pytest.raises(ExtractionError, match="campos em formato inesperado") as error:
        extract_expense("dados sintéticos", "recibo-sintetico.pdf")
    assert "supplier" in str(error.value)


def test_ollama_connection_failure_is_user_friendly(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass

        def list(self):
            raise httpx.ConnectError("private connection details")

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    connected, message = check_ollama_connection()
    assert not connected
    assert message == "Não foi possível conectar ao Ollama local."


def test_inference_timeout_has_distinct_actionable_message(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["timeout"] == 300

        def chat(self, **kwargs):
            raise httpx.ReadTimeout("private timeout details")

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    with pytest.raises(ExtractionError, match="Ollama demorou demais"):
        extract_expense("texto", "recibo.pdf")


def test_missing_model_error_is_actionable(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass

        def chat(self, **kwargs):
            raise ollama.ResponseError("missing model", status_code=404)

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    with pytest.raises(ExtractionError, match="ollama pull qwen3:4b"):
        extract_expense("texto", "recibo.pdf")


def test_ollama_connection_reports_missing_configured_model(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass

        def list(self):
            return {"models": [{"name": "llama3:8b"}]}

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    connected, message = check_ollama_connection()
    assert not connected
    assert "não está instalado" in message
