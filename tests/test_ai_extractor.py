import json
from decimal import Decimal
from types import SimpleNamespace

import httpx
import ollama
import pytest

from src.ai_extractor import ExtractionError, check_ollama_connection, extract_expense


def response_with(content: str):
    return SimpleNamespace(message=SimpleNamespace(content=content))


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
    assert captured["format"]["properties"]["amount"]
    assert captured["messages"][1]["content"] == "Total pago R$ 42,90"
    assert "recibo.pdf" not in captured["messages"][1]["content"]


def test_malformed_model_response_is_reported(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass

        def chat(self, **kwargs):
            return response_with("not JSON")

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    with pytest.raises(ExtractionError, match="não pôde ser validada"):
        extract_expense("texto", "recibo.pdf")


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
