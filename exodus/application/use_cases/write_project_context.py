"""Infer, per system, what the code cannot state: why the system exists, its goals, the
principles its code shows, the assumptions it relies on and its vocabulary.

The model gets numbered facts extracted from the graph (F1, F2, ...) and, when a retriever is
given (the RAG example), the pieces of the legacy's written documentation closest to a few fixed
questions (D1, D2, ...). A principle must cite a fact or piece it was given; a glossary term must
appear in them. Anything else is dropped. The retrieval is returned as a trace, to see what the
search brought for each question.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from exodus.application.ports import (
    Hit,
    Language,
    ProjectDraft,
    ProjectRequest,
    ProjectWriter,
    Retriever,
)
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import GlossaryTerm, InferredItem, Node, NodeKind, ProjectContext, RelKind
from exodus.domain.views import entry_points

Progress = Callable[[str], None] | None
MAX_ENTRY_POINTS = 8  # per container: enough to show what it does, not a catalog
MAX_OBJECTS = 10  # tables/collections per data store
MAX_DOCUMENT_CHARS = 6_000  # retrieved documentation sent to the model (context is limited)
QUESTIONS = {  # searched in the documents' language: similarity drops across languages
    Language.PT_BR: (
        "Qual problema de negócio o sistema resolve e para quem?",
        "Quais são os objetivos e as funcionalidades principais do sistema?",
        "Termos, siglas e conceitos do domínio de negócio",
        "Premissas, restrições e requisitos de ambiente",
        "Decisões e padrões de arquitetura adotados",
    ),
    Language.EN: (
        "What business problem does the system solve, and for whom?",
        "What are the main goals and features of the system?",
        "Business domain terms, acronyms and concepts",
        "Assumptions, constraints and environment requirements",
        "Architecture decisions and patterns adopted",
    ),
}


@dataclass(frozen=True)
class RetrievalTrace:
    system: str
    question: str
    hits: tuple[Hit, ...]


def write_project_context(
    graph: ArchitectureGraph,
    writer: ProjectWriter | None,
    progress: Progress = None,
    thinking: Progress = None,
    retriever: Retriever | None = None,
    language: Language = Language.PT_BR,
) -> list[RetrievalTrace]:
    """Infer the context of every system into the graph; return what retrieval found."""
    traces: list[RetrievalTrace] = []
    if writer is None:
        return traces
    for system in graph.nodes(NodeKind.SYSTEM):
        facts = _facts(graph, system)
        if not facts:
            continue
        found = [
            RetrievalTrace(system.name, q, tuple(retriever.search(q))) for q in QUESTIONS[language]
        ] if retriever else []  # fmt: skip
        traces += found
        pieces = _selected(found)
        numbered = tuple(f"F{number}: {fact}" for number, fact in enumerate(facts, start=1))
        documents = tuple(
            f"D{n}: [{h.piece.title} — {h.piece.source}] {' '.join(h.piece.text.split())}"
            for n, h in enumerate(pieces, start=1)
        )
        request = ProjectRequest(system=system.name, facts=numbered, documents=documents)
        draft = writer.draft(request, progress, thinking)
        if draft is not None:
            graph.set_project_context(_checked(system, draft, facts, pieces))
    return traces


def _selected(traces: list[RetrievalTrace]) -> list[Hit]:
    """The best pieces over all questions, each once, within MAX_DOCUMENT_CHARS."""
    best: dict[str, Hit] = {}
    for trace in traces:
        for hit in trace.hits:
            if hit.piece.id not in best or hit.score > best[hit.piece.id].score:
                best[hit.piece.id] = hit
    selected: list[Hit] = []
    budget = MAX_DOCUMENT_CHARS
    for hit in sorted(best.values(), key=lambda h: -h.score):
        if len(hit.piece.text) <= budget:
            selected.append(hit)
            budget -= len(hit.piece.text)
    return selected


def _facts(graph: ArchitectureGraph, system: Node) -> list[str]:
    facts: list[str] = []
    if system.description:
        facts.append(f"system description: {system.description.text}")
    containers = graph.children(system.id, NodeKind.CONTAINER)
    ids = {c.id for c in containers}
    for c in containers:
        runtime = " / ".join(
            v for v in (c.attributes.get("language"), c.attributes.get("framework")) if v
        )
        facts.append(f"container {c.name}: {runtime or 'unknown runtime'}")
        if c.description:
            facts.append(f"what {c.name} does: {c.description.text}")
        entries = [f"{e.kind} {e.name}" for e in entry_points(c)][:MAX_ENTRY_POINTS]
        if entries:
            facts.append(f"entry points of {c.name}: {', '.join(entries)}")
        components = [n.name for n in graph.children(c.id, NodeKind.COMPONENT)]
        if components:
            facts.append(f"components of {c.name}: {', '.join(components)}")
    messages = sorted(
        {
            part.split(" (")[0].strip()
            for r in graph.relationships()
            if r.kind in (RelKind.PUBLISHES, RelKind.CONSUMES)
            and (source := graph.ancestor(r.source_id, NodeKind.CONTAINER)) is not None
            and source.id in ids
            for part in r.label.split(", ")
            if part != r.kind.value  # a queue link names its direction, not a message
        }
    )
    if messages:
        facts.append(f"messages: {', '.join(messages)}")
    for use_case in graph.use_cases():
        if use_case.container_id in ids:
            facts.append(f"use case: {use_case.title}")
    for store in _used(graph, ids, NodeKind.DATA_STORE):
        objects = [
            k.split(":", 1)[1] for k in store.attributes if k.startswith(("table:", "collection:"))
        ][:MAX_OBJECTS]
        engine = store.attributes.get("engine", "unknown")
        facts.append(f"data {store.name} ({engine}): {', '.join(objects) or 'no tables found'}")
    externals = [n.name for n in _used(graph, ids, NodeKind.EXTERNAL_SYSTEM)]
    if externals:
        facts.append(f"external systems called: {', '.join(externals)}")
    platform = [n.name for n in _used(graph, ids, NodeKind.PLATFORM)]
    if platform:
        facts.append(f"platform services: {', '.join(platform)}")
    return facts


def _used(graph: ArchitectureGraph, ids: set[str], kind: NodeKind) -> list[Node]:
    found = {
        r.target_id
        for r in graph.relationships()
        if (c := graph.ancestor(r.source_id, NodeKind.CONTAINER)) is not None
        and c.id in ids
        and graph.node(r.target_id).kind is kind
    }
    return sorted((graph.node(i) for i in found), key=lambda n: n.name)


def _checked(
    system: Node, draft: ProjectDraft, facts: list[str], pieces: list[Hit] | None = None
) -> ProjectContext:
    pieces = pieces or []
    bases = {f"F{n}": fact for n, fact in enumerate(facts, start=1)}
    bases |= {f"D{n}": f"{h.piece.source} ({h.piece.title})" for n, h in enumerate(pieces, 1)}
    text = "\n".join([*facts, *(h.piece.text for h in pieces)]).lower()
    return ProjectContext(
        system_id=system.id,
        problem=draft.problem.strip(),
        goals=tuple(g.strip() for g in draft.goals if g.strip()),
        principles=tuple(
            InferredItem(text=principle.strip(), basis=bases[ref])
            for principle, raw in draft.principles
            if principle.strip() and (ref := _ref(raw)) in bases
        ),
        assumptions=tuple(a.strip() for a in draft.assumptions if a.strip()),
        glossary=tuple(
            GlossaryTerm(term=term.strip(), meaning=meaning.strip())
            for term, meaning in draft.glossary
            if term.strip() and meaning.strip() and term.strip().lower() in text
        ),
        confidence=min(1.0, max(0.0, draft.confidence)),
        sources=tuple(h.piece.source for h in pieces),
    )


def _ref(raw: str) -> str:
    """ "F3", "f3", "D 2" -> "F3", "D2"; anything else -> ""."""
    found = re.fullmatch(r"\s*([FDfd])\s*(\d+)\s*", raw)
    return f"{found.group(1).upper()}{found.group(2)}" if found else ""
