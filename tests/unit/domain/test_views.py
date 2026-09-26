from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence, Node, NodeKind, Relationship, RelKind
from exodus.domain.views import (
    ViewRelationship,
    component_relationships,
    component_view,
    container_view,
    container_views,
    core_containers,
    core_entry_points,
    system_context,
)

EV = Evidence(file="f.cs", line=1, snippet="")


def node(node_id: str, kind: NodeKind, parent: str | None = None) -> Node:
    return Node(id=node_id, kind=kind, name=node_id, evidence=(EV,), parent_id=parent)


def rel(
    src: str, tgt: str, kind: RelKind = RelKind.DEPENDS_ON, label: str = "reads/writes"
) -> Relationship:
    return Relationship(source_id=src, target_id=tgt, kind=kind, label=label, evidence=(EV,))


def landscape() -> ArchitectureGraph:
    graph = ArchitectureGraph(
        [
            node("A", NodeKind.SYSTEM),
            node("a1", NodeKind.CONTAINER, "A"),
            node("a2", NodeKind.CONTAINER, "A"),
            node("a1.comp", NodeKind.COMPONENT, "a1"),
            node("a2.comp", NodeKind.COMPONENT, "a2"),
            node("B", NodeKind.SYSTEM),
            node("b1", NodeKind.CONTAINER, "B"),
            node("privdb", NodeKind.DATA_STORE),
            node("shared", NodeKind.DATA_STORE),
            node("q", NodeKind.QUEUE),
            node("unused", NodeKind.QUEUE),
            node("X", NodeKind.EXTERNAL_SYSTEM),
        ]
    )
    for r in [
        rel("a1", "privdb"),
        rel("a2", "privdb"),
        rel("a1", "shared"),
        rel("b1", "shared"),
        rel("a1", "q", RelKind.PUBLISHES, "publishes"),
        rel("a2", "q", RelKind.CONSUMES, "consumes"),
        rel("a1", "b1", RelKind.CALLS, "SOAP"),
        rel("a1", "a2", RelKind.DEPENDS_ON, "project reference"),
        rel("a1", "X", RelKind.CALLS, "HTTPS"),
        rel("a1.comp", "a2.comp", RelKind.DEPENDS_ON, "imports"),
    ]:
        graph.add_relationship(r)
    return graph


def pairs(view_rels: list[ViewRelationship]) -> dict[tuple[str, str], str]:
    return {(r.source_id, r.target_id): r.description for r in view_rels}


def test_system_context_rolls_up_to_systems_and_hides_private_infra() -> None:
    view = system_context(landscape())
    assert view.boundary is None
    assert [n.id for n in view.outer] == ["A", "B", "shared", "unused", "X"]
    assert pairs(view.relationships) == {
        ("A", "shared"): "reads/writes",
        ("B", "shared"): "reads/writes",
        ("A", "B"): "calls (SOAP)",
        ("A", "X"): "calls (HTTPS)",
    }


def test_container_view_shows_own_containers_and_private_infra_inside() -> None:
    graph = landscape()
    view = container_view(graph, graph.node("A"))
    assert view.key == "A"
    assert [n.id for n in view.inner] == ["a1", "a2", "privdb", "q"]
    assert [n.id for n in view.outer] == ["B", "shared", "X"]
    assert pairs(view.relationships) == {
        ("a1", "privdb"): "reads/writes",
        ("a2", "privdb"): "reads/writes",
        ("a1", "shared"): "reads/writes",
        ("a1", "q"): "publishes",
        ("a2", "q"): "consumes",
        ("a1", "B"): "calls (SOAP)",
        ("a1", "a2"): "project reference",
        ("a1", "X"): "calls (HTTPS)",
    }


def at(file: str, line: int = 1) -> Evidence:
    return Evidence(file=file, line=line, snippet="")


def components_landscape() -> ArchitectureGraph:
    """web has two components; svc has two; lib has none; o1 lives in another system."""

    def comp(node_id: str, parent: str, file: str, **attributes: str) -> Node:
        return Node(
            id=node_id,
            kind=NodeKind.COMPONENT,
            name=node_id,
            evidence=(at(file),),
            parent_id=parent,
            attributes=attributes,
        )

    graph = ArchitectureGraph(
        [
            node("S", NodeKind.SYSTEM),
            node("web", NodeKind.CONTAINER, "S"),
            node("svc", NodeKind.CONTAINER, "S"),
            node("lib", NodeKind.CONTAINER, "S"),
            node("O", NodeKind.SYSTEM),
            node("o1", NodeKind.CONTAINER, "O"),
            comp("web.ui", "web", "ui.cs"),
            comp("web.core", "web", "core.cs", **{"class:Helper": "helper.cs"}),
            comp("svc.api", "svc", "api.cs"),
            comp("svc.data", "svc", "data.cs"),
            node("db", NodeKind.DATA_STORE),
            node("X", NodeKind.EXTERNAL_SYSTEM),
        ]
    )
    for src, tgt, kind, label, evidence in [
        ("web", "X", RelKind.CALLS, "HTTP", (at("ui.cs", 3),)),
        ("web", "db", RelKind.DEPENDS_ON, "reads/writes", (at("web.config"), at("helper.cs", 2))),
        ("web", "svc", RelKind.CALLS, "SOAP", (at("web.config", 2),)),
        ("web", "lib", RelKind.DEPENDS_ON, "project reference", (at("web.csproj"),)),
        ("o1", "web", RelKind.CALLS, "HTTP", (at("o.cs"), at("ui.cs", 9))),
        ("web.ui", "web.core", RelKind.DEPENDS_ON, "imports", (at("ui.cs"),)),
        ("web.core", "svc.api", RelKind.DEPENDS_ON, "imports", (at("core.cs"),)),
        ("svc.data", "svc.api", RelKind.DEPENDS_ON, "imports", (at("data.cs"),)),
    ]:
        graph.add_relationship(
            Relationship(source_id=src, target_id=tgt, kind=kind, label=label, evidence=evidence)
        )
    return graph


def test_core_containers_rank_by_dependents_then_relationships_and_skip_empty() -> None:
    graph = components_landscape()
    # web and svc have one dependent container each; web touches more relationships
    assert [c.id for c in core_containers(graph, graph.node("S"))] == ["web", "svc"]
    assert [c.id for c in core_containers(graph, graph.node("S"), limit=1)] == ["web"]
    assert core_containers(graph, graph.node("O")) == []


def test_component_view_attributes_container_relationships_to_components_by_file() -> None:
    graph = components_landscape()
    view = component_view(graph, graph.node("web"))
    assert view.key == "web"
    assert view.boundary == graph.node("web")
    assert [n.id for n in view.inner] == ["web.ui", "web.core"]
    assert [n.id for n in view.outer] == ["svc", "O", "db", "X"]
    assert pairs(view.relationships) == {
        ("web.ui", "X"): "calls (HTTP)",
        ("web.core", "db"): "reads/writes",
        ("O", "web.ui"): "calls (HTTP)",
        ("web.ui", "web.core"): "imports",
        ("web.core", "svc"): "imports",
    }
    evidence = {(r.source_id, r.target_id): r.evidence for r in view.relationships}
    assert evidence[("web.core", "db")] == (at("helper.cs", 2),)
    assert evidence[("O", "web.ui")] == (at("ui.cs", 9),)


def test_component_relationships_keep_real_ends() -> None:
    graph = components_landscape()
    edges = pairs(component_relationships(graph, graph.node("web")))
    assert edges == {
        ("web.ui", "X"): "calls (HTTP)",
        ("web.core", "db"): "reads/writes",
        ("o1", "web.ui"): "calls (HTTP)",
        ("web.ui", "web.core"): "imports",
        ("web.core", "svc.api"): "imports",
    }


def with_platform() -> ArchitectureGraph:
    graph = landscape()
    graph.add_node(node("consul", NodeKind.PLATFORM))
    graph.add_node(node("vault", NodeKind.PLATFORM))
    graph.add_relationship(rel("a1", "consul", RelKind.DEPENDS_ON, "uses"))
    graph.add_relationship(rel("a2", "vault", RelKind.DEPENDS_ON, "uses"))
    graph.add_relationship(rel("b1", "consul", RelKind.DEPENDS_ON, "uses"))
    return graph


def test_platform_is_a_group_of_the_container_view_with_one_link() -> None:
    graph = with_platform()
    view = container_view(graph, graph.node("A"))
    assert [n.id for n in view.platform] == ["consul", "vault"]
    assert all("consul" not in (r.source_id, r.target_id) for r in view.relationships)
    assert len(view.platform_evidence) == 2  # one per container using a platform service
    assert container_view(graph, graph.node("B")).platform == [graph.node("consul")]


def test_mutual_relationships_with_the_same_description_become_one_both_ways() -> None:
    def at(file: str) -> tuple[Evidence, ...]:
        return (Evidence(file=file, line=1, snippet=""),)

    graph = ArchitectureGraph([
        Node(id="S", kind=NodeKind.SYSTEM, name="S", evidence=at("s")),
        Node(id="c", kind=NodeKind.CONTAINER, name="c", evidence=at("c"), parent_id="S"),
        Node(id="k1", kind=NodeKind.COMPONENT, name="k1", evidence=at("k1.cs"), parent_id="c"),
        Node(id="k2", kind=NodeKind.COMPONENT, name="k2", evidence=at("k2.cs"), parent_id="c"),
    ])  # fmt: skip
    for src, tgt in (("k1", "k2"), ("k2", "k1")):
        graph.add_relationship(Relationship(source_id=src, target_id=tgt, kind=RelKind.DEPENDS_ON,
                                            label="imports", evidence=at(f"{src}.cs")))  # fmt: skip
    [both] = component_view(graph, graph.node("c")).relationships
    assert both.both_ways and both.description == "imports"
    assert len(both.evidence) == 2


def test_caches_are_left_out_of_the_diagrams() -> None:
    graph = landscape()
    graph.add_node(Node(id="cache", kind=NodeKind.DATA_STORE, name="cache", evidence=(EV,),
                        attributes={"engine": "redis"}))  # fmt: skip
    graph.add_relationship(rel("a1", "cache"))
    assert "cache" not in {n.id for n in container_view(graph, graph.node("A")).inner}
    assert "cache" not in {n.id for n in system_context(graph).outer}
    assert graph.node("cache")  # still in the graph, and so in the inventory


def busy_system(extra_calls: int) -> ArchitectureGraph:
    """System A with two containers exchanging events, plus `extra_calls` external systems."""
    graph = landscape()
    graph.add_relationship(rel("a2", "a1", RelKind.PUBLISHES, "OrderCreated (RabbitMQ)"))
    for i in range(extra_calls):
        graph.add_node(node(f"X{i}", NodeKind.EXTERNAL_SYSTEM))
        graph.add_relationship(rel("a1", f"X{i}", RelKind.CALLS, "HTTP"))
    return graph


def test_container_views_keep_events_with_synchronous_relationships() -> None:
    views = container_views(busy_system(extra_calls=2))
    assert [v.key for v in views] == ["A", "B"]


def test_a_busy_system_stays_in_one_container_view() -> None:
    graph = busy_system(extra_calls=20)
    graph.add_node(node("consul", NodeKind.PLATFORM))
    graph.add_relationship(rel("a1", "consul", RelKind.DEPENDS_ON, "uses"))
    view, other = container_views(graph)
    assert (view.key, other.key) == ("A", "B")
    assert view.title == "Containers of A (AS-IS)"
    relationships = pairs(view.relationships)
    assert {
        ("a2", "a1"): "OrderCreated (RabbitMQ)",
        ("a1", "q"): "publishes",
        ("a2", "q"): "consumes",
        **{("a1", f"X{i}"): "calls (HTTP)" for i in range(20)},
    }.items() <= relationships.items()
    assert view.platform


def test_events_exchanged_both_ways_remain_in_the_same_container_view() -> None:
    graph = busy_system(extra_calls=20)
    graph.add_relationship(rel("a1", "a2", RelKind.PUBLISHES, "OrderApproved (RabbitMQ)"))
    view = next(v for v in container_views(graph) if v.key == "A")
    events = [r for r in view.relationships if {r.source_id, r.target_id} == {"a1", "a2"}]
    descriptions = {r.description for r in events}
    assert any("OrderCreated (RabbitMQ)" in description for description in descriptions)
    assert any("OrderApproved (RabbitMQ)" in description for description in descriptions)


def test_core_entry_points_take_turns_between_containers_by_centrality() -> None:
    graph = components_landscape()
    for container_id, attributes in {
        "web": {"entry-point:HTTP:/orders": "ui.cs:5", "entry-point:CLI command:seed": "cli.cs:1"},
        "svc": {
            "entry-point:queue consumer:OrderPlaced": "api.cs:4",
            "entry-point:HTTP:/stock": "data.cs:2",
            "entry-point:SOAP:Audit": "audit.cs:2",
        },
        "lib": {"entry-point:HTTP:/lib": "lib.cs:1", "entry-point:HTTP:/old": "no-location"},
    }.items():
        graph.add_node(graph.node(container_id).model_copy(update={"attributes": attributes}))
    graph.add_relationship(rel("svc", "X", RelKind.PUBLISHES, "OrderPlaced (RabbitMQ)"))

    ranked = core_entry_points(graph, graph.node("S"))

    # web, then svc (core order), then lib (no components); inside a container: more
    # container-level relationships in the entry's file or naming it (imports don't count),
    # then HTTP/SOAP before consumers and commands, then name
    assert [(e.container_id, e.kind, e.name) for e in ranked] == [
        ("web", "HTTP", "/orders"),
        ("svc", "queue consumer", "OrderPlaced"),
        ("lib", "HTTP", "/lib"),
        ("web", "CLI command", "seed"),
        ("svc", "HTTP", "/stock"),
    ]
    assert (ranked[0].file, ranked[0].line) == ("ui.cs", 5)
    assert len(core_entry_points(graph, graph.node("S"), limit=2)) == 2
    assert core_entry_points(graph, graph.node("O")) == []
