from collections.abc import Callable
from pathlib import Path, PurePosixPath

from exodus.application.ports import DraftStep, UseCaseDraft, UseCaseRequest
from exodus.application.use_cases.write_use_cases import write_use_cases
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence, Node, NodeKind, Relationship, RelKind
from tests.unit.application.test_scan_and_render import FakeFileSource

CONTROLLER = "s/Web/OrdersController.cs"
SERVICE = "s/Web/OrderService.cs"
FILES = {
    CONTROLLER: 'class OrdersController {\n  [HttpPost("orders")]\n'
    "  void Post() { new OrderService().Place(new Order()); }\n}\n",
    SERVICE: "class OrderService {\n  void Place(Order o) { db.Save(o); }\n}\n",
    "s/Web/Unused.cs": "class Unused {}\n",
    "o/Order.cs": "class Order {}\n",
}
ROOTS = [Path("/src/s"), Path("/src/o")]


def ev(file: str, line: int = 1) -> Evidence:
    return Evidence(file=file, line=line, snippet="")


def node(node_id: str, kind: NodeKind, parent: str | None = None, **attributes: str) -> Node:
    return Node(
        id=node_id,
        kind=kind,
        name=node_id,
        evidence=(ev("s/x"),),
        parent_id=parent,
        attributes=attributes,
    )


def shop() -> ArchitectureGraph:
    graph = ArchitectureGraph(
        [
            node("S", NodeKind.SYSTEM),
            node("web", NodeKind.CONTAINER, "S", **{"entry-point:HTTP:/orders": f"{CONTROLLER}:2"}),
            node(
                "web.api",
                NodeKind.COMPONENT,
                "web",
                **{"class:OrderService": SERVICE, "class:Unused": "s/Web/Unused.cs"},
            ),
            node("O", NodeKind.SYSTEM),
            node("o1", NodeKind.CONTAINER, "O"),
            node("o1.core", NodeKind.COMPONENT, "o1", **{"class:Order": "o/Order.cs"}),
            node("db", NodeKind.DATA_STORE),
            node("other-db", NodeKind.DATA_STORE),
            node("consul", NodeKind.PLATFORM),
        ]
    )
    for source, target, file in [
        ("web", "db", CONTROLLER),
        ("web", "consul", CONTROLLER),  # platform: never touched by a use case
        ("o1", "web", "o/Order.cs"),  # calls web: triggers, is not touched
        ("o1", "other-db", "o/Order.cs"),
    ]:
        graph.add_relationship(
            Relationship(
                source_id=source,
                target_id=target,
                kind=RelKind.DEPENDS_ON,
                label="reads/writes",
                evidence=(ev(file),),
            )
        )
    return graph


class FakeWriter:
    def __init__(self, draft: UseCaseDraft | None) -> None:
        self.answer = draft
        self.requests: list[UseCaseRequest] = []

    def draft(
        self,
        request: UseCaseRequest,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> UseCaseDraft | None:
        self.requests.append(request)
        return self.answer


DRAFT = UseCaseDraft(
    title="Registrar pedido",
    steps=(
        DraftStep(text="Recebe o POST /orders", file=CONTROLLER, line=3),
        DraftStep(text="Grava o pedido", file=SERVICE, line=2),
        DraftStep(text="Arquivo não enviado", file="s/Web/Unused.cs", line=1),
        DraftStep(text="Linha inexistente", file=SERVICE, line=99),
    ),
    touches=("db", "ghost"),
    confidence=1.5,
)


def test_writes_a_use_case_keeping_only_valid_citations_and_known_touches() -> None:
    graph, writer = shop(), FakeWriter(DRAFT)

    write_use_cases(graph, ROOTS, FakeFileSource(FILES), writer)

    [request] = writer.requests
    assert (request.entry.container_id, request.container) == ("web", "web")
    # the entry file, then the classes it names in the same system (not o/Order.cs of O)
    assert [s.path for s in request.sources] == [CONTROLLER, SERVICE]
    assert request.sources[0].first_line == 1
    # only what the container uses, platform services aside
    assert request.candidates == ("db",)
    [use_case] = graph.use_cases()
    assert use_case.container_id == "web"
    assert (use_case.trigger_kind, use_case.trigger) == ("HTTP", "/orders")
    assert use_case.entry == Evidence(file=CONTROLLER, line=2, snippet='[HttpPost("orders")]')
    assert use_case.title == "Registrar pedido"
    assert [(s.text, str(s.evidence)) for s in use_case.steps] == [
        ("Recebe o POST /orders", f"{CONTROLLER}:3"),
        ("Grava o pedido", f"{SERVICE}:2"),
    ]
    assert use_case.steps[1].evidence.snippet == "void Place(Order o) { db.Save(o); }"
    assert use_case.touches == ("db",)
    assert use_case.confidence == 1.0


def test_small_budget_windows_the_entry_file_and_leaves_out_what_does_not_fit() -> None:
    writer = FakeWriter(DRAFT)

    write_use_cases(shop(), ROOTS, FakeFileSource(FILES), writer, max_chars=60)

    [source] = writer.requests[0].sources
    assert source.path == CONTROLLER
    assert source.has(2)
    assert sum(len(line) + 1 for line in source.lines) <= 60


def test_without_writer_answer_or_valid_step_nothing_is_added() -> None:
    graph = shop()
    assert write_use_cases(graph, ROOTS, FakeFileSource(FILES), None) is graph
    write_use_cases(graph, ROOTS, FakeFileSource(FILES), FakeWriter(None))
    invalid = UseCaseDraft(title="x", steps=DRAFT.steps[2:], touches=(), confidence=0.5)
    write_use_cases(graph, ROOTS, FakeFileSource(FILES), FakeWriter(invalid))
    assert graph.use_cases() == []


class MissingFiles(FakeFileSource):
    def read_text(self, root: Path, path: PurePosixPath) -> str:
        raise FileNotFoundError(path)
