"""Safe, in-memory extraction of text from PDF and image uploads."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import PurePath

import fitz
from PIL import Image, UnidentifiedImageError
import pytesseract

from src.config import settings

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


class DocumentReadError(ValueError):
    """Raised when a document cannot be safely read or OCR'd."""


def _ocr(image: Image.Image, language: str) -> str:
    try:
        installed = pytesseract.get_languages(config="")
    except pytesseract.TesseractNotFoundError as error:
        raise DocumentReadError(
            "Tesseract não está instalado ou não foi encontrado. Instale-o para usar OCR."
        ) from error
    if language not in installed:
        raise DocumentReadError(
            f"O pacote de idioma OCR '{language}' não está instalado no Tesseract."
        )
    try:
        return pytesseract.image_to_string(image, lang=language)
    except pytesseract.TesseractNotFoundError as error:
        raise DocumentReadError(
            "Tesseract não está instalado ou não foi encontrado. Instale-o para usar OCR."
        ) from error
    except pytesseract.TesseractError as error:
        raise DocumentReadError("Não foi possível executar o OCR deste documento.") from error


def extract_text(filename: str, content: bytes, ocr_language: str | None = None) -> str:
    """Validate upload signatures and extract text without persisting the source file."""
    extension = PurePath(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise DocumentReadError("Formato não suportado. Envie PDF, PNG, JPG ou JPEG.")
    if not content:
        raise DocumentReadError("O documento está vazio.")

    language = ocr_language or settings.ocr_language
    if extension == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise DocumentReadError("O arquivo não possui uma assinatura PDF válida.")
        try:
            with fitz.open(stream=content, filetype="pdf") as document:
                text = "\n".join(page.get_text() for page in document).strip()
                if text:
                    return text
                ocr_pages = [
                    Image.open(BytesIO(page.get_pixmap(dpi=200).tobytes("png")))
                    for page in document
                ]
        except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError, ValueError) as error:
            raise DocumentReadError("Não foi possível ler este PDF.") from error
        text = "\n".join(_ocr(page, language) for page in ocr_pages).strip()
    else:
        expected_signatures = {
            ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
            ".jpg": content.startswith(b"\xff\xd8\xff"),
            ".jpeg": content.startswith(b"\xff\xd8\xff"),
        }
        if not expected_signatures[extension]:
            raise DocumentReadError("A assinatura do arquivo não corresponde a uma imagem válida.")
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
            with Image.open(BytesIO(content)) as image:
                text = _ocr(image.convert("RGB"), language).strip()
        except DocumentReadError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise DocumentReadError("Não foi possível ler esta imagem.") from error

    if not text:
        raise DocumentReadError("Nenhum texto foi encontrado no documento.")
    return text


def content_fingerprint(content: bytes) -> str:
    """Return an in-memory digest for duplicate detection inside one batch."""
    return sha256(content).hexdigest()
