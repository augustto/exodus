"""ADR drafts for the refactor proposal: one per group of decisions (structure, then each
catalog category), built from the choices kept in the graph and the catalog notes. No model
call: the justifications are the ones inferred when the proposal was made."""

from exodus.application.ports import Document
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import RefactorChoice, RefactorPlan
from exodus.domain.refactor import Catalog, PieceType
from exodus.infrastructure.rendering.common import evidence_summary

_CATEGORIES = ("edge", "compute", "data", "integration", "platform", "security", "observability")
NOT_INFERRED = "No inferred choice: first catalog option"


class AdrRenderer:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def render(self, graph: ArchitectureGraph) -> list[Document]:
        plan = graph.refactor
        if plan is None:
            return []
        adrs: list[tuple[str, str, list[str]]] = []  # (slug, title, body)
        if plan.merges or plan.shared:
            adrs.append(("structure", "Structure of the refactor", self._structure(graph, plan)))
        for category in _CATEGORIES:
            choices = [c for c in plan.choices if self._category(c) == category]
            if choices:
                title = f"{category.capitalize()} on AWS"
                adrs.append((category, title, self._choices(graph, choices)))
        return [
            Document(
                name=f"to-be/adr/{number:03}-{slug}.md",
                content="\n".join([f"# ADR {number:03}: {title}", "", *self._header(), *body]),
            )
            for number, (slug, title, body) in enumerate(adrs, start=1)
        ]

    def _category(self, choice: RefactorChoice) -> str | None:
        piece = self.catalog.piece(choice.piece_type)
        return piece.category if piece else None

    def _header(self) -> list[str]:
        return [
            "- **Status:** Proposed — inferred by AI; review before accepting",
            f"- **Priorities:** {' → '.join(self.catalog.priorities)}",
            "",
        ]

    def _structure(self, graph: ArchitectureGraph, plan: RefactorPlan) -> list[str]:
        options = self.catalog.piece("shared-database")
        lines = ["## Decision", ""]
        lines += [
            f"- Merge **{graph.node(m.source_id).name}** into **{graph.node(m.into_id).name}**: "
            f"{m.justification}"
            for m in plan.merges
        ]
        for shared in plan.shared:
            chosen = options.option(shared.option_id) if options else None
            service = chosen.service if chosen else shared.option_id
            lines.append(
                f"- **{graph.node(shared.store_id).name}**: {service} — {shared.justification}"
            )
        lines += ["", "## Options considered", ""]
        lines += ["- Merge services that already move together, or keep them apart"]
        lines += _options(options) if options else []
        return [*lines, ""]

    def _choices(self, graph: ArchitectureGraph, choices: list[RefactorChoice]) -> list[str]:
        pieces = [p for p in self.catalog.piece_types if p.id in {c.piece_type for c in choices}]
        labels = {p.id: p.label for p in pieces}
        lines = ["## Context", ""]
        for c in choices:
            node = graph.node(c.node_id)
            lines.append(
                f"- **{node.name}** ({labels.get(c.piece_type, c.piece_type)}) — "
                f"`{evidence_summary(node.evidence, 1)}`"
            )
        lines += ["", "## Options considered", ""]
        for piece in pieces:
            lines += [f"**{piece.label}**", "", *_options(piece), ""]
        lines += ["## Decision", "", "| Element | Choice | Confidence | Justification |"]
        lines.append("|---|---|---|---|")
        for c in choices:
            confidence = f"{c.confidence:.0%}" if c.inferred else "default"
            why = c.justification if c.inferred else NOT_INFERRED
            lines.append(f"| {graph.node(c.node_id).name} | {c.service} | {confidence} | {why} |")
        lines += ["", "## Consequences", ""]
        for piece_id, option_id in dict.fromkeys((c.piece_type, c.option_id) for c in choices):
            found = self.catalog.piece(piece_id)
            option = found.option(option_id) if found else None
            if option:
                notes = f"{option.cost}; {option.security}; {option.performance}"
                lines.append(f"- **{option.service}:** {notes}")
        return [*lines, ""]


def _options(piece: PieceType) -> list[str]:
    return [f"- **{o.id}** — {o.service}: {o.when}" for o in piece.options]
