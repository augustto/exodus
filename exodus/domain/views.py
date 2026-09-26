"""C4 views projected from the graph (pure). Renderers only format what these views contain.

- A data store or queue used by a single system belongs to that system (drawn inside it);
  one shared by several systems is drawn as its own element.
- Component-level relationships (imports) are not part of L1/L2 views.
- L3 (components) is drawn only for the core containers of each system (see `core_containers`).
- Use cases are written only for the core entry points of each system (`core_entry_points`).
  A relationship of the container is attributed to the component that owns the file of its
  evidence; one with no evidence in a component file is not drawn at L3.
- Relationships are rolled up to the elements visible in the view and deduplicated; two
  opposite ones with the same description become one, both ways.
- Platform services (discovery, secrets, tracing, logging, metrics, broker) are a group of the
  container view (L2), linked once to the boundary; context (L1) and component (L3) views leave
  them out. Caches (Redis) are details of the services using them: left out of every view.
- Container views keep synchronous and event relationships together.
"""

import re
from collections.abc import Callable, Iterable

from pydantic import Field

from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import (
    Entity,
    Evidence,
    Node,
    NodeKind,
    Relationship,
    RelKind,
    merge_evidence,
)

_INFRA = (NodeKind.DATA_STORE, NodeKind.QUEUE)
_MESSAGES = (RelKind.PUBLISHES, RelKind.CONSUMES)
CORE_LIMIT = 3
CORE_ENTRY_POINTS = 5
ENTRY_POINT_PREFIX = "entry-point:"
_ENTRY_KIND_ORDER = {
    "HTTP": 0, "SOAP": 0, "queue consumer": 1,
    "scheduled job": 2, "scheduled task": 2, "Windows service": 2, "CLI command": 3,
}  # fmt: skip


class ViewRelationship(Entity):
    source_id: str
    target_id: str
    description: str
    evidence: tuple[Evidence, ...]
    both_ways: bool = False


class EntryPointRef(Entity):
    """An entry point of a container, from its `entry-point:<kind>:<name>` = `file:line`
    attribute."""

    container_id: str
    kind: str
    name: str
    file: str
    line: int


class C4View(Entity):
    key: str
    title: str
    boundary: Node | None  # the system (container view) or container (component view) zoomed in
    inner: list[Node]  # elements drawn inside the boundary
    outer: list[Node]  # elements drawn outside it
    relationships: list[ViewRelationship]
    platform: list[Node] = Field(default_factory=list)  # used inside the boundary; a group
    platform_evidence: tuple[Evidence, ...] = ()  # of the single link between group and boundary


def describe(relationship: Relationship) -> str:
    label = relationship.label
    if relationship.kind is RelKind.DEPENDS_ON or label == relationship.kind.value:
        return label
    if relationship.kind in _MESSAGES:  # named by the messages themselves
        return label
    return f"{relationship.kind.value} ({label})"


def _hidden(node: Node) -> bool:
    """Left out of every view: caches (details of the services using them)."""
    return node.kind is NodeKind.DATA_STORE and node.attributes.get("engine") == "redis"


def owner_system(graph: ArchitectureGraph, node_id: str) -> str | None:
    """The only system whose containers use this data store/queue, or None if shared/unused."""
    systems = {
        system.id
        for r in graph.relationships()
        if r.target_id == node_id
        and (system := graph.ancestor(r.source_id, NodeKind.SYSTEM)) is not None
    }
    return systems.pop() if len(systems) == 1 else None


def system_context(graph: ArchitectureGraph) -> C4View:
    def place(node: Node) -> str | None:
        if _hidden(node):
            return None
        if node.kind in (NodeKind.CONTAINER, NodeKind.SYSTEM):
            system = graph.ancestor(node.id, NodeKind.SYSTEM)
            return system.id if system else None
        if node.kind in _INFRA:
            return owner_system(graph, node.id) or node.id
        if node.kind is NodeKind.EXTERNAL_SYSTEM:
            return node.id
        return None

    ids = _placed_ids(graph, place)
    return C4View(
        key="context",
        title="System Landscape (AS-IS)",
        boundary=None,
        inner=[],
        outer=[graph.node(i) for i in ids],
        relationships=_rolled_up(graph, place),
    )


def container_views(graph: ArchitectureGraph) -> list[C4View]:
    views: list[C4View] = []
    for system in graph.nodes(NodeKind.SYSTEM):
        whole = container_view(graph, system)
        views.append(whole)
    return views


def container_view(
    graph: ArchitectureGraph,
    system: Node,
    keep: Callable[[Relationship], bool] = lambda r: True,
) -> C4View:
    """The containers of a system, with the relationships `keep` accepts."""
    owners = {n.id: owner_system(graph, n.id) for n in graph.nodes() if n.kind in _INFRA}

    def place(node: Node) -> str | None:
        if _hidden(node):
            return None
        if node.kind is NodeKind.CONTAINER:
            if node.parent_id == system.id:
                return node.id
            return node.parent_id
        if node.kind in _INFRA:
            return node.id if owners[node.id] in (system.id, None) else owners[node.id]
        if node.kind in (NodeKind.SYSTEM, NodeKind.EXTERNAL_SYSTEM):
            return node.id
        return None

    inner_ids = {c.id for c in graph.children(system.id, NodeKind.CONTAINER)}
    inner_ids |= {i for i, owner in owners.items() if owner == system.id}
    relationships = [
        r
        for r in _rolled_up(graph, place, keep)
        if r.source_id in inner_ids or r.target_id in inner_ids
    ]
    connected = {i for r in relationships for i in (r.source_id, r.target_id)}
    ordered = _placed_ids(graph, place)
    own = {c.id for c in graph.children(system.id, NodeKind.CONTAINER)}
    uses = [
        r
        for r in graph.relationships()
        if r.source_id in own and graph.node(r.target_id).kind is NodeKind.PLATFORM
    ]
    services = {r.target_id: graph.node(r.target_id) for r in uses}
    platform = sorted(services.values(), key=lambda n: (n.name, n.id))
    return C4View(
        key=system.id.removeprefix("system:"),
        title=f"Containers of {system.name} (AS-IS)",
        boundary=system,
        inner=[graph.node(i) for i in ordered if i in inner_ids],
        outer=[graph.node(i) for i in ordered if i in connected - inner_ids],
        relationships=relationships,
        platform=platform,
        platform_evidence=tuple(e for r in uses for e in r.evidence),
    )


def core_containers(graph: ArchitectureGraph, system: Node, limit: int = CORE_LIMIT) -> list[Node]:
    """Containers of the system that have components, most central first: more distinct
    containers depending on it, then more relationships touching it, then more components, then
    name."""
    candidates = [c for c in graph.children(system.id, NodeKind.CONTAINER) if graph.children(c.id)]
    dependents: dict[str, set[str]] = {c.id: set() for c in candidates}
    degree = dict.fromkeys(dependents, 0)
    for r in graph.relationships():
        source, target = _container_of(graph, r.source_id), _container_of(graph, r.target_id)
        if source == target:
            continue
        if target in dependents:
            dependents[target].add(source)
            degree[target] += 1
        if source in degree:
            degree[source] += 1
    ranked = sorted(
        candidates,
        key=lambda c: (-len(dependents[c.id]), -degree[c.id], -len(graph.children(c.id)), c.name),
    )
    return ranked[:limit]


def entry_points(container: Node) -> list[EntryPointRef]:
    """Entry points of a container; ones without a file:line location are skipped."""
    found = []
    for key, location in container.attributes.items():
        if not key.startswith(ENTRY_POINT_PREFIX):
            continue
        kind, _, name = key.removeprefix(ENTRY_POINT_PREFIX).partition(":")
        file, _, line = location.rpartition(":")
        if file and line.isdigit() and int(line) >= 1:
            found.append(
                EntryPointRef(
                    container_id=container.id, kind=kind, name=name, file=file, line=int(line)
                )
            )
    return found


def core_entry_points(
    graph: ArchitectureGraph, system: Node, limit: int = CORE_ENTRY_POINTS
) -> list[EntryPointRef]:
    """Entry points of the system most worth a use case. Containers take turns, most central
    first, so the use cases cover the system; inside a container, first the entry points in
    more container-level relationships (data, calls, events) evidenced in their file or naming
    them, then HTTP/SOAP before consumers, jobs and commands, then name."""
    containers = graph.children(system.id, NodeKind.CONTAINER)
    core = [c.id for c in core_containers(graph, system, limit=len(containers))]
    by_file: dict[str, int] = {}
    by_container: dict[str, list[Relationship]] = {}
    for r in graph.relationships():
        if NodeKind.COMPONENT in (graph.node(r.source_id).kind, graph.node(r.target_id).kind):
            continue
        for file in {e.file for e in r.evidence}:
            by_file[file] = by_file.get(file, 0) + 1
        for end in (r.source_id, r.target_id):
            by_container.setdefault(end, []).append(r)

    def weight(e: EntryPointRef) -> int:
        named = re.compile(rf"(?<![\w/]){re.escape(e.name)}(?!\w)")
        mentions = sum(1 for r in by_container.get(e.container_id, []) if named.search(r.label))
        return by_file.get(e.file, 0) + mentions

    queues = [
        sorted(
            entry_points(container),
            key=lambda e: (
                -weight(e),
                _ENTRY_KIND_ORDER.get(e.kind, len(_ENTRY_KIND_ORDER)),
                e.name,
            ),
        )
        for container in sorted(
            containers, key=lambda c: core.index(c.id) if c.id in core else len(core)
        )
    ]
    turns = [queue[turn] for turn in range(max(map(len, queues), default=0)) for queue in queues
             if turn < len(queue)]  # fmt: skip
    return turns[:limit]


def component_views(graph: ArchitectureGraph) -> list[C4View]:
    return [
        component_view(graph, container)
        for system in graph.nodes(NodeKind.SYSTEM)
        for container in core_containers(graph, system)
    ]


def component_view(graph: ArchitectureGraph, container: Node) -> C4View:
    def place(node: Node) -> str | None:
        if _hidden(node):
            return None
        if node.kind is NodeKind.COMPONENT:
            return node.id if node.parent_id == container.id else _container_of(graph, node.id)
        if node.kind is NodeKind.CONTAINER:
            return node.id if node.parent_id == container.parent_id else node.parent_id
        return None if node.kind is NodeKind.PLATFORM else node.id

    inner = graph.children(container.id, NodeKind.COMPONENT)
    inner_ids = {c.id for c in inner}
    relationships = _merge(graph, component_relationships(graph, container), place)
    connected = {i for r in relationships for i in (r.source_id, r.target_id)}
    return C4View(
        key=container.id.removeprefix("container:").replace("/", "-"),
        title=f"Components of {container.name} (AS-IS)",
        boundary=container,
        inner=inner,
        outer=[graph.node(i) for i in _placed_ids(graph, place) if i in connected - inner_ids],
        relationships=relationships,
    )


def component_relationships(graph: ArchitectureGraph, container: Node) -> list[ViewRelationship]:
    """Relationships touching the container's components, with the container's own
    relationships attributed to components through the files of their evidence."""
    components = graph.children(container.id, NodeKind.COMPONENT)
    component_ids = {c.id for c in components}
    owners: dict[str, str] = {}  # file -> component that declares it
    for component in components:
        classes = [f for k, f in component.attributes.items() if k.startswith("class:")]
        for file in [e.file for e in component.evidence] + classes:
            owners.setdefault(file, component.id)

    edges: list[ViewRelationship] = []
    for r in graph.relationships():
        if container.id not in (r.source_id, r.target_id):
            if {r.source_id, r.target_id} & component_ids:
                edges.append(_edge(r.source_id, r.target_id, describe(r), r.evidence))
            continue
        by_component: dict[str, list[Evidence]] = {}
        for e in r.evidence:
            if (component_id := owners.get(e.file)) is not None:
                by_component.setdefault(component_id, []).append(e)
        for component_id, evidence in by_component.items():
            source, target = (
                (component_id, r.target_id)
                if r.source_id == container.id
                else (r.source_id, component_id)
            )
            edges.append(_edge(source, target, describe(r), tuple(evidence)))
    return edges


def _container_of(graph: ArchitectureGraph, node_id: str) -> str:
    container = graph.ancestor(node_id, NodeKind.CONTAINER)
    return container.id if container else node_id


def _edge(
    source: str, target: str, description: str, evidence: tuple[Evidence, ...]
) -> ViewRelationship:
    return ViewRelationship(
        source_id=source, target_id=target, description=description, evidence=evidence
    )


def _placed_ids(graph: ArchitectureGraph, place: Callable[[Node], str | None]) -> list[str]:
    return list(dict.fromkeys(p for n in graph.nodes() if (p := place(n)) is not None))


def _rolled_up(
    graph: ArchitectureGraph,
    place: Callable[[Node], str | None],
    keep: Callable[[Relationship], bool] = lambda r: True,
) -> list[ViewRelationship]:
    edges = [
        _edge(r.source_id, r.target_id, describe(r), r.evidence)
        for r in graph.relationships()
        if keep(r)
        and NodeKind.COMPONENT not in (graph.node(r.source_id).kind, graph.node(r.target_id).kind)
    ]
    return _merge(graph, edges, place)


def _merge(
    graph: ArchitectureGraph,
    edges: Iterable[ViewRelationship],
    place: Callable[[Node], str | None],
) -> list[ViewRelationship]:
    """Move edge ends to their placed elements; drop self/unplaced edges and merge duplicates."""
    merged: dict[tuple[str, str], tuple[list[str], tuple[Evidence, ...]]] = {}
    for edge in edges:
        src, tgt = place(graph.node(edge.source_id)), place(graph.node(edge.target_id))
        if src is None or tgt is None or src == tgt:
            continue
        descriptions, evidence = merged.get((src, tgt), ([], ()))
        if edge.description not in descriptions:
            descriptions.append(edge.description)
        merged[(src, tgt)] = (descriptions, merge_evidence(evidence, edge.evidence))
    relationships: list[ViewRelationship] = []
    for (src, tgt), (descs, evidence) in merged.items():
        back = merged.get((tgt, src))
        if back is not None and back[0] == descs:  # opposite, same description: one, both ways
            if (tgt, src) in [(r.source_id, r.target_id) for r in relationships]:
                continue
            evidence = merge_evidence(evidence, back[1])
        relationships.append(
            ViewRelationship(source_id=src, target_id=tgt, description=", ".join(descs),
                             evidence=evidence, both_ways=back is not None and back[0] == descs)
        )  # fmt: skip
    return relationships
