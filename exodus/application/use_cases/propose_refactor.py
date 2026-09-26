"""Propose the refactor TO-BE with an optional advisor (a model), in two steps.

1. Per system, the structural decisions that need the whole picture: which services merge
   (only services already moving in the same wave group) and what becomes of each database
   shared by several containers.
2. Per element, its AWS target among the options of its piece type in the catalog.

Every answer is checked against the catalog and the candidates: an unknown option, a merge that
was not a candidate or a merge chain is dropped, and the element keeps the first option of its
piece type, marked as not inferred. Without an advisor every element gets that default.
"""

from collections.abc import Callable

from exodus.application.ports import (
    PieceRequest,
    RefactorAdvisor,
    StructuralAnswer,
    StructuralRequest,
)
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.migration import plan_migration
from exodus.domain.model import (
    Merge,
    Node,
    NodeKind,
    RefactorChoice,
    RefactorPlan,
    SharedDataChoice,
)
from exodus.domain.refactor import (
    Catalog,
    PieceType,
    merge_candidates,
    piece_type,
    shared_databases,
)
from exodus.domain.risks import Risk, assess_risks

MERGE = "merge"
NOT_INFERRED = "Default option: no valid inferred choice (model unavailable or invalid answer)."

Progress = Callable[[str], None] | None


def propose_refactor(
    graph: ArchitectureGraph,
    catalog: Catalog,
    advisor: RefactorAdvisor | None,
    progress: Progress = None,
    thinking: Progress = None,
) -> ArchitectureGraph:
    merges: list[Merge] = []
    shared: list[SharedDataChoice] = []
    if advisor is not None:
        for system in graph.nodes(NodeKind.SYSTEM):
            request = _structural_request(graph, catalog, system)
            if request is None:
                continue
            answer = advisor.structure(request, progress, thinking)
            if answer is not None:
                found_merges, found_shared = _checked_structure(graph, catalog, system, answer)
                merges += found_merges
                shared += found_shared
    merged = {m.source_id for m in merges}
    context = _Context(graph)
    choices = [
        _choice(context, catalog, advisor, node, piece, progress, thinking)
        for node in graph.nodes()
        if node.id not in merged
        and (piece := catalog.piece(piece_type(graph, node) or "")) is not None
    ]
    graph.set_refactor(
        RefactorPlan(choices=tuple(choices), merges=tuple(merges), shared=tuple(shared))
    )
    return graph


class _Context:
    """What is computed once for every element: its extracted facts and replatform target."""

    def __init__(self, graph: ArchitectureGraph) -> None:
        self.graph = graph
        plan = plan_migration(graph)
        self.targets = {c.container_id: c.fast.target for c in plan.containers}
        self.targets |= {i.node_id: i.fast for i in plan.infrastructure}
        self.risks = assess_risks(graph)

    def facts(self, node: Node) -> list[str]:
        return _facts(self.graph, node, [r for r in self.risks if r.container_id == node.id])


def _in_system(graph: ArchitectureGraph, node_id: str, system: Node) -> bool:
    found = graph.ancestor(node_id, NodeKind.SYSTEM)
    return found is not None and found.id == system.id


def _structural_request(
    graph: ArchitectureGraph, catalog: Catalog, system: Node
) -> StructuralRequest | None:
    shared_options = catalog.piece("shared-database")
    names = {n.id: n.name for n in graph.nodes()}
    candidates = tuple(
        (names[a], names[b]) for a, b in merge_candidates(graph) if _in_system(graph, a, system)
    )
    shared = tuple(
        (names[store], tuple(names[u] for u in users))
        for store, users in shared_databases(graph).items()
        if any(_in_system(graph, u, system) for u in users)
    )
    if shared_options is None or not (candidates or shared):
        return None
    facts = tuple(
        f"{c.name}: {piece_type(graph, c)}; {'; '.join(_facts(graph, c, [])) or 'no facts'}"
        for c in graph.children(system.id, NodeKind.CONTAINER)
    )
    return StructuralRequest(
        system=system.name,
        merges=candidates,
        shared=shared,
        shared_options=shared_options,
        facts=facts,
        priorities=catalog.priorities,
    )


def _checked_structure(
    graph: ArchitectureGraph, catalog: Catalog, system: Node, answer: StructuralAnswer
) -> tuple[list[Merge], list[SharedDataChoice]]:
    ids = {n.name: n.id for n in graph.nodes() if _in_system(graph, n.id, system)}
    ids |= {graph.node(s).name: s for s in shared_databases(graph)}
    candidates = set(merge_candidates(graph))
    merges: list[Merge] = []
    for service, into, justification in answer.merges:
        pair = (ids.get(service, ""), ids.get(into, ""))
        involved = {i for m in merges for i in (m.source_id, m.into_id)}
        if pair in candidates and not {pair[0], pair[1]} & involved:  # no chains
            merges.append(Merge(source_id=pair[0], into_id=pair[1], justification=justification))
    options = catalog.piece("shared-database")
    shared = [
        SharedDataChoice(store_id=ids[database], option_id=option_id, justification=justification)
        for database, option_id, justification in answer.shared
        if database in ids
        and ids[database] in shared_databases(graph)
        and options is not None
        and options.option(option_id) is not None
    ]
    return merges, shared


def _choice(
    context: _Context,
    catalog: Catalog,
    advisor: RefactorAdvisor | None,
    node: Node,
    piece: PieceType,
    progress: Progress,
    thinking: Progress,
) -> RefactorChoice:
    options = piece.model_copy(update={"options": tuple(o for o in piece.options if o.id != MERGE)})
    if advisor is not None:
        request = PieceRequest(
            name=node.name,
            piece=options,
            facts=tuple(context.facts(node)),
            replatform=context.targets.get(node.id, ""),
            priorities=catalog.priorities,
        )
        answer = advisor.choose(request, progress, thinking)
        chosen = options.option(answer.option_id) if answer else None
        if answer is not None and chosen is not None:
            return RefactorChoice(
                node_id=node.id,
                piece_type=piece.id,
                option_id=chosen.id,
                service=chosen.service,
                justification=answer.justification.strip() or chosen.when,
                confidence=min(1.0, max(0.0, answer.confidence)),
            )
    default = options.options[0]
    return RefactorChoice(
        node_id=node.id,
        piece_type=piece.id,
        option_id=default.id,
        service=default.service,
        justification=NOT_INFERRED,
        confidence=0,
        inferred=False,
    )


def _facts(graph: ArchitectureGraph, node: Node, risks: list[Risk]) -> list[str]:
    """What was extracted about an element, in short lines, for the model to reason on."""
    facts = [f"{key}: {node.attributes[key]}" for key in ("language", "framework", "engine")
             if key in node.attributes]  # fmt: skip
    entries = sorted({k.split(":")[1] for k in node.attributes if k.startswith("entry-point:")})
    facts += [f"entry points: {', '.join(entries)}"] if entries else []
    technologies = [
        k.removeprefix("technology:") for k in node.attributes if k.startswith("technology:")
    ]
    facts += [f"legacy technologies: {', '.join(technologies)}"] if technologies else []
    tables = sum(k.startswith(("table:", "collection:")) for k in node.attributes)
    facts += [f"tables/collections: {tables}"] if tables else []
    facts += sorted({f"risk: {r.title} ({r.detail})" for r in risks})
    for r in graph.relationships():
        if r.source_id == node.id and graph.node(r.target_id).kind is not NodeKind.PLATFORM:
            facts.append(f"{r.kind.value} {graph.node(r.target_id).name}")
        elif r.target_id == node.id:
            facts.append(f"{r.kind.value} by {graph.node(r.source_id).name}")
    return list(dict.fromkeys(facts))
