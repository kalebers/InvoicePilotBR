from io import BytesIO

import fitz
from PIL import Image
import pytest

from src.document_reader import DocumentReadError, extract_text


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    result = document.tobytes()
    document.close()
    return result


def test_extracts_text_from_digital_pdf():
    assert "Total pago" in extract_text("recibo.pdf", make_pdf("Total pago: R$ 20,50"))


def test_rejects_unsupported_and_malformed_files():
    with pytest.raises(DocumentReadError, match="Formato não suportado"):
        extract_text("recibo.docx", b"not a document")
    with pytest.raises(DocumentReadError, match="assinatura PDF"):
        extract_text("recibo.pdf", b"not a PDF")
    with pytest.raises(DocumentReadError, match="ler este PDF"):
        extract_text("recibo.pdf", b"%PDF-1.4\ninvalid")


def test_image_ocr_requires_tesseract_language_pack(monkeypatch):
    image = Image.new("RGB", (5, 5), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    monkeypatch.setattr("src.document_reader.pytesseract.get_languages", lambda config: ["eng"])
    with pytest.raises(DocumentReadError, match="idioma OCR 'por'"):
        extract_text("recibo.png", buffer.getvalue())


def test_scanned_pdf_uses_ocr(monkeypatch):
    document = fitz.open()
    page = document.new_page()
    image = Image.new("RGB", (20, 20), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    page.insert_image(fitz.Rect(0, 0, 100, 100), stream=buffer.getvalue())
    content = document.tobytes()
    document.close()
    monkeypatch.setattr("src.document_reader._ocr", lambda image, language: "Total: R$ 10,00")
    assert extract_text("scan.pdf", content) == "Total: R$ 10,00"


def test_image_signature_must_match_extension():
    with pytest.raises(DocumentReadError, match="assinatura"):
        extract_text("recibo.png", b"\xff\xd8\xffjpeg bytes")
