import pytest

from exodus.domain.graph import ArchitectureGraph, GraphDocument
from exodus.domain.model import (
    DomainError,
    Evidence,
    Merge,
    Node,
    NodeKind,
    RefactorChoice,
    RefactorPlan,
    Relationship,
    RelKind,
    SharedDataChoice,
)
from exodus.domain.refactor import (
    Catalog,
    CatalogOption,
    PieceType,
    merge_candidates,
    piece_type,
    refactor_view,
    shared_databases,
)

EV = Evidence(file="s/x", line=1, snippet="")


def node(node_id: str, kind: NodeKind, parent: str | None = None, **attributes: str) -> Node:
    return Node(
        id=node_id, kind=kind, name=node_id, evidence=(EV,), parent_id=parent, attributes=attributes
    )


def option(option_id: str) -> CatalogOption:
    return CatalogOption(
        id=option_id, service=option_id, when="w", cost="c", security="s", performance="p"
    )


def test_catalog_finds_piece_types_and_options() -> None:
    catalog = Catalog(
        version="v",
        purpose="p",
        priorities=("cost", "security", "performance"),
        sources=(),
        retired_or_closed={},
        piece_types=(
            PieceType(id="cache", category="data", label="Cache", options=(option("valkey"),)),
        ),
        cross_cutting=(),
    )
    assert catalog.piece("cache").option("valkey") == option("valkey")
    assert catalog.piece("cache").option("nope") is None
    assert catalog.piece("nope") is None


@pytest.mark.parametrize(
    ("piece", "expected"),
    [
        (node("c", NodeKind.CONTAINER, **{"technology:Web Forms": "x"}), "web-frontend"),
        (node("c", NodeKind.CONTAINER, **{"package:Ocelot": "1"}), "api-gateway"),
        (node("c", NodeKind.CONTAINER, **{"package:IdentityServer4": "4"}), "identity-service"),
        (node("c", NodeKind.CONTAINER, **{"technology:WCF": "WCF"}), "soap-service"),
        (node("c", NodeKind.CONTAINER, **{"entry-point:HTTP:/": "s/x:1"}), "api-service"),
        (node("c", NodeKind.CONTAINER, **{"entry-point:queue consumer:A": "s/x:1"}), "worker"),
        (
            node("c", NodeKind.CONTAINER, **{"entry-point:scheduled job:A": "s/x:1"}),
            "scheduled-job",
        ),
        (node("d", NodeKind.DATA_STORE, engine="sqlserver"), "relational-database"),
        (node("d", NodeKind.DATA_STORE, engine="mongodb"), "document-database"),
        (node("d", NodeKind.DATA_STORE, engine="redis"), "cache"),
        (node("queue:amqp:q", NodeKind.QUEUE), "message-broker"),
        (node("platform:vault", NodeKind.PLATFORM), "secrets"),
        (node("platform:unknown", NodeKind.PLATFORM), None),
    ],
)
def test_piece_type_comes_from_what_was_extracted(piece: Node, expected: str | None) -> None:
    graph = ArchitectureGraph(
        [node("S", NodeKind.SYSTEM), piece.model_copy(update={"parent_id": None})]
    )
    assert piece_type(graph, graph.node(piece.id)) == expected


def test_a_container_called_synchronously_is_an_api_even_without_entry_points() -> None:
    graph = ArchitectureGraph(
        [
            node("S", NodeKind.SYSTEM),
            node("caller", NodeKind.CONTAINER, "S"),
            node("pricing", NodeKind.CONTAINER, "S", **{"entry-point:queue consumer:A": "s/x:1"}),
        ]
    )
    graph.add_relationship(
        Relationship(
            source_id="caller",
            target_id="pricing",
            kind=RelKind.CALLS,
            label="HTTP",
            evidence=(EV,),
        )
    )
    assert piece_type(graph, graph.node("pricing")) == "api-service"


def shop() -> ArchitectureGraph:
    graph = ArchitectureGraph(
        [
            node("S", NodeKind.SYSTEM),
            node("web", NodeKind.CONTAINER, "S", **{"entry-point:HTTP:/": "s/x:1"}),
            node("api", NodeKind.CONTAINER, "S", **{"entry-point:HTTP:/a": "s/x:1"}),
            node("audit", NodeKind.CONTAINER, "S", **{"entry-point:queue consumer:A": "s/x:1"}),
            node("db", NodeKind.DATA_STORE, engine="sqlserver"),
            node("platform:consul", NodeKind.PLATFORM),
            node("platform:rabbitmq", NodeKind.PLATFORM),
        ]
    )
    for source, target, kind, label in [
        ("web", "api", RelKind.CALLS, "HTTP"),
        ("api", "audit", RelKind.PUBLISHES, "Placed (platform:rabbitmq)"),
        ("web", "db", RelKind.DEPENDS_ON, "reads/writes"),
        ("api", "db", RelKind.DEPENDS_ON, "reads/writes"),
        ("api", "platform:consul", RelKind.DEPENDS_ON, "uses"),
        ("api", "platform:rabbitmq", RelKind.DEPENDS_ON, "uses"),
    ]:
        graph.add_relationship(
            Relationship(source_id=source, target_id=target, kind=kind, label=label, evidence=(EV,))
        )
    return graph


def test_structural_candidates_are_databases_and_services_already_moving_together() -> None:
    graph = shop()
    assert shared_databases(graph) == {"db": ("api", "web")}
    # web and api share db: same wave group; audit moves alone
    assert merge_candidates(graph) == [("api", "web"), ("web", "api")]


def choice(node_id: str, piece: str, option_id: str) -> RefactorChoice:
    return RefactorChoice(
        node_id=node_id,
        piece_type=piece,
        option_id=option_id,
        service=f"svc {option_id}",
        justification=f"why {option_id}",
        confidence=0.7,
    )


def test_refactor_plan_is_kept_in_the_graph_and_checked() -> None:
    graph = shop()
    plan = RefactorPlan(
        choices=(choice("api", "api-service", "lambda-api-gateway"),),
        merges=(Merge(source_id="web", into_id="api", justification="small"),),
    )
    graph.set_refactor(plan)
    restored = ArchitectureGraph.from_document(
        GraphDocument.model_validate_json(graph.to_document().model_dump_json())
    )
    assert restored.refactor == plan
    with pytest.raises(DomainError):
        graph.set_refactor(RefactorPlan(choices=(choice("ghost", "cache", "remove"),)))


def test_refactor_view_applies_merges_split_databases_removals_and_renamed_brokers() -> None:
    graph = shop()
    graph.set_refactor(
        RefactorPlan(
            choices=(
                choice("api", "api-service", "lambda-api-gateway"),
                choice("audit", "worker", "lambda-sqs"),
                choice("db", "relational-database", "aurora-postgresql"),
                choice("platform:consul", "service-discovery", "remove"),
                choice("platform:rabbitmq", "message-broker", "sns-sqs"),
            ),
            merges=(Merge(source_id="web", into_id="api", justification="small"),),
            shared=(
                SharedDataChoice(
                    store_id="db", option_id="database-per-service", justification="isolate"
                ),
            ),
        )
    )

    view = refactor_view(graph, graph.node("S"))

    assert view.title == "Containers of S (TO-BE: refactor)"
    elements = {n.id: n for n in [*view.inner, *view.outer, *view.platform]}
    assert set(elements) == {"api", "audit", "db", "platform:rabbitmq"}  # web merged, consul gone
    assert elements["api"].technology == "svc lambda-api-gateway"
    assert elements["api"].description is not None
    assert elements["api"].description.text == "why lambda-api-gateway"
    assert elements["db"].name == "db (database per service)"
    links = {(r.source_id, r.target_id): r.description for r in view.relationships}
    # web -> api became internal; web -> db moved to api and merged with api -> db
    assert links == {
        ("api", "audit"): "Placed (svc sns-sqs)",
        ("api", "db"): "reads/writes",
    }
    assert all(r.evidence for r in view.relationships)
