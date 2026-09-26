import pytest

from exodus.domain.documentation import OpenQuestion, Question, drivers, open_questions
from exodus.domain.graph import ArchitectureGraph, GraphDocument
from exodus.domain.model import (
    DomainError,
    Evidence,
    GlossaryTerm,
    InferredItem,
    Node,
    NodeKind,
    ProjectContext,
    Relationship,
    RelKind,
)

EV = Evidence(file="s/x", line=1, snippet="")


def node(node_id: str, kind: NodeKind, parent: str | None = None, **attributes: str) -> Node:
    return Node(
        id=node_id, kind=kind, name=node_id, evidence=(EV,), parent_id=parent, attributes=attributes
    )


def shop() -> ArchitectureGraph:
    graph = ArchitectureGraph(
        [
            node("S", NodeKind.SYSTEM),
            node("O", NodeKind.SYSTEM),
            node("web", NodeKind.CONTAINER, "S", language="C#", framework=".NET Framework 4.0",
                 **{"technology:WCF": "WCF", "unresolved-datasource:Legacy": "???",
                    "undetermined-table:Orders": "s/x:1"}),
            node("api", NodeKind.CONTAINER, "S", language="C#", framework=".NET Framework 4.0"),
            node("o1", NodeKind.CONTAINER, "O", language="C#", framework=".NET 8.0",
                 **{"entry-point:HTTP:/": "s/x:1"}),
            node("db", NodeKind.DATA_STORE, engine="sqlserver"),
            node("lite", NodeKind.DATA_STORE, engine="sqlite"),
        ]
    )  # fmt: skip
    for source, target in [("web", "db"), ("api", "db"), ("o1", "db"), ("web", "lite")]:
        graph.add_relationship(
            Relationship(
                source_id=source, target_id=target, kind=RelKind.DEPENDS_ON,
                label="reads/writes", evidence=(EV,),
            )
        )  # fmt: skip
    return graph


def test_drivers_group_the_high_risks_of_the_system() -> None:
    graph = shop()
    found = drivers(graph, graph.node("S"))
    titles = {d.title: d.where for d in found}
    assert titles["Unsupported .NET runtime"] == ("api", "web")
    assert titles["Legacy .NET technology"] == ("web",)
    assert titles["Shared database"] == ("db",)  # shared with system O
    assert all(d.detail for d in found)


def test_open_questions_list_what_needs_a_person_to_confirm() -> None:
    graph = shop()
    questions = open_questions(graph, graph.node("S"))
    assert OpenQuestion(kind=Question.UNRESOLVED_DATASOURCE, subject="web", detail="Legacy") in (
        questions
    )
    assert (
        OpenQuestion(kind=Question.UNDETERMINED_DATABASE, subject="web", detail="table:Orders")
        in questions
    )
    assert OpenQuestion(kind=Question.NO_AWS_TARGET, subject="lite", detail="sqlite") in questions
    assert OpenQuestion(kind=Question.RETIRE_CANDIDATE, subject="api") in questions
    assert all(q.subject != "o1" for q in questions)  # other system


def context() -> ProjectContext:
    return ProjectContext(
        system_id="S",
        problem="Vende online",
        goals=("Receber pedidos",),
        principles=(InferredItem(text="Camadas", basis="componentes Web e Data"),),
        assumptions=("Clientes pagam no ato",),
        glossary=(GlossaryTerm(term="Order", meaning="Pedido"),),
        confidence=0.7,
    )


def test_project_context_is_kept_per_system_and_round_trips() -> None:
    graph = shop()
    graph.set_project_context(context())
    restored = ArchitectureGraph.from_document(
        GraphDocument.model_validate_json(graph.to_document().model_dump_json())
    )
    assert restored.project_context("S") == context()
    assert restored.project_context("O") is None
    with pytest.raises(DomainError):
        graph.set_project_context(context().model_copy(update={"system_id": "ghost"}))
