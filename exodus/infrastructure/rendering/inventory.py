"""inventory.md: human-readable inventory of everything found, each item with its evidence."""

from collections.abc import Iterable, Sequence

from exodus.application.ports import Document
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence, Node, NodeKind, RelKind
from exodus.domain.views import describe
from exodus.infrastructure.rendering.common import evidence_summary


def _cell(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def _ev(evidence: Sequence[Evidence], limit: int = 3) -> str:
    return f"`{evidence_summary(evidence, limit)}`" if evidence else ""


def _table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return [*lines, ""]


def _prefixed(node: Node, prefix: str) -> list[tuple[str, str]]:
    return [(k.removeprefix(prefix), v) for k, v in node.attributes.items() if k.startswith(prefix)]


DATA_OBJECT_LIMIT = 10
_DATA_OBJECTS = (("table", "Tables"), ("collection", "Collections"), ("procedure", "Procedures"))


def _data_objects(node: Node, prefix: str = "") -> list[str]:
    """One line per kind: the most cited names first (by files naming them), then +N more."""
    lines = []
    for kind, label in _DATA_OBJECTS:
        named = _prefixed(node, f"{prefix}{kind}:")
        if not named:
            continue
        ranked = sorted(
            named,
            key=lambda item: (-len({p.rpartition(":")[0] for p in item[1].split(", ")}), item[0]),
        )
        shown = ", ".join(name for name, _ in ranked[:DATA_OBJECT_LIMIT])
        hidden = len(ranked) - DATA_OBJECT_LIMIT
        more = f", +{hidden} more" if hidden > 0 else ""
        lines.append(f"- {label} ({len(ranked)}): {shown}{more}")
    return lines


class InventoryRenderer:
    def render(self, graph: ArchitectureGraph) -> list[Document]:
        lines = [
            "# Exodus — Inventory (AS-IS)",
            "",
            "> Generated deterministically from source code and configuration. "
            "Evidence is `file:line`, relative to the parent of each scanned folder.",
            "",
        ]
        lines += self._summary(graph)
        for system in graph.nodes(NodeKind.SYSTEM):
            lines += self._system(graph, system)
        lines += self._data_stores(graph)
        lines += self._queues(graph)
        lines += self._externals(graph)
        lines += self._platform(graph)
        lines += self._messaging(graph)
        lines += self._relationships(graph)
        lines += self._module_dependencies(graph)
        return [Document(name="inventory.md", content="\n".join(lines))]

    def _summary(self, graph: ArchitectureGraph) -> list[str]:
        kinds = [
            ("Systems", NodeKind.SYSTEM),
            ("Containers", NodeKind.CONTAINER),
            ("Components", NodeKind.COMPONENT),
            ("Data stores", NodeKind.DATA_STORE),
            ("Queues", NodeKind.QUEUE),
            ("External systems", NodeKind.EXTERNAL_SYSTEM),
            ("Platform services", NodeKind.PLATFORM),
        ]
        headers = [label for label, _ in kinds] + ["Relationships"]
        row = [str(len(graph.nodes(kind))) for _, kind in kinds]
        return ["## Summary", "", *_table(headers, [[*row, str(len(graph.relationships()))]])]

    def _system(self, graph: ArchitectureGraph, system: Node) -> list[str]:
        lines = [f"## System: {system.name}", ""]
        deployment = _prefixed(system, "compose:")
        if deployment:
            lines += ["**Deployment (docker-compose)**", ""]
            lines += _table(["Service", "Image"], deployment)
        for container in graph.children(system.id, NodeKind.CONTAINER):
            lines += [f"### Container: {container.name}", ""]
            lines += [f"- **Technology:** {container.technology or 'unknown'}"]
            if container.description:
                lines += [
                    "- **Description:** *inferred* "
                    f"({container.description.confidence:.0%}): {container.description.text}"
                ]
            if image := container.attributes.get("runtime-image"):
                lines += [f"- **Runtime image:** {image}"]
            for name, image in _prefixed(container, "deployed-as:"):
                lines += [f"- **Deployed as:** {name} ({image})"]
            lines += [f"- **Declared at:** {_ev(container.evidence[:1])}", ""]
            packages = _prefixed(container, "package:")
            if packages:
                lines += [f"**Packages ({len(packages)})**", ""]
                lines += _table(["Package", "Version"], packages)
            endpoints = _prefixed(container, "endpoint:")
            if endpoints:
                lines += ["**Exposed endpoints**", ""]
                lines += _table(["Path", "Protocol"], endpoints)
            entry_points = _prefixed(container, "entry-point:")
            if entry_points:
                entry_rows = [(*key.split(":", 1), value) for key, value in entry_points]
                lines += ["**Entry points**", ""]
                lines += _table(["Type", "Route / name", "Evidence"], entry_rows)
            undetermined = _data_objects(container, "undetermined-")
            if undetermined:
                lines += ["**Data objects (database not determined)**", "", *undetermined, ""]
            unresolved = _prefixed(container, "unresolved-datasource:")
            if unresolved:
                lines += ["**Unrecognized data sources**", ""]
                lines += _table(["Name", "Source"], unresolved)
            components = graph.children(container.id, NodeKind.COMPONENT)
            if components:
                lines += ["**Components (namespaces / packages)**", ""]
                rows = [
                    (c.name, str(len(_prefixed(c, "class:"))), _ev(c.evidence[:1]))
                    for c in components
                ]
                lines += _table(["Name", "Classes", "Declared at"], rows)
        return lines

    def _data_stores(self, graph: ArchitectureGraph) -> list[str]:
        """Databases by server, each with its main tables/collections and procedures."""
        stores = graph.nodes(NodeKind.DATA_STORE)
        if not stores:
            return []
        lines = ["## Data stores", ""]
        servers = sorted({s.attributes.get("host", "") for s in stores})
        for server in servers:
            lines += [f"### Server `{server}`" if server else "### Server (unknown)", ""]
            for store in (s for s in stores if s.attributes.get("host", "") == server):
                users = ", ".join(self._users(graph, store.id)) or "—"
                lines.append(
                    f"- **{store.name}** ({store.technology or 'unknown'}) — used by {users}"
                    f" — {_ev(store.evidence)}"
                )
                lines += [f"  {line}" for line in _data_objects(store)]
            lines.append("")
        return lines

    def _queues(self, graph: ArchitectureGraph) -> list[str]:
        queues = graph.nodes(NodeKind.QUEUE)
        if not queues:
            return []
        rows = [
            (
                q.name,
                q.technology or "",
                ", ".join(self._users(graph, q.id, RelKind.PUBLISHES)),
                ", ".join(self._users(graph, q.id, RelKind.CONSUMES)),
                _ev(q.evidence),
            )
            for q in queues
        ]
        return [
            "## Queues",
            "",
            *_table(["Queue", "Technology", "Publishers", "Consumers", "Evidence"], rows),
        ]

    def _externals(self, graph: ArchitectureGraph) -> list[str]:
        externals = graph.nodes(NodeKind.EXTERNAL_SYSTEM)
        if not externals:
            return []
        rows = [
            (
                e.name,
                ", ".join(url for url, _ in _prefixed(e, "url:")),
                ", ".join(self._users(graph, e.id)),
                _ev(e.evidence),
            )
            for e in externals
        ]
        return [
            "## External systems",
            "",
            *_table(["Host", "Origins", "Called by", "Evidence"], rows),
        ]

    def _platform(self, graph: ArchitectureGraph) -> list[str]:
        services = graph.nodes(NodeKind.PLATFORM)
        if not services:
            return []
        rows = [(p.name, ", ".join(self._users(graph, p.id)), _ev(p.evidence)) for p in services]
        return ["## Platform services", "", *_table(["Service", "Used by", "Evidence"], rows)]

    def _messaging(self, graph: ArchitectureGraph) -> list[str]:
        """Messages sent from one container to another through a broker."""
        rows = [
            (graph.node(r.source_id).name, graph.node(r.target_id).name, r.label, _ev(r.evidence))
            for r in graph.relationships(RelKind.PUBLISHES)
            if graph.node(r.target_id).kind is NodeKind.CONTAINER
        ]
        if not rows:
            return []
        return ["## Messaging", "", *_table(["From", "To", "Messages", "Evidence"], rows)]

    def _relationships(self, graph: ArchitectureGraph) -> list[str]:
        rows = []
        for r in graph.relationships():
            source, target = graph.node(r.source_id), graph.node(r.target_id)
            if NodeKind.COMPONENT in (source.kind, target.kind) or target.kind is NodeKind.PLATFORM:
                continue
            rows.append((source.name, target.name, describe(r), _ev(r.evidence)))
        if not rows:
            return []
        return ["## Relationships", "", *_table(["From", "To", "Relationship", "Evidence"], rows)]

    def _module_dependencies(self, graph: ArchitectureGraph) -> list[str]:
        rows = [
            (graph.node(r.source_id).name, graph.node(r.target_id).name, _ev(r.evidence))
            for r in graph.relationships(RelKind.DEPENDS_ON)
            if graph.node(r.source_id).kind is NodeKind.COMPONENT
        ]
        if not rows:
            return []
        return ["## Module dependencies", "", *_table(["Module", "Depends on", "Evidence"], rows)]

    @staticmethod
    def _users(graph: ArchitectureGraph, node_id: str, kind: RelKind | None = None) -> list[str]:
        return list(
            dict.fromkeys(
                graph.node(r.source_id).name
                for r in graph.relationships(kind)
                if r.target_id == node_id
            )
        )
