import pytest

from src.config import Settings


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://[::1]:11434",
    ],
)
def test_ollama_base_url_must_be_local_and_accepts_loopback(url):
    assert Settings(ollama_base_url=url).ollama_base_url == url.rstrip("/")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://203.0.113.10:11434",
        "file:///tmp/ollama",
        "http://localhost:invalid",
    ],
)
def test_rejects_nonlocal_ollama_endpoint(url):
    with pytest.raises(ValueError, match="endpoint local"):
        Settings(ollama_base_url=url)


def test_ollama_timeout_must_be_positive():
    with pytest.raises(ValueError, match="OLLAMA_TIMEOUT_SECONDS"):
        Settings(ollama_timeout_seconds=0)
