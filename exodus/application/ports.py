"""Ports: what the use cases need from the outside world. Adapters live in infrastructure."""

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import Protocol

from exodus.domain.facts import Fact
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence
from exodus.domain.refactor import PieceType
from exodus.domain.views import EntryPointRef

SNIPPET_MAX = 200
_SECRET_LINE = re.compile(
    r"(?<!\w)[\w.-]*(?:api[_-]?key|client[_-]?secret|access[_-]?key|private[_-]?key|"
    r"key|secret|password|passwd|pwd|token|authorization|credential)[\w.-]*"
    r"[\"']?\s*[=:]|"
    r"\bBearer\s+\S+|://[^\s/@:]+:[^\s/@]+@",
    re.IGNORECASE,
)


def redact_sensitive_line(line: str) -> str:
    """Remove a whole line when it appears to contain a credential assignment or URL."""
    return "[REDACTED]" if _SECRET_LINE.search(line) else line


def _evidence_snippet(line: str) -> str:
    """Keep a source location without copying likely credentials into generated artifacts."""
    return redact_sensitive_line(line.strip())[:SNIPPET_MAX]


class Language(StrEnum):
    """Language of the documents written for people (report, documentation, AI texts)."""

    PT_BR = "pt-br"
    EN = "en"


@dataclass(frozen=True)
class SourceFile:
    """A file handed to extractors. path is '<root name>/<relative path>' so evidence is unique
    across the scanned roots."""

    path: PurePosixPath
    text: str

    @cached_property
    def lines(self) -> list[str]:
        return self.text.splitlines()

    def evidence(self, line: int) -> Evidence:
        snippet = _evidence_snippet(self.lines[line - 1]) if line <= len(self.lines) else ""
        return Evidence(file=str(self.path), line=line, snippet=snippet)

    def line_at(self, offset: int) -> int:
        """1-based line number of a character offset in text."""
        return self.text.count("\n", 0, offset) + 1


class FactExtractor(Protocol):
    """Reads one kind of file (source code or config) and emits facts."""

    def matches(self, path: PurePosixPath) -> bool: ...

    def extract(self, file: SourceFile) -> Iterable[Fact]: ...


class FileSource(Protocol):
    def iter_paths(self, root: Path) -> Iterable[PurePosixPath]:
        """Relative paths ('<root name>/...') of candidate files under root."""
        ...

    def read_text(self, root: Path, path: PurePosixPath) -> str: ...


class GraphRepository(Protocol):
    def save(self, graph: ArchitectureGraph) -> None: ...

    def load(self) -> ArchitectureGraph: ...


@dataclass(frozen=True)
class Document:
    """A generated output file: name is relative to the output directory."""

    name: str
    content: str


class DocumentRenderer(Protocol):
    def render(self, graph: ArchitectureGraph) -> list[Document]: ...


class Enricher(Protocol):
    """Optionally adds clearly-marked inferences to an extracted graph."""

    def enrich(
        self,
        graph: ArchitectureGraph,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> ArchitectureGraph: ...


@dataclass(frozen=True)
class SourceExcerpt:
    """Consecutive lines of a file, from first_line on, handed to a model to read."""

    path: str
    first_line: int
    lines: tuple[str, ...]

    def has(self, line: int) -> bool:
        return self.first_line <= line < self.first_line + len(self.lines)

    def evidence(self, line: int) -> Evidence:
        snippet = _evidence_snippet(self.lines[line - self.first_line])
        return Evidence(file=self.path, line=line, snippet=snippet)


@dataclass(frozen=True)
class UseCaseRequest:
    """What a model gets to describe one entry point: the code it may cite and the names of the
    elements the container uses (the only ones it may say the use case touches)."""

    entry: EntryPointRef
    container: str
    sources: tuple[SourceExcerpt, ...]
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class DraftStep:
    text: str
    file: str
    line: int


@dataclass(frozen=True)
class UseCaseDraft:
    """A model's answer, still unchecked: citations and touched names are validated later."""

    title: str
    steps: tuple[DraftStep, ...]
    touches: tuple[str, ...]
    confidence: float


class UseCaseWriter(Protocol):
    """Drafts a use case from the code of an entry point; None when no answer is available."""

    def draft(
        self,
        request: UseCaseRequest,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> UseCaseDraft | None: ...


@dataclass(frozen=True)
class PieceRequest:
    """One element to place on AWS: what was extracted about it and the options it may take."""

    name: str
    piece: PieceType
    facts: tuple[str, ...]
    replatform: str  # the fast-path target, for reference
    priorities: tuple[str, ...]


@dataclass(frozen=True)
class PieceAnswer:
    option_id: str
    justification: str
    confidence: float


@dataclass(frozen=True)
class StructuralRequest:
    """Decisions that need the whole system: merging services, splitting shared databases."""

    system: str
    merges: tuple[tuple[str, str], ...]  # (service, into) candidates, by name
    shared: tuple[tuple[str, tuple[str, ...]], ...]  # (database, its users), by name
    shared_options: PieceType
    facts: tuple[str, ...]
    priorities: tuple[str, ...]


@dataclass(frozen=True)
class StructuralAnswer:
    merges: tuple[tuple[str, str, str], ...]  # (service, into, justification), by name
    shared: tuple[tuple[str, str, str], ...]  # (database, option id, justification), by name


class RefactorAdvisor(Protocol):
    """Proposes the refactor: chooses among catalog options; None when it has no answer."""

    def structure(
        self,
        request: StructuralRequest,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> StructuralAnswer | None: ...

    def choose(
        self,
        request: PieceRequest,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> PieceAnswer | None: ...


@dataclass(frozen=True)
class ProjectRequest:
    """What a model gets to infer a system's context: numbered facts (F1, F2, ...)."""

    system: str
    facts: tuple[str, ...]
    documents: tuple[str, ...] = ()  # retrieved pieces of written documentation: D1, D2, ...


@dataclass(frozen=True)
class ProjectDraft:
    """A model's answer, still unchecked: principles cite fact numbers, terms must be in facts."""

    problem: str
    goals: tuple[str, ...]
    principles: tuple[tuple[str, str], ...]  # (principle, "F<n>" fact or "D<n>" document)
    assumptions: tuple[str, ...]
    glossary: tuple[tuple[str, str], ...]  # (term, meaning)
    confidence: float


class ProjectWriter(Protocol):
    """Infers why a system exists, its goals, principles, assumptions and vocabulary."""

    def draft(
        self,
        request: ProjectRequest,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> ProjectDraft | None: ...


@dataclass(frozen=True)
class StoredPiece:
    """A piece of written documentation as kept in the vector store."""

    id: str
    title: str
    text: str
    source: str  # file:line


@dataclass(frozen=True)
class Hit:
    score: float  # similarity to the question (higher is closer)
    piece: StoredPiece


class Retriever(Protocol):
    """Finds the pieces of written documentation closest to a question."""

    def search(self, question: str, limit: int = 5) -> list[Hit]: ...


class EmbeddingModel(Protocol):
    """Turns texts into vectors; None when the model is unavailable."""

    def embed(self, texts: Sequence[str]) -> list[list[float]] | None: ...


class VectorStore(Protocol):
    """Keeps pieces and their vectors, and finds the closest to a vector. Every method returns
    None (or False) when the store is unavailable."""

    def ids(self, collection: str) -> set[str] | None:
        """Ids kept in the collection (empty when it does not exist yet)."""
        ...

    def save(
        self, collection: str, pieces: Sequence[StoredPiece], vectors: Sequence[list[float]]
    ) -> bool:
        """Create the collection if needed and add or replace these pieces."""
        ...

    def delete(self, collection: str, ids: Sequence[str]) -> bool: ...

    def search(self, collection: str, vector: list[float], limit: int) -> list[Hit] | None: ...
