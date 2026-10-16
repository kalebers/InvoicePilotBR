"""Application settings loaded from environment variables and .env."""

from dataclasses import dataclass
import ipaddress
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:4b")
    default_currency: str = os.getenv("DEFAULT_CURRENCY", "BRL").upper()
    max_file_size_mb: int = int(os.getenv("MAX_FILE_SIZE_MB", "15"))
    max_files_per_batch: int = int(os.getenv("MAX_FILES_PER_BATCH", "20"))
    ocr_language: str = os.getenv("OCR_LANGUAGE", "por")

    def __post_init__(self) -> None:
        if self.max_file_size_mb < 1 or self.max_files_per_batch < 1:
            raise ValueError("Os limites de arquivos devem ser maiores que zero.")
        if len(self.default_currency) != 3 or not self.default_currency.isalpha():
            raise ValueError("DEFAULT_CURRENCY deve ser um código de três letras.")
        parsed_url = urlsplit(self.ollama_base_url)
        host = parsed_url.hostname
        try:
            parsed_url.port
            valid_authority = bool(parsed_url.netloc)
        except ValueError:
            valid_authority = False
        try:
            local_host = host == "localhost" or (
                host is not None and ipaddress.ip_address(host).is_loopback
            )
        except ValueError:
            local_host = False
        if (
            parsed_url.scheme not in {"http", "https"}
            or not valid_authority
            or not local_host
        ):
            raise ValueError("OLLAMA_BASE_URL deve apontar para um endpoint local (loopback).")


settings = Settings()
