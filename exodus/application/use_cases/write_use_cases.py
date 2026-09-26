"""Draft a use case for each core entry point of every system with an optional model.

The model only reads the entry point's file and the files of the classes it names in the same
system (no call graph yet). Its answer is checked here: a step must cite a line it was given,
and it may only touch elements its container uses.
"""

import re
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath

from exodus.application.ports import (
    FileSource,
    SourceExcerpt,
    SourceFile,
    UseCaseDraft,
    UseCaseRequest,
    UseCaseWriter,
)
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Node, NodeKind, UseCase, UseCaseStep
from exodus.domain.views import EntryPointRef, core_entry_points

MAX_FILES = 5
MAX_SOURCE_CHARS = 12_000
CONTEXT_BEFORE = 10  # lines kept above the entry point when its file is cut


def write_use_cases(
    graph: ArchitectureGraph,
    roots: Sequence[Path],
    file_source: FileSource,
    writer: UseCaseWriter | None,
    progress: Callable[[str], None] | None = None,
    thinking: Callable[[str], None] | None = None,
    max_chars: int = MAX_SOURCE_CHARS,
) -> ArchitectureGraph:
    if writer is None:
        return graph
    read = _reader(roots, file_source)
    for system in graph.nodes(NodeKind.SYSTEM):
        for entry in core_entry_points(graph, system):
            text = read(entry.file)
            if text is None:
                continue
            sources = _sources(graph, system, entry, text, read, max_chars)
            candidates = _candidates(graph, entry.container_id)
            request = UseCaseRequest(
                entry=entry,
                container=graph.node(entry.container_id).name,
                sources=sources,
                candidates=tuple(sorted(candidates)),
            )
            draft = writer.draft(request, progress, thinking)
            use_case = (
                _checked(entry, text, draft, sources, candidates) if draft is not None else None
            )
            if use_case is not None:
                graph.add_use_case(use_case)
    return graph


def _reader(roots: Sequence[Path], file_source: FileSource) -> Callable[[str], str | None]:
    """Read a file by its evidence path ('<root name>/...'); None when it cannot be read."""
    by_name = {root.name: root for root in roots}

    def read(file: str) -> str | None:
        path = PurePosixPath(file)
        root = by_name.get(path.parts[0])
        if root is None:
            return None
        try:
            return file_source.read_text(root, path)
        except OSError:
            return None

    return read


def _sources(
    graph: ArchitectureGraph,
    system: Node,
    entry: EntryPointRef,
    text: str,
    read: Callable[[str], str | None],
    max_chars: int,
) -> tuple[SourceExcerpt, ...]:
    """The entry point's file (cut around it when too long), then the files of the classes it
    names, in order of first mention, while they fit whole in the budget."""
    lines = text.splitlines()
    first = max(1, entry.line - CONTEXT_BEFORE) if len(text) > max_chars else 1
    kept = _fitting(lines[first - 1 :], max_chars)
    excerpts = [SourceExcerpt(path=entry.file, first_line=first, lines=kept)]
    budget = max_chars - _size(kept)
    for file in _referenced_files(graph, system, text):
        if len(excerpts) == MAX_FILES:
            break
        referenced = read(file) if file != entry.file else None
        if referenced is None or len(referenced) > budget:
            continue
        excerpts.append(
            SourceExcerpt(path=file, first_line=1, lines=tuple(referenced.splitlines()))
        )
        budget -= len(referenced)
    return tuple(excerpts)


def _fitting(lines: list[str], max_chars: int) -> tuple[str, ...]:
    kept: list[str] = []
    for line in lines:
        if _size((*kept, line)) > max_chars:
            break
        kept.append(line)
    return tuple(kept)


def _size(lines: Sequence[str]) -> int:
    return sum(len(line) + 1 for line in lines)


def _referenced_files(graph: ArchitectureGraph, system: Node, text: str) -> list[str]:
    first_mention: dict[str, int] = {}
    for container in graph.children(system.id, NodeKind.CONTAINER):
        for component in graph.children(container.id, NodeKind.COMPONENT):
            for key, file in component.attributes.items():
                if not key.startswith("class:"):
                    continue
                found = re.search(rf"\b{re.escape(key.removeprefix('class:'))}\b", text)
                if found and found.start() < first_mention.get(file, len(text)):
                    first_mention[file] = found.start()
    return sorted(first_mention, key=lambda file: first_mention[file])


def _candidates(graph: ArchitectureGraph, container_id: str) -> dict[str, str]:
    """Names (to ids) of the elements the container, or one of its components, uses: the
    targets of its relationships, except platform services (discovery, tracing, ...)."""

    def top(node_id: str) -> Node:
        return graph.ancestor(node_id, NodeKind.CONTAINER) or graph.node(node_id)

    found: dict[str, str] = {}
    for r in graph.relationships():
        source, target = top(r.source_id), top(r.target_id)
        if source.id == container_id != target.id and target.kind is not NodeKind.PLATFORM:
            found[target.name] = target.id
    return found


def _checked(
    entry: EntryPointRef,
    text: str,
    draft: UseCaseDraft,
    sources: tuple[SourceExcerpt, ...],
    candidates: dict[str, str],
) -> UseCase | None:
    """The use case with only the steps citing a line the model was given; None if none does."""
    by_path = {source.path: source for source in sources}
    steps = tuple(
        UseCaseStep(text=step.text.strip(), evidence=by_path[step.file].evidence(step.line))
        for step in draft.steps
        if step.text.strip() and step.file in by_path and by_path[step.file].has(step.line)
    )
    if not steps:
        return None
    return UseCase(
        container_id=entry.container_id,
        trigger_kind=entry.kind,
        trigger=entry.name,
        entry=SourceFile(PurePosixPath(entry.file), text).evidence(entry.line),
        title=draft.title.strip() or f"{entry.kind} {entry.name}",
        steps=steps,
        touches=tuple(dict.fromkeys(candidates[n] for n in draft.touches if n in candidates)),
        confidence=min(1.0, max(0.0, draft.confidence)),
    )
