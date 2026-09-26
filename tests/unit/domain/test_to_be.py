from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence, Node, NodeKind, Relationship, RelKind
from exodus.domain.to_be import replatform_view, replatform_views

EV = Evidence(file="s/x", line=1, snippet="")


def node(node_id: str, kind: NodeKind, parent: str | None = None, **attributes: str) -> Node:
    return Node(
        id=node_id, kind=kind, name=node_id, evidence=(EV,), parent_id=parent, attributes=attributes
    )


def shop() -> ArchitectureGraph:
    graph = ArchitectureGraph(
        [
            node("S", NodeKind.SYSTEM),
            node("web", NodeKind.CONTAINER, "S", language="C#", framework=".NET Framework 4.8"),
            node("api", NodeKind.CONTAINER, "S", language="C#", framework=".NET 8.0"),
            node("db", NodeKind.DATA_STORE, engine="sqlserver"),
            Node(id="platform:rabbitmq", kind=NodeKind.PLATFORM, name="RabbitMQ", evidence=(EV,)),
        ]
    )
    for source, target, kind, label in [
        ("web", "api", RelKind.PUBLISHES, "OrderPlaced (RabbitMQ)"),
        ("api", "db", RelKind.DEPENDS_ON, "reads/writes"),
        ("api", "platform:rabbitmq", RelKind.DEPENDS_ON, "uses"),
    ]:
        graph.add_relationship(
            Relationship(source_id=source, target_id=target, kind=kind, label=label, evidence=(EV,))
        )
    return graph


def test_replatform_view_is_the_container_view_with_aws_targets() -> None:
    graph = shop()
    view = replatform_view(graph, graph.node("S"))

    assert view.key == "S"
    assert view.title == "Containers of S (TO-BE: replatform)"
    assert view.boundary is not None and view.boundary.name == "AWS Cloud — S"
    technology = {n.id: n.technology for n in [*view.inner, *view.outer, *view.platform]}
    assert technology == {
        "web": "EC2 Windows (IIS)",
        "api": "ECS Fargate",
        "db": "Amazon RDS for SQL Server",
        "platform:rabbitmq": "Amazon MQ for RabbitMQ",
    }
    descriptions = {(r.source_id, r.target_id): r.description for r in view.relationships}
    assert descriptions[("web", "api")] == "OrderPlaced (Amazon MQ for RabbitMQ)"
    assert descriptions[("api", "db")] == "reads/writes"
    assert all(r.evidence == (EV,) for r in view.relationships)  # traceable to the AS-IS


def test_one_replatform_view_per_system() -> None:
    assert [v.key for v in replatform_views(shop())] == ["S"]
