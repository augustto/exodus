"""Turn the facts of every scanned root into one ArchitectureGraph, linking projects together.

Rules:
- one scanned root = one System; each application project (deployable) = one Container. A fact
  belongs to the project whose directory is its nearest ancestor; facts outside any project go
  to a root container whose language is the majority of the detected source files.
- a library project is part of every application that references it (directly or through
  other libraries): its facts go to those containers. A library no application references is a
  container of its own, so nothing is lost. A test project is not part of the architecture: it
  is only noted on the containers it tests.
- components group namespaces/packages: in a container made of several projects (a layered
  service: Api, Application, Core, Infrastructure) each project is one component, named by its
  root namespace; in a single-project container, namespaces one level below the project's root
  namespace. Imports = depends_on between components of the same system.
- data sources and queues are shared nodes keyed by their normalized identity.
- a called URL matching a path exposed by another container = calls; otherwise an ExternalSystem.
  A call by service name (service discovery) or port goes to the container declaring that
  service; an unknown service is an ExternalSystem.
- platform services (service discovery, secrets, tracing, logging, metrics, broker) are shared
  nodes the containers use.
- Docker: a Dockerfile's runtime image goes to the container of the project it builds (it often
  lives outside that project's folder); a docker-compose service goes to the container known by
  that service name, or else to the system (infrastructure: databases, brokers, tools).
- messages link who sends them to who consumes them (publishes, labelled with the messages):
  a consumed message comes from the owner of the exchange it is routed to (its own exchange
  when not routed); a command routed to an exchange and not consumed, or a message a gateway
  sends, goes to the owner of that exchange. An exchange nobody owns is a queue node. A message
  consumed without any exchange routing (MassTransit, NServiceBus) comes from the projects
  publishing that message type.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from exodus.application.use_cases.scan_projects import ProjectScan
from exodus.domain.facts import (
    ClassDeclared,
    ComposeService,
    DataObjectUsed,
    DataSourceUsed,
    DocumentSection,
    EndpointCalled,
    EndpointExposed,
    EntryPoint,
    ExchangeOwned,
    Fact,
    ImageBuilt,
    ImportFound,
    MessageConsumed,
    MessageDeclared,
    MessagePublished,
    MessageSent,
    ModuleDeclared,
    PackageDependency,
    PlatformUsed,
    ProjectDeclared,
    ProjectReference,
    ProjectRole,
    QueueUsed,
    SecretFound,
    ServiceCalled,
    ServiceDeclared,
    SolutionEntry,
    SourceFileDetected,
    TechnologyUsed,
)
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.identity import (
    datastore_ref,
    endpoint_matches,
    endpoint_origin,
    engine_family,
    queue_ref,
    slug,
    url_host,
)
from exodus.domain.model import Evidence, Node, NodeKind, Relationship, RelKind

DB_ACCESS_LABEL = "reads/writes"


@dataclass
class _Links:
    """Endpoints collected across all systems, resolved once every container exists."""

    exposed: list[tuple[str, EndpointExposed]] = field(default_factory=list)
    calls: list[tuple[str, EndpointCalled]] = field(default_factory=list)
    services: dict[str, tuple[str, Evidence]] = field(default_factory=dict)  # name -> container
    ports: dict[int, tuple[str, Evidence]] = field(default_factory=dict)  # port -> container
    service_calls: list[tuple[str, ServiceCalled]] = field(default_factory=list)
    exchanges: dict[str, tuple[str, str, Evidence]] = field(default_factory=dict)  # owner, tech
    declared: list[tuple[str, MessageDeclared]] = field(default_factory=list)
    consumed: list[tuple[str, MessageConsumed]] = field(default_factory=list)
    published: list[tuple[str, MessagePublished]] = field(default_factory=list)
    sent: list[tuple[str, MessageSent]] = field(default_factory=list)
    compose: list[tuple[str, ComposeService]] = field(default_factory=list)  # system id, service
    data_objects: list[tuple[str, DataObjectUsed]] = field(default_factory=list)


def build_graph(scans: Sequence[ProjectScan]) -> ArchitectureGraph:
    graph = ArchitectureGraph()
    links = _Links()
    for scan in scans:
        # written documentation is not architecture: it only feeds retrieval (see facts)
        facts = tuple(f for f in scan.facts if not isinstance(f, DocumentSection))
        if facts and not all(isinstance(f, SolutionEntry) for f in facts):  # not only a .sln
            _SystemBuilder(graph, ProjectScan(scan.name, facts), links).build()
    _link_calls(graph, links)
    _link_service_calls(graph, links)
    _link_messages(graph, links)
    _link_compose(graph, links)
    _link_data_objects(graph, links)
    return graph


class _SystemBuilder:
    def __init__(self, graph: ArchitectureGraph, scan: ProjectScan, links: _Links) -> None:
        self.graph = graph
        self.scan = scan
        self.links = links
        self.system_slug = slug(scan.name)
        self.system_id = f"system:{self.system_slug}"
        self.projects = [f for f in scan.facts if isinstance(f, ProjectDeclared)]
        self.project_dirs = {_directory(p.evidence): p for p in self.projects}
        self.references: dict[str, list[str]] = {}  # project name -> referenced project names
        for fact in scan.facts:
            if isinstance(fact, ProjectReference) and (project := self._project(fact)):
                self.references.setdefault(project.name, []).append(fact.target)
        self.containers = self._containers()
        self.members: dict[str, list[str]] = {}  # container id -> names of its projects
        for name, container_ids in self.containers.items():
            for container_id in container_ids:
                self.members.setdefault(container_id, []).append(name)
        namespaces: dict[str, list[str]] = {}
        for fact in scan.facts:
            if isinstance(fact, ModuleDeclared) and (project := self._project(fact)):
                namespaces.setdefault(project.name, []).append(fact.name)
        self.roots = {name: _common_prefix(found) for name, found in namespaces.items()}

    def build(self) -> None:
        owned = [(self._owners(f), f) for f in self.scan.facts]
        orphans = [f for owners, f in owned if owners is None and not isinstance(f, _ROUTED)]
        evidence = tuple(p.evidence for p in self.projects) or (self.scan.facts[0].evidence,)
        self.graph.add_node(
            Node(id=self.system_id, kind=NodeKind.SYSTEM, name=self.scan.name, evidence=evidence)
        )
        for project in self.projects:
            if self.containers[project.name] == [self._container_id(project.name)]:
                self._add_container(
                    project.name, project.language, project.framework, (project.evidence,)
                )
        root_id = self._add_root_container(orphans) if orphans else None
        self._note_tests()

        components: dict[str, list[str]] = {}  # file -> component ids declared in it
        imports: list[ImportFound] = []
        for owners, fact in owned:
            if isinstance(fact, _ROUTED):
                self._route(fact, owners)
                continue
            if owners is None and root_id is not None:
                owners = [root_id]
            for container_id in owners or []:
                self._apply(container_id, fact, components, imports)
        self._link_imports(components, imports)

    # --- containers ----------------------------------------------------------------------

    def _container_id(self, name: str) -> str:
        return f"container:{self.system_slug}/{slug(name)}"

    def _project(self, fact: Fact) -> ProjectDeclared | None:
        """The project whose directory is the nearest ancestor of the fact's file."""
        directory = _directory(fact.evidence)
        for candidate in (directory, *directory.parents):
            if candidate in self.project_dirs:
                return self.project_dirs[candidate]
        return None

    def _owners(self, fact: Fact) -> list[str] | None:
        """Containers the fact belongs to; None when it is outside every project."""
        project = self._project(fact)
        return None if project is None else self.containers[project.name]

    def _containers(self) -> dict[str, list[str]]:
        """Containers each project is part of: an application is its own container; a library
        is part of the applications reaching it through library references; one only tests
        reach is test support, part of none; any other library is its own container; a test
        project is part of none."""
        containers: dict[str, list[str]] = {p.name: [] for p in self.projects}
        for app in (p.name for p in self.projects if p.role is ProjectRole.APPLICATION):
            for name in self._libraries_reached(app) | {app}:
                containers[name].append(self._container_id(app))
        test_support = {
            name
            for test in (p.name for p in self.projects if p.role is ProjectRole.TEST)
            for name in self._libraries_reached(test)
        }
        for project in self.projects:
            orphan = project.role is ProjectRole.LIBRARY and not containers[project.name]
            if orphan and project.name not in test_support:
                containers[project.name] = [self._container_id(project.name)]
        return containers

    def _libraries_reached(self, start: str) -> set[str]:
        """Library projects reachable from a project through library references."""
        roles = {p.name: p.role for p in self.projects}
        reached: set[str] = set()
        pending = [start]
        while pending:
            for target in self.references.get(pending.pop(), []):
                if roles.get(target) is ProjectRole.LIBRARY and target not in reached:
                    reached.add(target)
                    pending.append(target)
        return reached

    def _note_tests(self) -> None:
        """A test project is noted on the containers of the projects it references."""
        for test in (p for p in self.projects if p.role is ProjectRole.TEST):
            tested = {c for target in self.references.get(test.name, [])
                      for c in self.containers.get(target, [])}  # fmt: skip
            for container_id in sorted(tested):
                _annotate(self.graph, container_id, f"test-project:{test.name}",
                          test.evidence.file, test.evidence)  # fmt: skip

    def _add_container(
        self, name: str, language: str | None, framework: str | None, evidence: tuple[Evidence, ...]
    ) -> str:
        attributes = {k: v for k, v in (("language", language), ("framework", framework)) if v}
        technology = " / ".join(v for v in (language, framework) if v) or None
        node = Node(
            id=self._container_id(name),
            kind=NodeKind.CONTAINER,
            name=name,
            evidence=evidence,
            parent_id=self.system_id,
            technology=technology,
            attributes=attributes,
        )
        return self.graph.add_node(node).id

    def _add_root_container(self, orphans: Sequence[Fact]) -> str:
        sources = [f for f in orphans if isinstance(f, SourceFileDetected)]
        languages = Counter(f.language for f in sources).most_common(1)
        language = languages[0][0] if languages else None
        evidence = tuple(f.evidence for f in sources) or (orphans[0].evidence,)
        return self._add_container(self.scan.name, language, None, evidence)

    # --- facts ---------------------------------------------------------------------------

    def _apply(
        self,
        container_id: str,
        fact: Fact,
        components: dict[str, list[str]],
        imports: list[ImportFound],
    ) -> None:
        match fact:
            case PackageDependency(name=name, version=version):
                _annotate(self.graph, container_id, f"package:{name}", version, fact.evidence)
            case ProjectReference(target=target):
                target_id = self._container_id(target)
                if target_id != container_id and self.graph.get(target_id):
                    self._relate(
                        container_id,
                        target_id,
                        RelKind.DEPENDS_ON,
                        "project reference",
                        fact.evidence,
                    )
            case DataSourceUsed():
                self._apply_datasource(container_id, fact)
            case DataObjectUsed():
                self.links.data_objects.append((container_id, fact))
            case QueueUsed():
                self._apply_queue(container_id, fact)
            case EndpointExposed(path=path, protocol=protocol):
                _annotate(self.graph, container_id, f"endpoint:{path}", protocol, fact.evidence)
                self.links.exposed.append((container_id, fact))
            case EndpointCalled():
                self.links.calls.append((container_id, fact))
            case EntryPoint(kind=kind, name=name):
                _annotate(
                    self.graph,
                    container_id,
                    f"entry-point:{kind}:{name}",
                    str(fact.evidence),
                    fact.evidence,
                )
            case TechnologyUsed(name=name):
                _annotate(self.graph, container_id, f"technology:{name}", name, fact.evidence)
            case SecretFound(name=name):
                _annotate(self.graph, container_id, f"secret:{name}", name, fact.evidence)
            case ServiceDeclared(name=name, port=port):
                _annotate(self.graph, container_id, f"service:{name}", str(port or ""),
                          fact.evidence)  # fmt: skip
                self.links.services.setdefault(name, (container_id, fact.evidence))
                if port is not None:
                    self.links.ports.setdefault(port, (container_id, fact.evidence))
            case ServiceCalled():
                self.links.service_calls.append((container_id, fact))
            case ExchangeOwned(name=name, technology=technology):
                _annotate(self.graph, container_id, f"exchange:{name}", technology, fact.evidence)
                self.links.exchanges.setdefault(name, (container_id, technology, fact.evidence))
            case MessageDeclared():
                self.links.declared.append((container_id, fact))
            case MessageConsumed():
                self.links.consumed.append((container_id, fact))
            case MessagePublished():
                self.links.published.append((container_id, fact))
            case MessageSent():
                self.links.sent.append((container_id, fact))
            case PlatformUsed(name=name):
                platform = Node(id=f"platform:{slug(name)}", kind=NodeKind.PLATFORM, name=name,
                                evidence=(fact.evidence,))  # fmt: skip
                self.graph.add_node(platform)
                self._relate(container_id, platform.id, RelKind.DEPENDS_ON, "uses", fact.evidence)
            case ModuleDeclared():
                name = self._component_name(container_id, fact)
                component = Node(
                    id=f"component:{container_id.removeprefix('container:')}/{name}",
                    kind=NodeKind.COMPONENT,
                    name=name,
                    evidence=(fact.evidence,),
                    parent_id=container_id,
                )
                ids = components.setdefault(fact.evidence.file, [])
                if (component_id := self.graph.add_node(component).id) not in ids:
                    ids.append(component_id)
            case ClassDeclared(name=name):
                for component_id in components.get(fact.evidence.file, []):
                    _annotate(
                        self.graph, component_id, f"class:{name}", fact.evidence.file, fact.evidence
                    )
            case ImportFound():
                imports.append(fact)
            case ProjectDeclared() | SourceFileDetected() | SolutionEntry():
                pass

    def _route(self, fact: Fact, owners: list[str] | None) -> None:
        """Facts not owned by the project around their file (see _ROUTED)."""
        match fact:
            case ImageBuilt(project=project, image=image) if project in self.containers:
                for container_id in self.containers[project]:
                    _annotate(self.graph, container_id, "runtime-image", image, fact.evidence)
            case ImageBuilt(image=image):
                for container_id in owners or []:
                    _annotate(self.graph, container_id, "runtime-image", image, fact.evidence)
            case ComposeService():
                self.links.compose.append((self.system_id, fact))

    def _component_name(self, container_id: str, fact: ModuleDeclared) -> str:
        """The component a declared namespace belongs to (see the module rules)."""
        project = self._project(fact)
        if project is None:
            return fact.name
        root = self.roots.get(project.name, "")
        if len(self.members.get(container_id, [])) > 1:
            return root or project.name
        if not root:
            return fact.name
        return ".".join(fact.name.split(".")[: root.count(".") + 2])

    def _apply_datasource(self, container_id: str, fact: DataSourceUsed) -> None:
        ref = datastore_ref(fact.raw, fact.engine_hint)
        if ref is None:
            key = f"unresolved-datasource:{fact.name or fact.evidence}"
            _annotate(self.graph, container_id, key, str(fact.evidence), fact.evidence)
            return
        store = Node(
            id=ref.id,
            kind=NodeKind.DATA_STORE,
            name=ref.name,
            evidence=(fact.evidence,),
            technology=ref.technology,
            attributes={"engine": ref.engine, "host": ref.host, "database": ref.database},
        )
        self.graph.add_node(store)
        self._relate(container_id, ref.id, RelKind.DEPENDS_ON, DB_ACCESS_LABEL, fact.evidence)

    def _apply_queue(self, container_id: str, fact: QueueUsed) -> None:
        ref = queue_ref(fact.raw)
        if ref is None:
            return
        queue = Node(
            id=ref.id,
            kind=NodeKind.QUEUE,
            name=ref.name,
            evidence=(fact.evidence,),
            technology=ref.technology_label,
        )
        self.graph.add_node(queue)
        self._relate(container_id, ref.id, fact.direction, fact.direction.value, fact.evidence)

    def _link_imports(self, components: dict[str, list[str]], imports: list[ImportFound]) -> None:
        """An import links the components of its file to the component with the longest name
        matching the imported module, preferring one in the same container (a library that is
        part of several applications has a component in each)."""
        by_name = [(self.graph.node(cid).name, cid) for ids in components.values() for cid in ids]
        for fact in imports:
            candidates = [
                (name, cid)
                for name, cid in dict.fromkeys(by_name)
                if fact.module == name or fact.module.startswith(name + ".")
            ]
            if not candidates:
                continue
            longest = max(len(name) for name, _ in candidates)
            targets = [cid for name, cid in candidates if len(name) == longest]
            for source_id in components.get(fact.evidence.file, []):
                parent = self.graph.node(source_id).parent_id
                local = [t for t in targets if self.graph.node(t).parent_id == parent]
                for target_id in local or targets:
                    if source_id != target_id:
                        self._relate(
                            source_id, target_id, RelKind.DEPENDS_ON, "imports", fact.evidence
                        )

    def _relate(
        self, source: str, target: str, kind: RelKind, label: str, *evidence: Evidence
    ) -> None:
        self.graph.add_relationship(
            Relationship(
                source_id=source, target_id=target, kind=kind, label=label, evidence=evidence
            )
        )


# facts whose owner is not the project around their file: they never make a root container
_ROUTED = (SolutionEntry, ImageBuilt, ComposeService)


def _common_prefix(names: Sequence[str]) -> str:
    """Longest dotted prefix shared by all the names ('A.B.C', 'A.B.D' -> 'A.B')."""
    common: list[str] = []
    for segments in zip(*(n.split(".") for n in names), strict=False):
        if len(set(segments)) != 1:
            break
        common.append(segments[0])
    return ".".join(common)


def _directory(evidence: Evidence) -> PurePosixPath:
    return PurePosixPath(evidence.file).parent


def _annotate(
    graph: ArchitectureGraph, node_id: str, key: str, value: str, evidence: Evidence
) -> None:
    """Add an attribute and its evidence to an existing node."""
    node = graph.node(node_id)
    graph.add_node(node.model_copy(update={"evidence": (evidence,), "attributes": {key: value}}))


def _specificity(path: str) -> int:
    return len([s for s in path.rstrip("*").split("/") if s])


def _link_data_objects(graph: ArchitectureGraph, links: _Links) -> None:
    """A table or procedure belongs to the only relational database of its container, a
    collection to its only document database; otherwise it stays on the container as
    undetermined. Attribute value: every place it is named."""
    stores: dict[tuple[str, str], list[str]] = {}  # (container, family) -> databases
    for r in graph.relationships(RelKind.DEPENDS_ON):
        target = graph.node(r.target_id)
        if target.kind is NodeKind.DATA_STORE:
            family = engine_family(target.attributes.get("engine", ""))
            stores.setdefault((r.source_id, family), []).append(target.id)
    found: dict[tuple[str, str], list[str]] = {}
    for container_id, fact in links.data_objects:
        family = "document" if fact.kind == "collection" else "relational"
        candidates = stores.get((container_id, family), [])
        owner, prefix = (
            (candidates[0], "") if len(candidates) == 1 else (container_id, "undetermined-")
        )
        places = found.setdefault((owner, f"{prefix}{fact.kind}:{fact.name}"), [])
        if str(fact.evidence) not in places:
            places.append(str(fact.evidence))
    for (owner, key), places in found.items():
        node = graph.node(owner)
        graph.add_node(node.model_copy(update={"attributes": {key: ", ".join(places)}}))


def _link_calls(graph: ArchitectureGraph, links: _Links) -> None:
    for caller_id, call in links.calls:
        matches = [
            (target_id, exposed)
            for target_id, exposed in links.exposed
            if endpoint_matches(call.url, exposed.path)
        ]
        if matches:
            best = max(_specificity(exposed.path) for _, exposed in matches)
            for target_id, exposed in matches:
                if _specificity(exposed.path) == best and target_id != caller_id:
                    graph.add_relationship(
                        Relationship(
                            source_id=caller_id,
                            target_id=target_id,
                            kind=RelKind.CALLS,
                            label=call.protocol,
                            evidence=(call.evidence, exposed.evidence),
                        )
                    )
            continue
        host = url_host(call.url)
        if not host:
            continue
        external = Node(
            id=f"external:{host}",
            kind=NodeKind.EXTERNAL_SYSTEM,
            name=host,
            evidence=(call.evidence,),
            attributes={f"url:{endpoint_origin(call.url)}": call.protocol},
        )
        graph.add_node(external)
        graph.add_relationship(
            Relationship(
                source_id=caller_id,
                target_id=external.id,
                kind=RelKind.CALLS,
                label=call.protocol,
                evidence=(call.evidence,),
            )
        )


def _link_service_calls(graph: ArchitectureGraph, links: _Links) -> None:
    for caller_id, call in links.service_calls:
        found = links.services.get(call.service or "") or links.ports.get(call.port or -1)
        if found is not None:
            target_id, declared = found
            if target_id != caller_id:
                graph.add_relationship(
                    Relationship(source_id=caller_id, target_id=target_id, kind=RelKind.CALLS,
                                 label=call.protocol, evidence=(call.evidence, declared))
                )  # fmt: skip
            continue
        if not call.service:
            continue
        external = Node(id=f"external:{call.service}", kind=NodeKind.EXTERNAL_SYSTEM,
                        name=call.service, evidence=(call.evidence,))  # fmt: skip
        graph.add_node(external)
        graph.add_relationship(
            Relationship(source_id=caller_id, target_id=external.id, kind=RelKind.CALLS,
                         label=call.protocol, evidence=(call.evidence,))
        )  # fmt: skip


_BROKER = "RabbitMQ"  # technology of an exchange nobody owns (Convey routes to RabbitMQ)
_BUS_PACKAGES = ("MassTransit", "NServiceBus")


def _bus(graph: ArchitectureGraph, container_id: str) -> str:
    """Messaging library of a container, from its packages ("async" when unknown)."""
    packages = [k.removeprefix("package:") for k in graph.node(container_id).attributes
                if k.startswith("package:")]  # fmt: skip
    return next((b for b in _BUS_PACKAGES for p in packages if p.startswith(b)), "async")


def _link_messages(graph: ArchitectureGraph, links: _Links) -> None:
    routed = {(cid, f.message): f for cid, f in reversed(links.declared)}  # first one wins
    own = {cid: name for name, (cid, _, _) in reversed(links.exchanges.items())}
    consumed = {(cid, f.message) for cid, f in links.consumed}
    flows: dict[tuple[str, str, RelKind], tuple[list[str], list[Evidence], str]] = {}

    def flow(source: str, target: str, kind: RelKind, message: str, technology: str,
             *evidence: Evidence) -> None:  # fmt: skip
        messages, found, _ = flows.setdefault((source, target, kind), ([], [], technology))
        if message not in messages:
            messages.append(message)
        found.extend(evidence)

    def queue(exchange: str, *evidence: Evidence) -> str:
        """Node of an exchange nobody owns, traced to the messages routed to it."""
        return graph.add_node(
            Node(id=f"queue:{slug(_BROKER)}:{slug(exchange)}", kind=NodeKind.QUEUE, name=exchange,
                 evidence=evidence, technology=_BROKER)
        ).id  # fmt: skip

    for consumer, fact in links.consumed:
        declared = routed.get((consumer, fact.message))
        exchange = fact.exchange or (declared.exchange if declared else own.get(consumer))
        if exchange is None:  # no exchange routing: from who publishes this message type
            for publisher, published in links.published:
                if published.message == fact.message and publisher != consumer:
                    flow(publisher, consumer, RelKind.PUBLISHES, fact.message,
                         _bus(graph, publisher), published.evidence, fact.evidence)  # fmt: skip
            continue
        evidence = [fact.evidence] + ([declared.evidence] if declared else [])
        owner = links.exchanges.get(exchange)
        if owner is None:
            target = queue(exchange, *evidence)
            flow(consumer, target, RelKind.CONSUMES, fact.message, _BROKER, *evidence)
        elif owner[0] != consumer:
            flow(owner[0], consumer, RelKind.PUBLISHES, fact.message, owner[1], owner[2], *evidence)

    sends = [(cid, f.exchange, f.message, f.evidence) for cid, f in links.sent]
    sends += [(cid, f.exchange, f.message, f.evidence) for cid, f in links.declared
              if f.is_command and (cid, f.message) not in consumed]  # fmt: skip
    for sender, exchange, message, sent_at in sends:
        owner = links.exchanges.get(exchange)
        if owner is None:
            flow(sender, queue(exchange, sent_at), RelKind.PUBLISHES, message, _BROKER, sent_at)
        elif owner[0] != sender:
            flow(sender, owner[0], RelKind.PUBLISHES, message, owner[1], sent_at, owner[2])

    for (source, target, kind), (messages, evidence, technology) in flows.items():
        graph.add_relationship(
            Relationship(source_id=source, target_id=target, kind=kind,
                         label=f"{', '.join(messages)} ({technology})", evidence=tuple(evidence))
        )  # fmt: skip


def _link_compose(graph: ArchitectureGraph, links: _Links) -> None:
    for system_id, fact in links.compose:
        found = links.services.get(fact.name)
        if found is not None:
            key, node_id = f"deployed-as:{fact.name}", found[0]
        else:
            key, node_id = f"compose:{fact.name}", system_id
        _annotate(graph, node_id, key, fact.image, fact.evidence)
