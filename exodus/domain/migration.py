"""Deterministic migration recommendations (7R, AWS targets, waves) projected from the graph.

- Every container gets two paths: the fast one (Rehost when its runtime cannot run in a Linux
  container, else Replatform) and the modern one (Refactor, or none when nothing needs to be
  rewritten). Retain, Repurchase and Relocate cannot be deduced from code.
- Infrastructure (data stores, queues, platform services) maps to AWS by fixed rule tables;
  what no rule covers is "No rule: evaluate".
- Waves: platform services first (the foundation); then groups that must move together
  (containers sharing a data store, or calling each other in a cycle), called before callers.
  Events do not order waves (the broker is in the foundation); a dedicated queue moves with its
  consumer. A wave is a topological level; inside it, groups with fewer HIGH risks come first.
"""

from collections.abc import Iterable
from enum import StrEnum

from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Entity, Node, NodeKind, RelKind
from exodus.domain.risks import Risk, Severity, assess_risks


class Strategy(StrEnum):
    REHOST = "Rehost"
    REPLATFORM = "Replatform"
    REFACTOR = "Refactor"
    NO_RULE = "No rule"


class Path(Entity):
    strategy: Strategy
    target: str
    reason: str = ""


class ContainerPlan(Entity):
    container_id: str
    fast: Path
    modern: Path | None  # None: nothing to rewrite, the fast path is final
    retire_candidate: bool = False


class InfraPlan(Entity):
    node_id: str
    fast: str
    modern: str


class WaveGroup(Entity):
    container_ids: tuple[str, ...]
    store_ids: tuple[str, ...] = ()
    queue_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


class Wave(Entity):
    number: int
    groups: tuple[WaveGroup, ...]


class MigrationPlan(Entity):
    containers: tuple[ContainerPlan, ...]
    infrastructure: tuple[InfraPlan, ...]
    foundation: tuple[str, ...]  # platform services: wave 0
    waves: tuple[Wave, ...]


NO_RULE = "No rule: evaluate"
FARGATE = "ECS Fargate"
DOTNET_MODERN = ".NET 8+ on ECS Fargate"
_DOTNET_REWRITES = {
    "WCF": "WCF → ASP.NET Core / gRPC",
    "Web Forms": "Web Forms → ASP.NET Core",
    "Remoting": "Remoting → gRPC",
    "MSMQ": "MSMQ → Amazon SQS",
}
_TO_AURORA = "Amazon Aurora PostgreSQL (convert schema and procedures with AWS SCT/DMS)"
_DATA_STORES = {
    "sqlserver": ("Amazon RDS for SQL Server", _TO_AURORA),
    "oracle": ("Amazon RDS for Oracle", _TO_AURORA),
    "mysql": ("Amazon RDS for MySQL", "Amazon Aurora MySQL"),
    "postgresql": ("Amazon RDS for PostgreSQL", "Amazon Aurora PostgreSQL"),
    "db2": ("EC2 (no Amazon RDS for this engine)", _TO_AURORA),
    "mongodb": ("Amazon DocumentDB", "Amazon DocumentDB"),
    "redis": ("Amazon ElastiCache for Redis", "Amazon ElastiCache for Redis"),
}
_EVENTS = "Amazon SNS + SQS (or EventBridge)"
_QUEUES = {
    "msmq": ("No equivalent: stays on the rehosted VM", "Amazon SQS"),
    "jms": ("Amazon MQ for ActiveMQ", "Amazon SQS"),
    "amqp": ("Amazon MQ for RabbitMQ", _EVENTS),
}
_PROMETHEUS = "Amazon Managed Service for Prometheus"
_PLATFORM = {
    "consul": ("AWS Cloud Map", "Amazon ECS Service Connect"),
    "fabio": ("Application Load Balancer", "Application Load Balancer"),
    "vault": ("AWS Secrets Manager", "AWS Secrets Manager"),
    "jaeger": ("AWS X-Ray", "AWS X-Ray (OpenTelemetry)"),
    "seq": ("Amazon CloudWatch Logs", "Amazon CloudWatch Logs"),
    "elasticsearch": ("Amazon OpenSearch Service", "Amazon CloudWatch Logs"),
    "prometheus": (_PROMETHEUS, _PROMETHEUS),
    "influxdb": ("Amazon Timestream for InfluxDB", _PROMETHEUS),
    "grafana": ("Amazon Managed Grafana", "Amazon Managed Grafana"),
    "rabbitmq": ("Amazon MQ for RabbitMQ", _EVENTS),
}


def plan_migration(graph: ArchitectureGraph) -> MigrationPlan:
    risks = assess_risks(graph)
    containers = graph.nodes(NodeKind.CONTAINER)
    return MigrationPlan(
        containers=tuple(
            _container_plan(graph, c, [r for r in risks if r.container_id == c.id])
            for c in containers
        ),
        infrastructure=tuple(_infrastructure(graph)),
        foundation=tuple(sorted(n.id for n in graph.nodes(NodeKind.PLATFORM))),
        waves=_waves(graph, containers, risks),
    )


def _container_plan(graph: ArchitectureGraph, container: Node, risks: list[Risk]) -> ContainerPlan:
    fast, modern = _paths(container, {r.rule: r.detail for r in risks})
    return ContainerPlan(
        container_id=container.id,
        fast=fast,
        modern=modern,
        retire_candidate=_retire_candidate(graph, container),
    )


def _paths(container: Node, risks: dict[str, str]) -> tuple[Path, Path | None]:
    language = container.attributes.get("language", "").lower()
    framework = container.attributes.get("framework", "")
    if language in {"c#", "vb"}:
        legacy = [t for t in _DOTNET_REWRITES if f"technology:{t}" in container.attributes]
        if ".NET Framework" in framework or legacy:
            rewrites = [_DOTNET_REWRITES[t] for t in legacy]
            if ".NET Framework" in framework:
                rewrites.append(".NET Framework → .NET 8+")
            return (
                Path(
                    strategy=Strategy.REHOST,
                    target="EC2 Windows (IIS)",
                    reason="; ".join([p for p in [framework] if p] + legacy),
                ),
                Path(strategy=Strategy.REFACTOR, target=DOTNET_MODERN, reason="; ".join(rewrites)),
            )
        if "dotnet-unsupported-runtime" in risks:
            return _upgrade(framework, DOTNET_MODERN)
        return _replatform(framework), None
    if language == "java":
        legacy = [risks[r] for r in ("java-legacy-api", "java-application-server") if r in risks]
        if legacy:
            return (
                Path(
                    strategy=Strategy.REHOST,
                    target="EC2 (same application server)",
                    reason="; ".join(legacy),
                ),
                Path(
                    strategy=Strategy.REFACTOR,
                    target="Spring Boot / Jakarta EE on ECS Fargate",
                    reason="; ".join(legacy),
                ),
            )
        if "java-unsupported-runtime" in risks:
            return _upgrade(framework, "Java 21 on ECS Fargate")
        return _replatform(framework), None
    if language == "python":
        modern = "Current Python 3 on ECS Fargate"
        if "python-unsupported-runtime" in risks:
            return (
                Path(strategy=Strategy.REHOST, target="EC2", reason=framework),
                Path(strategy=Strategy.REFACTOR, target=modern, reason=f"upgrade {framework}"),
            )
        if "python-unsupported-framework" in risks:
            detail = risks["python-unsupported-framework"]
            return (
                _replatform(framework),
                Path(strategy=Strategy.REFACTOR, target=modern, reason=f"upgrade {detail}"),
            )
        return _replatform(framework), None
    return Path(strategy=Strategy.NO_RULE, target="Evaluate", reason=language or "unknown"), None


def _replatform(framework: str) -> Path:
    return Path(strategy=Strategy.REPLATFORM, target=FARGATE, reason=framework)


def _upgrade(framework: str, target: str) -> tuple[Path, Path]:
    return (
        _replatform(framework),
        Path(strategy=Strategy.REFACTOR, target=target, reason=f"runtime upgrade from {framework}"),
    )


def _retire_candidate(graph: ArchitectureGraph, container: Node) -> bool:
    """No entry point, no exposed endpoint and no relationship coming from another container."""
    if any(k.startswith(("entry-point:", "endpoint:")) for k in container.attributes):
        return False
    return not any(
        _container_of(graph, r.target_id) == container.id
        and _container_of(graph, r.source_id) not in (None, container.id)
        for r in graph.relationships()
    )


def _infrastructure(graph: ArchitectureGraph) -> Iterable[InfraPlan]:
    for store in graph.nodes(NodeKind.DATA_STORE):
        fast, modern = _DATA_STORES.get(store.attributes.get("engine", ""), (NO_RULE, NO_RULE))
        yield InfraPlan(node_id=store.id, fast=fast, modern=modern)
    for queue in graph.nodes(NodeKind.QUEUE):
        technology = queue.id.split(":")[1] if queue.id.count(":") >= 2 else ""
        fast, modern = _QUEUES.get(technology, (NO_RULE, NO_RULE))
        yield InfraPlan(node_id=queue.id, fast=fast, modern=modern)
    for platform in graph.nodes(NodeKind.PLATFORM):
        fast, modern = _PLATFORM.get(platform.id.removeprefix("platform:"), (NO_RULE, NO_RULE))
        yield InfraPlan(node_id=platform.id, fast=fast, modern=modern)


def _container_of(graph: ArchitectureGraph, node_id: str) -> str | None:
    container = graph.ancestor(node_id, NodeKind.CONTAINER)
    return container.id if container else None


class _Groups:
    """Union-find over container ids."""

    def __init__(self, ids: Iterable[str]) -> None:
        self.parent = {i: i for i in ids}

    def find(self, i: str) -> str:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, ids: Iterable[str]) -> None:
        roots = sorted({self.find(i) for i in ids})
        for root in roots[1:]:
            self.parent[root] = roots[0]


def _waves(graph: ArchitectureGraph, containers: list[Node], risks: list[Risk]) -> tuple[Wave, ...]:
    names = {c.id: c.name for c in containers}
    groups = _Groups(names)
    users: dict[str, set[str]] = {}
    for r in graph.relationships(RelKind.DEPENDS_ON):
        user = _container_of(graph, r.source_id)
        if user and graph.node(r.target_id).kind is NodeKind.DATA_STORE:
            users.setdefault(r.target_id, set()).add(user)
    for sharing in users.values():
        groups.union(sharing)
    calls = {
        (source, target)
        for r in graph.relationships(RelKind.CALLS)
        if (source := _container_of(graph, r.source_id))
        and (target := _container_of(graph, r.target_id))
        and source != target
    }
    cycles = _merge_cycles(groups, calls)

    def members(root: str) -> list[str]:
        return sorted((i for i in names if groups.find(i) == root), key=lambda i: names[i])

    roots = sorted({groups.find(i) for i in names})
    callees = {root: set[str]() for root in roots}
    for source, target in calls:
        if groups.find(source) != groups.find(target):
            callees[groups.find(source)].add(groups.find(target))
    level: dict[str, int] = {}

    def level_of(root: str) -> int:
        if root not in level:
            level[root] = 1 + max((level_of(c) for c in callees[root]), default=0)
        return level[root]

    queues: dict[str, list[str]] = {}
    for queue in graph.nodes(NodeKind.QUEUE):
        ends = [
            (r.kind is not RelKind.CONSUMES, names[c], c)
            for r in graph.relationships()
            if r.target_id == queue.id and (c := _container_of(graph, r.source_id))
        ]
        if ends:
            queues.setdefault(groups.find(min(ends)[2]), []).append(queue.id)
    high = [r.container_id for r in risks if r.severity is Severity.HIGH and r.container_id]

    def group(root: str) -> WaveGroup:
        ids = members(root)
        shared = sorted(
            graph.node(s).name for s, u in users.items() if len(u) > 1 and u <= set(ids)
        )
        reasons = [f"share {name}" for name in shared]
        reasons += [
            "call each other: " + ", ".join(sorted(names[i] for i in cycle))
            for cycle in cycles
            if groups.find(cycle[0]) == root
        ]
        by_wave: dict[int, list[str]] = {}
        for source, target in sorted(calls):
            if groups.find(source) == root and groups.find(target) != root:
                by_wave.setdefault(level_of(groups.find(target)), []).append(names[target])
        if by_wave:  # what holds the group in its wave: calls into the wave just before
            last = max(by_wave)
            earlier = len({n for wave, called in by_wave.items() if wave < last for n in called})
            held = f"calls {', '.join(sorted(set(by_wave[last])))} (wave {last})"
            reasons.append(held + (f"; +{earlier} in earlier waves" if earlier else ""))
        return WaveGroup(
            container_ids=tuple(ids),
            store_ids=tuple(sorted(s for s, u in users.items() if u <= set(ids))),
            queue_ids=tuple(sorted(queues.get(root, []))),
            reasons=tuple(reasons),
        )

    waves: dict[int, list[str]] = {}
    for root in roots:
        waves.setdefault(level_of(root), []).append(root)
    return tuple(
        Wave(
            number=number,
            groups=tuple(
                group(root)
                for root in sorted(
                    waves[number],
                    key=lambda r: (sum(c in members(r) for c in high), names[members(r)[0]]),
                )
            ),
        )
        for number in sorted(waves)
    )


def _merge_cycles(groups: _Groups, calls: set[tuple[str, str]]) -> list[list[str]]:
    """Merge the groups calling each other in a cycle; return the containers of each cycle."""
    cycles: list[list[str]] = []
    changed = True
    while changed:
        changed = False
        edges: dict[str, set[str]] = {}
        for source, target in calls:
            a, b = groups.find(source), groups.find(target)
            if a != b:
                edges.setdefault(a, set()).add(b)
        for start in sorted(edges):
            reach = _reachable(edges, start)
            cycle = sorted(r for r in reach if start in _reachable(edges, r))
            if cycle:
                involved = [c for c in groups.parent if groups.find(c) in {start, *cycle}]
                cycles.append(sorted(involved))
                groups.union([start, *cycle])
                changed = True
                break
    return cycles


def _reachable(edges: dict[str, set[str]], start: str) -> set[str]:
    seen: set[str] = set()
    stack = list(edges.get(start, ()))
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(edges.get(node, ()))
    return seen
