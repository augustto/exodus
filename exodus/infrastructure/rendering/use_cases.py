"""Render the optional inferred use cases of each system's core entry points."""

from exodus.application.ports import Document
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import NodeKind
from exodus.domain.views import CORE_ENTRY_POINTS, entry_points


class UseCasesRenderer:
    def render(self, graph: ArchitectureGraph) -> list[Document]:
        lines = [
            "# Exodus — Use cases",
            "",
            f"> Up to {CORE_ENTRY_POINTS} main entry points per system, *inferred* by AI from "
            "their code; every step cites the line it was read from. The full list of entry "
            "points is in inventory.md.",
            "",
        ]
        header = len(lines)
        for system in graph.nodes(NodeKind.SYSTEM):
            containers = graph.children(system.id, NodeKind.CONTAINER)
            total = sum(len(entry_points(c)) for c in containers)
            if not total:
                continue
            ids = {c.id for c in containers}
            use_cases = [u for u in graph.use_cases() if u.container_id in ids]
            lines += [f"## {system.name}", ""]
            lines += [f"{len(use_cases)} use case(s) out of {total} entry point(s).", ""]
            for use_case in use_cases:
                touched = ", ".join(graph.node(node_id).name for node_id in use_case.touches)
                lines += [
                    f"### {use_case.title}",
                    "",
                    f"- **Trigger:** {use_case.trigger_kind} `{use_case.trigger}` — "
                    f"`{use_case.entry}`",
                    f"- **Container:** {graph.node(use_case.container_id).name}",
                    f"- *inferred* ({use_case.confidence:.0%})",
                ]
                if touched:
                    lines.append(f"- **Touches:** {touched}")
                lines.append("")
                lines += [
                    f"{number}. {step.text} — `{step.evidence}`"
                    for number, step in enumerate(use_case.steps, start=1)
                ]
                lines.append("")
            if not use_cases:
                lines += ["No use case inferred (Ollama unavailable).", ""]
        if len(lines) == header:
            lines += ["No entry points found.", ""]
        return [Document(name="use-cases.md", content="\n".join(lines))]
