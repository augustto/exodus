from collections.abc import Callable

from exodus.application.ports import (
    PieceAnswer,
    PieceRequest,
    StructuralAnswer,
    StructuralRequest,
)
from exodus.application.use_cases.propose_refactor import propose_refactor
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence, Node, NodeKind, Relationship, RelKind
from exodus.domain.refactor import Catalog, CatalogOption, PieceType

EV = Evidence(file="s/x", line=1, snippet="")


def option(option_id: str) -> CatalogOption:
    return CatalogOption(
        id=option_id, service=f"AWS {option_id}", when="w", cost="c", security="s", performance="p"
    )


def piece(piece_id: str, *options: str) -> PieceType:
    return PieceType(
        id=piece_id, category="x", label=piece_id, options=tuple(option(o) for o in options)
    )


CATALOG = Catalog(
    version="v",
    purpose="p",
    priorities=("cost", "security", "performance"),
    sources=(),
    retired_or_closed={},
    piece_types=(
        piece("api-service", "ecs-fargate", "lambda-api-gateway", "merge"),
        piece("worker", "ecs-fargate", "lambda-sqs", "merge"),
        piece("relational-database", "rds-same-engine", "aurora-postgresql"),
        piece("shared-database", "keep-shared", "database-per-service"),
    ),
    cross_cutting=(),
)


def node(node_id: str, kind: NodeKind, parent: str | None = None, **attributes: str) -> Node:
    return Node(
        id=node_id, kind=kind, name=node_id, evidence=(EV,), parent_id=parent, attributes=attributes
    )


def shop() -> ArchitectureGraph:
    graph = ArchitectureGraph(
        [
            node("S", NodeKind.SYSTEM),
            node("web", NodeKind.CONTAINER, "S", language="C#", framework=".NET 8.0",
                 **{"entry-point:HTTP:/": "s/x:1"}),
            node("api", NodeKind.CONTAINER, "S", language="C#", framework=".NET 8.0",
                 **{"entry-point:HTTP:/a": "s/x:1"}),
            node("audit", NodeKind.CONTAINER, "S", **{"entry-point:queue consumer:A": "s/x:1"}),
            node("db", NodeKind.DATA_STORE, engine="sqlserver"),
            node("X", NodeKind.EXTERNAL_SYSTEM),
        ]
    )  # fmt: skip
    for source, target, kind in [
        ("web", "api", RelKind.CALLS),
        ("web", "db", RelKind.DEPENDS_ON),
        ("api", "db", RelKind.DEPENDS_ON),
        ("api", "X", RelKind.CALLS),
    ]:
        graph.add_relationship(
            Relationship(source_id=source, target_id=target, kind=kind, label="l", evidence=(EV,))
        )
    return graph


class FakeAdvisor:
    def __init__(
        self, structural: StructuralAnswer | None, answers: dict[str, PieceAnswer | None]
    ) -> None:
        self.structural = structural
        self.answers = answers
        self.structural_requests: list[StructuralRequest] = []
        self.piece_requests: list[PieceRequest] = []

    def structure(
        self,
        request: StructuralRequest,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> StructuralAnswer | None:
        self.structural_requests.append(request)
        return self.structural

    def choose(
        self,
        request: PieceRequest,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> PieceAnswer | None:
        self.piece_requests.append(request)
        return self.answers.get(request.name)


def test_choices_are_validated_against_the_catalog_and_default_when_invalid() -> None:
    advisor = FakeAdvisor(
        StructuralAnswer(
            merges=(("web", "api", "tiny"), ("audit", "api", "not a candidate")),
            shared=(("db", "database-per-service", "isolate"),),
        ),
        {
            "api": PieceAnswer("lambda-api-gateway", "cheaper at low traffic", 0.8),
            "audit": PieceAnswer("made-up-service", "?", 0.9),
            "db": PieceAnswer("aurora-postgresql", "no licence", 1.4),
        },
    )
    graph = shop()

    propose_refactor(graph, CATALOG, advisor)

    [structural] = advisor.structural_requests
    assert structural.merges == (("api", "web"), ("web", "api"))
    assert structural.shared == (("db", ("api", "web")),)
    assert [o.id for o in structural.shared_options.options] == [
        "keep-shared",
        "database-per-service",
    ]
    # web was merged: no choice asked for it; merge is never a per-piece option
    assert [r.name for r in advisor.piece_requests] == ["api", "audit", "db"]
    assert [o.id for o in advisor.piece_requests[0].piece.options] == [
        "ecs-fargate",
        "lambda-api-gateway",
    ]
    assert "calls X" in advisor.piece_requests[0].facts
    assert advisor.piece_requests[0].replatform == "ECS Fargate"
    plan = graph.refactor
    assert plan is not None
    assert [(m.source_id, m.into_id) for m in plan.merges] == [("web", "api")]
    assert [(s.store_id, s.option_id) for s in plan.shared] == [("db", "database-per-service")]
    chosen = {c.node_id: (c.option_id, c.service, c.inferred, c.confidence) for c in plan.choices}
    assert chosen == {
        "api": ("lambda-api-gateway", "AWS lambda-api-gateway", True, 0.8),
        "audit": ("ecs-fargate", "AWS ecs-fargate", False, 0.0),  # invalid answer: default
        "db": ("aurora-postgresql", "AWS aurora-postgresql", True, 1.0),
    }


def test_without_advisor_every_piece_gets_its_default_option() -> None:
    graph = shop()
    propose_refactor(graph, CATALOG, None)
    plan = graph.refactor
    assert plan is not None and plan.merges == () and plan.shared == ()
    assert {c.node_id: c.option_id for c in plan.choices} == {
        "web": "ecs-fargate",
        "api": "ecs-fargate",
        "audit": "ecs-fargate",
        "db": "rds-same-engine",
    }
    assert all(not c.inferred for c in plan.choices)


def test_merge_chains_are_not_applied() -> None:
    advisor = FakeAdvisor(
        StructuralAnswer(merges=(("web", "api", "a"), ("api", "web", "b")), shared=()), {}
    )
    graph = shop()
    propose_refactor(graph, CATALOG, advisor)
    assert graph.refactor is not None
    assert [(m.source_id, m.into_id) for m in graph.refactor.merges] == [("web", "api")]
