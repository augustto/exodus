"""Render the deterministic migration recommendations (7R, AWS targets, waves) as Markdown."""

from exodus.application.ports import Document
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.migration import ContainerPlan, MigrationPlan, Path, Strategy, plan_migration
from exodus.domain.model import NodeKind
from exodus.infrastructure.rendering.common import evidence_summary

AWS_STRATEGIES = (
    "https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/"
    "migration-strategies.html"
)
_LEGEND = [
    ("Retire", "Decommission or archive", "Only as a *Retire?* candidate to confirm"),
    ("Retain", "Keep where it is for now", "No: a business or compliance decision"),
    ("Rehost", "Lift and shift to EC2, no code change", "Yes: runtime cannot run in a container"),
    ("Relocate", "Move a whole VMware environment", "No: not visible in source code"),
    ("Repurchase", "Replace with a SaaS product", "No: depends on products available"),
    ("Replatform", "Managed services / containers, little code change", "Yes"),
    ("Refactor", "Re-architect or rewrite for the cloud", "Yes: modern path"),
]


class MigrationRenderer:
    def render(self, graph: ArchitectureGraph) -> list[Document]:
        plan = plan_migration(graph)
        lines = [
            "# Exodus — Migration recommendations",
            "",
            "> Generated deterministically by rules from source code and configuration (no AI). "
            "Each container has a fast path (Rehost/Replatform: reach AWS with minimal change) "
            "and a modern path (Refactor). AWS recommends moving first and modernizing after.",
            "",
            "Diagrams (after `render --to-be`): `to-be/replatform.drawio` (fast path) and "
            "`to-be/refactor.drawio` (architecture proposed by AI from the refactor catalog, "
            "prioritizing cost, security and performance; decisions in `to-be/adr/`).",
            "",
            *_summary(plan),
            *_containers(graph, plan),
            *_infrastructure(graph, plan),
            *_waves(graph, plan),
            *_legend(),
        ]
        return [Document(name="migration.md", content="\n".join(lines))]


def _summary(plan: MigrationPlan) -> list[str]:
    def count(paths: list[Path]) -> str:
        return ", ".join(
            f"{sum(p.strategy is s for p in paths)} {s}"
            for s in Strategy
            if any(p.strategy is s for p in paths)
        )

    fast = [c.fast for c in plan.containers]
    modern = [c.modern for c in plan.containers if c.modern]
    same = len(plan.containers) - len(modern)
    retire = sum(c.retire_candidate for c in plan.containers)
    lines = [
        "## Summary",
        "",
        f"- **Fast path:** {count(fast) or 'no containers'}",
        f"- **Modern path:** {count(modern) or 'nothing to rewrite'}"
        + (f", {same} already final" if modern and same else ""),
        f"- **Waves:** foundation + {len(plan.waves)}",
    ]
    if retire:
        lines.append(f"- **Retire candidates:** {retire}")
    return [*lines, ""]


def _containers(graph: ArchitectureGraph, plan: MigrationPlan) -> list[str]:
    if not plan.containers:
        return []
    lines = [
        "## Containers",
        "",
        "| Container | System | Fast path | Modern path | Notes | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for container_plan in plan.containers:
        container = graph.node(container_plan.container_id)
        system = graph.ancestor(container.id, NodeKind.SYSTEM)
        lines.append(
            f"| {container.name} | {system.name if system else ''} "
            f"| {_path(container_plan.fast)} "
            f"| {_path(container_plan.modern) if container_plan.modern else '= fast path'} "
            f"| {_notes(container_plan)} | `{evidence_summary(container.evidence, 1)}` |"
        )
    return [*lines, ""]


def _path(path: Path) -> str:
    reason = f" — {path.reason}" if path.reason else ""
    return f"**{path.strategy}** → {path.target}{reason}"


def _notes(plan: ContainerPlan) -> str:
    if plan.retire_candidate:
        return "*Retire?* no entry point or inbound call detected: confirm it is used"
    return ""


def _infrastructure(graph: ArchitectureGraph, plan: MigrationPlan) -> list[str]:
    if not plan.infrastructure:
        return []
    lines = [
        "## Infrastructure",
        "",
        "| Element | Type | Fast path | Modern path | Used by |",
        "|---|---|---|---|---|",
    ]
    for infra in plan.infrastructure:
        node = graph.node(infra.node_id)
        users = dict.fromkeys(
            graph.node(r.source_id).name for r in graph.relationships() if r.target_id == node.id
        )
        kind = node.technology or node.kind.value.replace("_", " ")
        lines.append(
            f"| {node.name} | {kind} | {infra.fast} | {infra.modern} | {', '.join(users)} |"
        )
    return [*lines, ""]


def _waves(graph: ArchitectureGraph, plan: MigrationPlan) -> list[str]:
    targets = {i.node_id: i.fast for i in plan.infrastructure}
    lines = ["## Waves", ""]
    if plan.foundation:
        lines += ["### Wave 0 — Foundation (platform services)", ""]
        lines += [f"- {graph.node(p).name} → {targets[p]}" for p in plan.foundation]
        lines.append("")
    for wave in plan.waves:
        lines += [f"### Wave {wave.number}", ""]
        for group in wave.groups:
            names = ", ".join(f"**{graph.node(c).name}**" for c in group.container_ids)
            data = [graph.node(i).name for i in (*group.store_ids, *group.queue_ids)]
            with_data = f" + {', '.join(data)}" if data else ""
            reasons = f" — {'; '.join(group.reasons)}" if group.reasons else ""
            lines.append(f"- {names}{with_data}{reasons}")
        lines.append("")
    return lines


def _legend() -> list[str]:
    lines = [
        f"## The 7R ([AWS migration strategies]({AWS_STRATEGIES}))",
        "",
        "| R | Meaning | Assigned by Exodus |",
        "|---|---|---|",
    ]
    lines += [f"| {r} | {meaning} | {assigned} |" for r, meaning, assigned in _LEGEND]
    return [*lines, ""]
