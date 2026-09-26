"""Retrieval over the legacy's written documentation (the RAG example).

Indexing keeps the vector store in step with the documents of a scan: a piece's id comes from
its place and text, so only new or changed pieces are embedded, and pieces no longer in the
documents are removed. Retrieval embeds a question and keeps the pieces close enough to it.
Neither ever raises when the model or the store is down: the result says it was unavailable.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from exodus.application.ports import EmbeddingModel, Hit, StoredPiece, VectorStore
from exodus.application.use_cases.scan_projects import ProjectScan
from exodus.domain.facts import DocumentSection

BATCH = 32  # pieces embedded per request
MIN_SCORE = 0.45  # cosine similarity below which a piece is not about the question
CANDIDATES = 4  # pieces fetched per piece wanted, to still have enough after removing repeats


@dataclass(frozen=True)
class IndexResult:
    available: bool
    pieces: int = 0  # in the documents now
    embedded: int = 0  # new or changed, embedded in this run
    removed: int = 0  # no longer in the documents


def pieces_of(scans: Sequence[ProjectScan]) -> list[StoredPiece]:
    found: dict[str, StoredPiece] = {}
    for scan in scans:
        for fact in scan.facts:
            if isinstance(fact, DocumentSection):
                source = str(fact.evidence)
                piece_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}\n{fact.text}"))
                found[piece_id] = StoredPiece(
                    id=piece_id, title=fact.title, text=fact.text, source=source
                )
    return list(found.values())


def index_documents(
    scans: Sequence[ProjectScan],
    collection: str,
    embedder: EmbeddingModel,
    store: VectorStore,
) -> IndexResult:
    pieces = pieces_of(scans)
    kept = store.ids(collection)
    if kept is None:
        return IndexResult(available=False)
    current = {p.id for p in pieces}
    missing = [p for p in pieces if p.id not in kept]
    for start in range(0, len(missing), BATCH):
        batch = missing[start : start + BATCH]
        vectors = embedder.embed([p.text for p in batch])
        if vectors is None or not store.save(collection, batch, vectors):
            return IndexResult(available=False)
    stale = sorted(kept - current)
    if stale and not store.delete(collection, stale):
        return IndexResult(available=False)
    return IndexResult(True, pieces=len(pieces), embedded=len(missing), removed=len(stale))


class DocumentRetriever:
    """Finds the pieces of documentation closest to a question."""

    def __init__(
        self,
        embedder: EmbeddingModel,
        store: VectorStore,
        collection: str,
        min_score: float = MIN_SCORE,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.collection = collection
        self.min_score = min_score

    def search(self, question: str, limit: int = 5) -> list[Hit]:
        """The closest pieces, each text once: a block repeated in several files (the same
        README intro in every service) would otherwise fill every place."""
        vectors = self.embedder.embed([question])
        if not vectors:
            return []
        candidates = self.store.search(self.collection, vectors[0], limit * CANDIDATES) or []
        hits: list[Hit] = []
        seen: set[str] = set()
        for hit in candidates:
            text = " ".join(hit.piece.text.split()).lower()
            if hit.score >= self.min_score and text not in seen:
                seen.add(text)
                hits.append(hit)
        return hits[:limit]
