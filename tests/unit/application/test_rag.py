from collections.abc import Sequence

from exodus.application.ports import Hit, StoredPiece
from exodus.application.use_cases.rag import DocumentRetriever, index_documents
from exodus.application.use_cases.scan_projects import ProjectScan
from exodus.domain.facts import DocumentSection, ModuleDeclared
from exodus.domain.model import Evidence


def section(text: str, line: int = 1) -> DocumentSection:
    return DocumentSection(
        title="Billing", text=text, evidence=Evidence(file="b/README.md", line=line, snippet="")
    )


class FakeEmbedder:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        self.calls.append(list(texts))
        return [[float(len(t)), 1.0] for t in texts] if self.available else None


class FakeStore:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.kept: dict[str, dict[str, StoredPiece]] = {}

    def ids(self, collection: str) -> set[str] | None:
        return set(self.kept.get(collection, {})) if self.available else None

    def save(
        self, collection: str, pieces: Sequence[StoredPiece], vectors: Sequence[list[float]]
    ) -> bool:
        self.kept.setdefault(collection, {}).update({p.id: p for p in pieces})
        return self.available

    def delete(self, collection: str, ids: Sequence[str]) -> bool:
        for i in ids:
            self.kept[collection].pop(i)
        return True

    def search(self, collection: str, vector: list[float], limit: int) -> list[Hit] | None:
        pieces = list(self.kept.get(collection, {}).values())
        return [Hit(score=0.9 - 0.1 * k, piece=p) for k, p in enumerate(pieces[:limit])]


def scan(*facts: DocumentSection) -> list[ProjectScan]:
    code = ModuleDeclared(name="Billing", evidence=Evidence(file="b/x.cs", line=1, snippet=""))
    return [ProjectScan("b", (code, *facts))]


def test_only_new_pieces_are_embedded_and_vanished_ones_removed() -> None:
    embedder, store = FakeEmbedder(), FakeStore()
    first = index_documents(scan(section("Issues invoices"), section("Runs nightly", 5)),
                            "exodus-b", embedder, store)  # fmt: skip
    assert (first.pieces, first.embedded, first.removed) == (2, 2, 0)
    second = index_documents(scan(section("Issues invoices"), section("Runs hourly", 5)),
                             "exodus-b", embedder, store)  # fmt: skip
    assert (second.pieces, second.embedded, second.removed) == (2, 1, 1)
    assert embedder.calls[-1] == ["Runs hourly"]
    kept = sorted((p.text, p.source, p.title) for p in store.kept["exodus-b"].values())
    assert kept == [("Issues invoices", "b/README.md:1", "Billing"),
                    ("Runs hourly", "b/README.md:5", "Billing")]  # fmt: skip


def test_unavailable_store_or_model_is_reported_not_raised() -> None:
    assert not index_documents(scan(section("x")), "c", FakeEmbedder(), FakeStore(False)).available
    assert not index_documents(scan(section("x")), "c", FakeEmbedder(False), FakeStore()).available
    nothing = index_documents(scan(), "c", FakeEmbedder(), FakeStore())
    assert nothing.available and nothing.pieces == 0


def test_empty_document_set_removes_previous_indexed_content() -> None:
    store = FakeStore()
    embedder = FakeEmbedder()
    index_documents(scan(section("DB_PASSWORD=audit-canary-123")), "c", embedder, store)
    result = index_documents(scan(), "c", embedder, store)
    assert result.available and result.removed == 1
    assert store.kept["c"] == {}


def test_retriever_embeds_the_question_and_keeps_close_enough_pieces() -> None:
    embedder, store = FakeEmbedder(), FakeStore()
    index_documents(scan(section("a" * 30), section("b" * 30, 2), section("c" * 30, 3)),
                    "exodus-b", embedder, store)  # fmt: skip
    retriever = DocumentRetriever(embedder, store, "exodus-b", min_score=0.75)
    hits = retriever.search("what does it do?", limit=5)
    assert [round(h.score, 2) for h in hits] == [0.9, 0.8]  # 0.7 is below min_score
    assert embedder.calls[-1] == ["what does it do?"]
    assert DocumentRetriever(FakeEmbedder(False), store, "exodus-b").search("q") == []


def test_a_text_repeated_in_several_files_is_retrieved_once() -> None:
    embedder, store = FakeEmbedder(), FakeStore()
    same = "What is Pacco? Pacco is an open source project."
    index_documents(scan(section(same), section(same, 2), section("Pricing rules apply", 3)),
                    "exodus-b", embedder, store)  # fmt: skip
    hits = DocumentRetriever(embedder, store, "exodus-b", min_score=0.0).search("q", limit=5)
    assert [h.piece.text for h in hits] == [same, "Pricing rules apply"]
