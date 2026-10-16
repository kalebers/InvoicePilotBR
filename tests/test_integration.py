import json
from types import SimpleNamespace

import fitz

from src.ai_extractor import extract_expense
from src.document_reader import extract_text


def test_pdf_text_to_mocked_expense_integration(monkeypatch):
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Mercado Exemplo\nTotal pago: R$ 42,90")
    content = pdf.tobytes()
    pdf.close()
    model_response = {
        "supplier": "Mercado Exemplo",
        "document_date": None,
        "amount": 42.90,
        "currency": "BRL",
        "category": "food",
        "description": "Compra no mercado",
        "needs_review": True,
        "review_notes": "Data não identificada.",
    }

    class Client:
        def __init__(self, **kwargs):
            pass

        def chat(self, **kwargs):
            return SimpleNamespace(message=SimpleNamespace(content=json.dumps(model_response)))

    monkeypatch.setattr("src.ai_extractor.ollama.Client", Client)
    text = extract_text("recibo.pdf", content)
    record = extract_expense(text, "recibo.pdf")
    assert record.supplier == "Mercado Exemplo"
    assert str(record.amount) == "42.9"
    assert record.needs_review
    assert "data" in record.review_notes
