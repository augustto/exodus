from collections.abc import Iterator
from urllib.error import URLError

import pytest

from exodus.infrastructure import rag
from exodus.infrastructure.enrichment import ollama


def _offline(model: str, prompt: str, progress: object, thinking: object) -> dict[str, object]:
    raise URLError("Ollama is offline in tests")


@pytest.fixture(autouse=True, scope="session")
def _offline_ollama() -> Iterator[None]:
    """Tests never call a local model nor Qdrant: they behave as unavailable (deterministic, fast).
    Session-scoped so module-scoped fixtures that run a scan are covered too."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ollama, "ask", _offline)
        patch.setattr(rag, "http_json", lambda *_: None)  # Qdrant and embeddings: offline
        yield
