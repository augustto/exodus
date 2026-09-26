"""Render the deterministic migration-risk assessment as Markdown."""

from exodus.application.ports import Document
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import NodeKind
from exodus.domain.risks import Risk, assess_risks
from exodus.infrastructure.rendering.common import evidence_summary


class RisksRenderer:
    def render(self, graph: ArchitectureGraph) -> list[Document]:
        risks = assess_risks(graph)
        lines = [
            "# Exodus — Migration risks",
            "",
            "> Generated deterministically from source code and configuration. "
            "Evidence is `file:line`, relative to the parent of each scanned folder.",
            "",
            "## Summary",
            "",
            f"{len(risks)} risk(s): "
            + ", ".join(
                f"{sum(r.severity.value == severity for r in risks)} {severity}"
                for severity in ("high", "medium", "low")
            ),
            "",
        ]
        for system in graph.nodes(NodeKind.SYSTEM):
            system_risks = [r for r in risks if _belongs_to(graph, r, system.id)]
            if system_risks:
                lines += [f"## System: {system.name}", "", *_table(graph, system_risks)]
        shared = [r for r in risks if r.container_id is None]
        if shared:
            lines += ["## Cross-system", "", *_table(graph, shared)]
        if not risks:
            lines += ["No deterministic risks were detected.", ""]
        return [Document(name="risks.md", content="\n".join(lines))]


def _belongs_to(graph: ArchitectureGraph, risk: Risk, system_id: str) -> bool:
    if risk.container_id is None:
        return False
    system = graph.ancestor(risk.container_id, NodeKind.SYSTEM)
    return system is not None and system.id == system_id


def _table(graph: ArchitectureGraph, risks: list[Risk]) -> list[str]:
    lines = ["| Severity | Container | Risk | Detail | Evidence |", "|---|---|---|---|---|"]
    for risk in risks:
        container = (
            graph.node(risk.container_id).name if risk.container_id else "all affected systems"
        )
        evidence = evidence_summary(risk.evidence, 3)
        lines.append(
            f"| {risk.severity} | {container} | {risk.title} | {risk.detail} | `{evidence}` |"
        )
    return [*lines, ""]
