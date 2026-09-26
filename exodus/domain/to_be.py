"""TO-BE container views (L2), projected from the AS-IS view of each system.

The replatform view keeps every element and relationship of the AS-IS container view, each
element running on its fast-path AWS target (see `migration`); a relationship through a
platform service (e.g. "OrderPlaced (RabbitMQ)") names that service's target instead. Every
relationship keeps its AS-IS evidence.
"""

from exodus.domain.graph import ArchitectureGraph
from exodus.domain.migration import plan_migration
from exodus.domain.model import Node, NodeKind
from exodus.domain.views import C4View, ViewRelationship, container_view


def replatform_views(graph: ArchitectureGraph) -> list[C4View]:
    return [replatform_view(graph, system) for system in graph.nodes(NodeKind.SYSTEM)]


def replatform_view(graph: ArchitectureGraph, system: Node) -> C4View:
    plan = plan_migration(graph)
    targets = {c.container_id: c.fast.target for c in plan.containers}
    targets |= {i.node_id: i.fast for i in plan.infrastructure}
    as_is = container_view(graph, system)
    renamed = {
        f"({graph.node(i).name})": f"({target})"
        for i, target in targets.items()
        if graph.node(i).kind is NodeKind.PLATFORM
    }

    def moved(node: Node) -> Node:
        target = targets.get(node.id)
        return node.model_copy(update={"technology": target}) if target else node

    def relabeled(relationship: ViewRelationship) -> ViewRelationship:
        description = relationship.description
        for old, new in renamed.items():
            description = description.replace(old, new)
        return relationship.model_copy(update={"description": description})

    return as_is.model_copy(
        update={
            "title": f"Containers of {system.name} (TO-BE: replatform)",
            "boundary": system.model_copy(update={"name": f"AWS Cloud — {system.name}"}),
            "inner": [moved(n) for n in as_is.inner],
            "outer": [moved(n) for n in as_is.outer],
            "platform": [moved(n) for n in as_is.platform],
            "relationships": [relabeled(r) for r in as_is.relationships],
        }
    )
