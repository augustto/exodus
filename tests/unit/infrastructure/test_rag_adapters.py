from typing import Any

import pytest

from exodus.application.ports import Hit, StoredPiece
from exodus.infrastructure import rag
from exodus.infrastructure.rag import OllamaEmbedder, QdrantStore

PIECE = StoredPiece(id="11111111-1111-5111-8111-111111111111", title="T", text="x", source="f:1")


class FakeHttp:
    """Answers by (method, path suffix); records every call."""

    def __init__(self, answers: dict[tuple[str, str], Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str, object]] = []

    def __call__(self, method: str, url: str, body: object | None = None) -> Any:
        self.calls.append((method, url, body))
        for (m, suffix), answer in self.answers.items():
            if m == method and url.endswith(suffix):
                return answer
        return None


def test_embedder_calls_ollama_embed_and_checks_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    http = FakeHttp({("POST", "/api/embed"): {"embeddings": [[1, 2], [3, 4]]}})
    monkeypatch.setattr(rag, "http_json", http)
    assert OllamaEmbedder().embed(["a", "b"]) == [[1.0, 2.0], [3.0, 4.0]]
    assert http.calls[0][2] == {"model": "bge-m3", "input": ["a", "b"]}
    assert OllamaEmbedder().embed(["only one of two", "x"]) is not None  # same fake answer
    monkeypatch.setattr(rag, "http_json", FakeHttp({}))
    assert OllamaEmbedder().embed(["a"]) is None


def test_store_creates_the_collection_once_and_saves_pieces_with_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = FakeHttp(
        {
            ("GET", "/collections"): {"result": {"collections": []}},
            ("PUT", "/collections/exodus-b"): {"result": True},
            ("PUT", "/points?wait=true"): {"result": {}},
        }
    )
    monkeypatch.setattr(rag, "http_json", http)
    assert QdrantStore().ids("exodus-b") == set()
    assert QdrantStore().save("exodus-b", [PIECE], [[0.1, 0.2]])
    created = [c for c in http.calls if c[0] == "PUT" and c[1].endswith("/collections/exodus-b")]
    assert created[0][2] == {"vectors": {"size": 2, "distance": "Cosine"}}
    [upsert] = [c for c in http.calls if c[1].endswith("/points?wait=true")]
    assert upsert[2] == {
        "points": [{"id": PIECE.id, "vector": [0.1, 0.2],
                    "payload": {"title": "T", "text": "x", "source": "f:1"}}]
    }  # fmt: skip


def test_store_pages_through_ids_and_searches(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = iter(
        [
            {"result": {"points": [{"id": "a"}], "next_page_offset": "b"}},
            {"result": {"points": [{"id": "b"}], "next_page_offset": None}},
        ]
    )

    def http(method: str, url: str, body: object | None = None) -> Any:
        if url.endswith("/collections"):
            return {"result": {"collections": [{"name": "c"}]}}
        if url.endswith("/points/scroll"):
            return next(pages)
        if url.endswith("/points/search"):
            return {"result": [{"id": "a", "score": 0.8, "payload": {"title": "T", "text": "x",
                                                                   "source": "f:1"}}]}  # fmt: skip
        return None

    monkeypatch.setattr(rag, "http_json", http)
    store = QdrantStore()
    assert store.ids("c") == {"a", "b"}
    assert store.search("c", [0.1], 5) == [
        Hit(score=0.8, piece=StoredPiece(id="a", title="T", text="x", source="f:1"))
    ]


def test_store_down_means_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rag, "http_json", FakeHttp({}))
    store = QdrantStore()
    assert store.ids("c") is None
    assert store.search("c", [0.1], 5) is None
    assert not store.save("c", [PIECE], [[0.1]])
    assert not store.delete("c", ["a"])
    assert store.save("c", [], [])  # nothing to save


def test_local_http_rejects_external_and_file_urls() -> None:
    assert rag.http_json("GET", "file:///etc/passwd") is None
    assert rag.http_json("POST", "https://example.com/api/embed", {"input": ["source"]}) is None
    assert rag.http_json("GET", "http://user:pass@localhost:6333/collections") is None
