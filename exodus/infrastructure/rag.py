"""RAG adapters: embeddings from the local Ollama (bge-m3) and the Qdrant vector store over its
REST API, both with the standard library only. Any network or format error means
"unavailable" (None/False), never an exception: the scan goes on without retrieval."""

import json
from collections.abc import Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request

from exodus.application.ports import Hit, StoredPiece
from exodus.infrastructure.local_http import DIRECT_OPENER

EMBEDDING_MODEL = "bge-m3"
OLLAMA_URL = "http://localhost:11434"
QDRANT_URL = "http://localhost:6333"
TIMEOUT_SECONDS = 120


def http_json(method: str, url: str, body: object | None = None) -> Any | None:
    """The JSON answer of a request; None when the service is down or answers an error."""
    try:
        parts = urlsplit(url)
        if (
            parts.scheme not in {"http", "https"}
            or parts.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parts.username is not None
        ):
            return None
    except ValueError:
        return None
    data = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with DIRECT_OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read() or b"{}")
    except (HTTPError, URLError, OSError, ValueError):
        return None


class OllamaEmbedder:
    def __init__(self, model: str = EMBEDDING_MODEL, url: str = OLLAMA_URL) -> None:
        self.model = model
        self.url = url

    def embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        answer = http_json(
            "POST", f"{self.url}/api/embed", {"model": self.model, "input": list(texts)}
        )
        vectors = answer.get("embeddings") if isinstance(answer, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            return None
        return [[float(x) for x in vector] for vector in vectors]


class QdrantStore:
    """One collection per analyzed project; each point keeps the piece's text, title and source
    (file:line) as payload, which is what the Qdrant dashboard shows."""

    def __init__(self, url: str = QDRANT_URL) -> None:
        self.url = url

    def ids(self, collection: str) -> set[str] | None:
        found = http_json("GET", f"{self.url}/collections")
        if not isinstance(found, dict):
            return None
        names = {c.get("name") for c in found.get("result", {}).get("collections", [])}
        if collection not in names:
            return set()
        ids: set[str] = set()
        offset: object = None
        while True:
            body = {"limit": 256, "with_payload": False, "with_vector": False, "offset": offset}
            page = http_json("POST", f"{self.url}/collections/{collection}/points/scroll", body)
            if not isinstance(page, dict):
                return None
            result = page.get("result", {})
            ids |= {str(p["id"]) for p in result.get("points", [])}
            offset = result.get("next_page_offset")
            if offset is None:
                return ids

    def save(
        self, collection: str, pieces: Sequence[StoredPiece], vectors: Sequence[list[float]]
    ) -> bool:
        if not vectors:
            return True
        ids = self.ids(collection)
        if ids is None:
            return False
        if not ids and http_json("GET", f"{self.url}/collections/{collection}") is None:
            config = {"vectors": {"size": len(vectors[0]), "distance": "Cosine"}}
            if http_json("PUT", f"{self.url}/collections/{collection}", config) is None:
                return False
        points = [
            {
                "id": p.id,
                "vector": v,
                "payload": {"title": p.title, "text": p.text, "source": p.source},
            }
            for p, v in zip(pieces, vectors, strict=True)
        ]
        url = f"{self.url}/collections/{collection}/points?wait=true"
        return http_json("PUT", url, {"points": points}) is not None

    def delete(self, collection: str, ids: Sequence[str]) -> bool:
        url = f"{self.url}/collections/{collection}/points/delete?wait=true"
        return http_json("POST", url, {"points": list(ids)}) is not None

    def search(self, collection: str, vector: list[float], limit: int) -> list[Hit] | None:
        body = {"vector": vector, "limit": limit, "with_payload": True}
        found = http_json("POST", f"{self.url}/collections/{collection}/points/search", body)
        if not isinstance(found, dict):
            return None
        return [
            Hit(
                score=float(point["score"]),
                piece=StoredPiece(
                    id=str(point["id"]),
                    title=str(point["payload"].get("title", "")),
                    text=str(point["payload"].get("text", "")),
                    source=str(point["payload"].get("source", "")),
                ),
            )
            for point in found.get("result", [])
        ]
