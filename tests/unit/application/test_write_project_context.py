from collections.abc import Callable

from exodus.application.ports import Hit, Language, ProjectDraft, ProjectRequest, StoredPiece
from exodus.application.use_cases.write_project_context import write_project_context
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import (
    Evidence,
    GlossaryTerm,
    Inference,
    InferredItem,
    Node,
    NodeKind,
    Relationship,
    RelKind,
)

EV = Evidence(file="s/x", line=1, snippet="")


def shop() -> ArchitectureGraph:
    graph = ArchitectureGraph(
        [
            Node(id="S", kind=NodeKind.SYSTEM, name="shop", evidence=(EV,),
                 description=Inference(text="Loja online", confidence=0.9, evidence=(EV,))),
            Node(id="orders", kind=NodeKind.CONTAINER, name="Orders.Api", parent_id="S",
                 evidence=(EV,), attributes={"language": "C#", "framework": ".NET 8.0",
                                             "entry-point:HTTP:/orders": "s/x:1"}),
            Node(id="parcels", kind=NodeKind.CONTAINER, name="Parcels.Api", parent_id="S",
                 evidence=(EV,)),
            Node(id="q", kind=NodeKind.QUEUE, name="jobs", evidence=(EV,)),
            Node(id="db", kind=NodeKind.DATA_STORE, name="orders-db", evidence=(EV,),
                 attributes={"engine": "mongodb", "collection:orders": "s/x:2"}),
        ]
    )  # fmt: skip
    for source, target, kind, label in [
        ("orders", "parcels", RelKind.PUBLISHES, "OrderCreated (RabbitMQ)"),
        ("orders", "db", RelKind.DEPENDS_ON, "reads/writes"),
        ("orders", "q", RelKind.PUBLISHES, "publishes"),
    ]:
        graph.add_relationship(
            Relationship(source_id=source, target_id=target, kind=kind, label=label, evidence=(EV,))
        )
    return graph


class FakeWriter:
    def __init__(self, draft: ProjectDraft | None) -> None:
        self.answer = draft
        self.requests: list[ProjectRequest] = []

    def draft(
        self,
        request: ProjectRequest,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> ProjectDraft | None:
        self.requests.append(request)
        return self.answer


def test_facts_are_numbered_and_answers_checked_against_them() -> None:
    writer = FakeWriter(
        ProjectDraft(
            problem="Vender online",
            goals=("Receber pedidos", " "),
            principles=(("Orientado a eventos", "F1"), ("Inventado", "F999"), ("Sem base", "X")),
            assumptions=("Pagamento no ato",),
            glossary=(("OrderCreated", "Pedido criado"), ("Invoice", "não está nos fatos")),
            confidence=1.4,
        )
    )
    graph = shop()

    write_project_context(graph, writer)

    [request] = writer.requests
    assert request.system == "shop"
    facts = "\n".join(request.facts)
    assert request.facts[0].startswith("F1: ")
    assert "system description: Loja online" in facts
    assert "container Orders.Api: C# / .NET 8.0" in facts
    assert "entry points of Orders.Api: HTTP /orders" in facts
    assert "messages: OrderCreated\n" in facts + "\n"  # not the queue's "publishes"
    assert "data orders-db (mongodb): orders" in facts
    context = graph.project_context("S")
    assert context is not None
    assert context.problem == "Vender online"
    assert context.goals == ("Receber pedidos",)
    fact_one = request.facts[0].removeprefix("F1: ")
    assert context.principles == (InferredItem(text="Orientado a eventos", basis=fact_one),)
    assert context.glossary == (GlossaryTerm(term="OrderCreated", meaning="Pedido criado"),)
    assert context.assumptions == ("Pagamento no ato",)
    assert context.confidence == 1.0


def test_without_writer_or_answer_nothing_is_inferred() -> None:
    graph = shop()
    write_project_context(graph, None)
    write_project_context(graph, FakeWriter(None))
    assert graph.project_context("S") is None


class FakeRetriever:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def search(self, question: str, limit: int = 5) -> list[Hit]:
        self.questions.append(question)
        piece = StoredPiece(
            id="p1", title="Visão", text="O Pacco entrega\nencomendas.", source="d/README.md:3"
        )
        return [Hit(score=0.8, piece=piece)]


def test_documentation_pieces_are_numbered_cited_and_traced() -> None:
    writer = FakeWriter(
        ProjectDraft(
            problem="Entregar encomendas",
            goals=(),
            principles=(("Baseado na visão", "D1"), ("Documento inexistente", "D9")),
            assumptions=(),
            glossary=(("encomendas", "Pacotes"),),
            confidence=0.6,
        )
    )
    retriever = FakeRetriever()
    graph = shop()

    traces = write_project_context(graph, writer, retriever=retriever)

    [request] = writer.requests
    assert request.documents == ("D1: [Visão — d/README.md:3] O Pacco entrega encomendas.",)
    assert len(retriever.questions) == 5
    assert [t.question for t in traces] == retriever.questions
    assert all(t.system == "shop" and len(t.hits) == 1 for t in traces)
    context = graph.project_context("S")
    assert context is not None
    assert context.principles == (
        InferredItem(text="Baseado na visão", basis="d/README.md:3 (Visão)"),
    )
    assert context.glossary == (GlossaryTerm(term="encomendas", meaning="Pacotes"),)  # from D1
    assert context.sources == ("d/README.md:3",)


def test_documentation_is_searched_in_the_chosen_language() -> None:
    pt, en = FakeRetriever(), FakeRetriever()
    write_project_context(shop(), FakeWriter(None), retriever=pt)
    write_project_context(shop(), FakeWriter(None), retriever=en, language=Language.EN)
    assert pt.questions[0] == "Qual problema de negócio o sistema resolve e para quem?"
    assert en.questions[0] == "What business problem does the system solve, and for whom?"
