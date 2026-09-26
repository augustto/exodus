"""The refactor (modern) TO-BE: a plan of choices from the refactor catalog and its L2 view.

- The catalog (`exodus/catalog/refactor-catalog.json`) is the closed list of AWS options per
  kind of piece; the plan is made of choices from it (inferred by a model, or the first option
  of the piece type when none was inferred).
- Each piece gets its type from what was extracted: entry points, technologies, packages,
  database engine, queue technology, platform service name.
- Structural decisions (merging services, splitting a shared database) only apply to services
  that already move together (same wave group) and to databases used by several containers.
- The view is the AS-IS container view transformed by the plan: a merged service's
  relationships move to the service absorbing it (calls between the two become internal), a
  removed piece disappears with its relationships, a split database is named by the split, and
  a relationship through a platform service names its new target. No relationship is invented:
  each keeps its AS-IS evidence.
"""

from pydantic import Field

from exodus.domain.graph import ArchitectureGraph
from exodus.domain.identity import engine_family
from exodus.domain.migration import plan_migration
from exodus.domain.model import (
    Entity,
    Inference,
    Node,
    NodeKind,
    RefactorPlan,
    RelKind,
    merge_evidence,
)
from exodus.domain.views import C4View, ViewRelationship, container_view


class CatalogOption(Entity):
    id: str
    service: str
    when: str
    cost: str
    security: str
    performance: str


class PieceType(Entity):
    id: str
    category: str
    label: str
    options: tuple[CatalogOption, ...] = Field(min_length=1)

    def option(self, option_id: str) -> CatalogOption | None:
        return next((o for o in self.options if o.id == option_id), None)


class CrossCutting(Entity):
    id: str
    applies_to: str
    suggestion: str
    cost: str
    security: str
    performance: str


class Catalog(Entity):
    version: str
    purpose: str
    priorities: tuple[str, ...]
    sources: tuple[str, ...]
    retired_or_closed: dict[str, str]
    piece_types: tuple[PieceType, ...]
    cross_cutting: tuple[CrossCutting, ...]

    def piece(self, piece_id: str) -> PieceType | None:
        return next((p for p in self.piece_types if p.id == piece_id), None)


REMOVE = "remove"
_SPLITS = {
    "schema-per-service": "schema per service",
    "database-per-service": "database per service",
}
_GATEWAYS = ("ocelot", "ntrada", "yarp", "spring-cloud-starter-gateway", "zuul")
_IDENTITY = ("identityserver", "microsoft.aspnetcore.identity", "authorization-server")
_PLATFORM_TYPES = {
    "consul": "service-discovery", "eureka": "service-discovery", "fabio": "load-balancer",
    "vault": "secrets", "jaeger": "tracing", "zipkin": "tracing", "seq": "logging",
    "elasticsearch": "logging", "prometheus": "metrics", "influxdb": "metrics",
    "grafana": "metrics", "rabbitmq": "message-broker",
}  # fmt: skip
_QUEUE_TYPES = {"msmq": "local-queue", "jms": "local-queue", "amqp": "message-broker"}
_DATA_TYPES = {
    "relational": "relational-database",
    "document": "document-database",
    "cache": "cache",
}


def piece_type(graph: ArchitectureGraph, node: Node) -> str | None:
    """The catalog piece type of an element; None for what is not migrated (other systems).
    A container called synchronously by another one is an API even when its routes were not
    detected as entry points."""
    attributes = node.attributes
    if node.kind is NodeKind.CONTAINER:
        packages = [
            k.removeprefix("package:").lower() for k in attributes if k.startswith("package:")
        ]
        entries = {k.split(":")[1] for k in attributes if k.startswith("entry-point:")}
        if "technology:Web Forms" in attributes:
            return "web-frontend"
        if any(p.startswith(_GATEWAYS) for p in packages):
            return "api-gateway"
        if any(p.startswith(_IDENTITY) for p in packages):
            return "identity-service"
        if "technology:WCF" in attributes or "SOAP" in entries:
            return "soap-service"
        if (
            "HTTP" in entries
            or any(k.startswith("endpoint:") for k in attributes)
            or _called(graph, node)
        ):
            return "api-service"
        if entries & {"queue consumer", "Windows service", "CLI command"}:
            return "worker"
        if entries & {"scheduled job", "scheduled task"}:
            return "scheduled-job"
        return "api-service"
    if node.kind is NodeKind.DATA_STORE:
        return _DATA_TYPES[engine_family(attributes.get("engine", ""))]
    if node.kind is NodeKind.QUEUE:
        technology = node.id.split(":")[1] if node.id.count(":") >= 2 else ""
        return _QUEUE_TYPES.get(technology)
    if node.kind is NodeKind.PLATFORM:
        return _PLATFORM_TYPES.get(node.id.removeprefix("platform:"))
    return None


def _called(graph: ArchitectureGraph, container: Node) -> bool:
    for r in graph.relationships(RelKind.CALLS):
        target = graph.ancestor(r.target_id, NodeKind.CONTAINER)
        source = graph.ancestor(r.source_id, NodeKind.CONTAINER)
        if target is not None and target.id == container.id and source != target:
            return True
    return False


def shared_databases(graph: ArchitectureGraph) -> dict[str, tuple[str, ...]]:
    """Data stores used by several containers, with those containers."""
    users: dict[str, set[str]] = {}
    for r in graph.relationships():
        container = graph.ancestor(r.source_id, NodeKind.CONTAINER)
        if container and graph.node(r.target_id).kind is NodeKind.DATA_STORE:
            users.setdefault(r.target_id, set()).add(container.id)
    return {store: tuple(sorted(u)) for store, u in users.items() if len(u) > 1}


def merge_candidates(graph: ArchitectureGraph) -> list[tuple[str, str]]:
    """(service, into) pairs that may merge: containers already moving in the same wave group."""
    groups = [g.container_ids for w in plan_migration(graph).waves for g in w.groups]
    return sorted((a, b) for ids in groups for a in ids for b in ids if a != b)


def refactor_view(graph: ArchitectureGraph, system: Node) -> C4View:
    plan = graph.refactor or RefactorPlan()
    choices = {c.node_id: c for c in plan.choices}
    into = {m.source_id: m.into_id for m in plan.merges}
    splits = {s.store_id: _SPLITS[s.option_id] for s in plan.shared if s.option_id in _SPLITS}
    removed = {i for i, c in choices.items() if c.option_id == REMOVE} | set(into)
    renamed = {
        f"({graph.node(i).name})": f"({c.service})"
        for i, c in choices.items()
        if graph.node(i).kind is NodeKind.PLATFORM and c.option_id != REMOVE
    }
    as_is = container_view(graph, system)

    def moved(node: Node) -> Node:
        choice = choices.get(node.id)
        update: dict[str, object] = {}
        if choice:
            update["technology"] = choice.service
            update["description"] = Inference(
                text=choice.justification,
                confidence=choice.confidence if choice.inferred else 0,
                evidence=node.evidence,
            )
        if node.id in splits:
            update["name"] = f"{node.name} ({splits[node.id]})"
        return node.model_copy(update=update)

    links: dict[tuple[str, str], ViewRelationship] = {}
    for r in as_is.relationships:
        source, target = into.get(r.source_id, r.source_id), into.get(r.target_id, r.target_id)
        if source == target or {source, target} & (removed - set(into)):
            continue
        description = r.description
        for old, new in renamed.items():
            description = description.replace(old, new)
        found = links.get((source, target))
        if found:
            parts = dict.fromkeys([*found.description.split(", "), *description.split(", ")])
            description = ", ".join(parts)
            evidence = merge_evidence(found.evidence, r.evidence)
        else:
            evidence = r.evidence
        links[(source, target)] = r.model_copy(
            update={
                "source_id": source,
                "target_id": target,
                "description": description,
                "evidence": evidence,
            }
        )

    def kept(nodes: list[Node]) -> list[Node]:
        return [moved(n) for n in nodes if n.id not in removed]

    return as_is.model_copy(
        update={
            "title": f"Containers of {system.name} (TO-BE: refactor)",
            "boundary": system.model_copy(update={"name": f"AWS Cloud — {system.name}"}),
            "inner": kept(as_is.inner),
            "outer": kept(as_is.outer),
            "platform": kept(as_is.platform),
            "relationships": list(links.values()),
        }
    )
