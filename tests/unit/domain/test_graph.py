import pytest

from exodus.domain.graph import SCHEMA_VERSION, ArchitectureGraph, GraphDocument
from exodus.domain.model import (
    DomainError,
    Evidence,
    Node,
    NodeKind,
    Relationship,
    RelKind,
    UseCase,
    UseCaseStep,
)

E1 = Evidence(file="a/x.csproj", line=1, snippet="<Project>")
E2 = Evidence(file="a/web.config", line=7, snippet="<add>")


def system(node_id: str = "system:a", ev: Evidence = E1) -> Node:
    return Node(id=node_id, kind=NodeKind.SYSTEM, name=node_id, evidence=(ev,))


def container(node_id: str, parent: str = "system:a", **kw: str) -> Node:
    return Node(
        id=node_id,
        kind=NodeKind.CONTAINER,
        name=node_id,
        evidence=(E1,),
        parent_id=parent,
        attributes=dict(kw),
    )


def test_add_node_is_idempotent_and_merges_evidence_and_attributes() -> None:
    graph = ArchitectureGraph([system()])
    graph.add_node(container("c1", lang="C#"))
    merged = graph.add_node(
        Node(
            id="c1",
            kind=NodeKind.CONTAINER,
            name="c1",
            evidence=(E2,),
            parent_id="system:a",
            technology="ASP.NET",
            attributes={"lang": "VB", "extra": "1"},
        )
    )
    assert merged.evidence == (E1, E2)
    assert merged.attributes == {"lang": "C#", "extra": "1"}
    assert merged.technology == "ASP.NET"
    assert len(graph.nodes()) == 2


def test_add_node_rejects_kind_change() -> None:
    graph = ArchitectureGraph([system()])
    with pytest.raises(DomainError):
        graph.add_node(Node(id="system:a", kind=NodeKind.QUEUE, name="q", evidence=(E1,)))


def test_add_node_rejects_unknown_parent() -> None:
    with pytest.raises(DomainError):
        ArchitectureGraph([container("c1", parent="system:missing")])


def test_relationship_requires_existing_ends() -> None:
    graph = ArchitectureGraph([system()])
    with pytest.raises(DomainError):
        graph.add_relationship(
            Relationship(
                source_id="system:a",
                target_id="nope",
                kind=RelKind.CALLS,
                label="x",
                evidence=(E1,),
            )
        )


def test_self_relationship_is_rejected() -> None:
    graph = ArchitectureGraph([system()])
    with pytest.raises(DomainError):
        graph.add_relationship(
            Relationship(
                source_id="system:a",
                target_id="system:a",
                kind=RelKind.CALLS,
                label="x",
                evidence=(E1,),
            )
        )


def test_duplicate_relationship_merges_evidence() -> None:
    graph = ArchitectureGraph([system(), system("system:b")])
    graph.add_relationship(
        Relationship(
            source_id="system:a",
            target_id="system:b",
            kind=RelKind.CALLS,
            label="first",
            evidence=(E1,),
        )
    )
    graph.add_relationship(
        Relationship(
            source_id="system:a",
            target_id="system:b",
            kind=RelKind.CALLS,
            label="second",
            evidence=(E2,),
        )
    )
    graph.add_relationship(
        Relationship(
            source_id="system:a",
            target_id="system:b",
            kind=RelKind.DEPENDS_ON,
            label="dep",
            evidence=(E2,),
        )
    )
    calls = graph.relationships(RelKind.CALLS)
    assert len(calls) == 1
    assert calls[0].label == "first"
    assert calls[0].evidence == (E1, E2)
    assert len(graph.relationships()) == 2


def test_document_round_trip_through_json() -> None:
    graph = ArchitectureGraph([system(), system("system:b"), container("c1", lang="C#")])
    graph.add_relationship(
        Relationship(
            source_id="c1",
            target_id="system:b",
            kind=RelKind.CALLS,
            label="SOAP",
            evidence=(E1, E2),
        )
    )
    json_text = graph.to_document().model_dump_json()

    restored = ArchitectureGraph.from_document(GraphDocument.model_validate_json(json_text))

    assert restored.nodes() == graph.nodes()
    assert restored.relationships() == graph.relationships()
    assert GraphDocument.model_validate_json(json_text).schema_version == SCHEMA_VERSION


def test_rejects_incompatible_schema_version() -> None:
    with pytest.raises(DomainError):
        ArchitectureGraph.from_document(GraphDocument(schema_version="2.0"))


def use_case(container_id: str = "c1", touches: tuple[str, ...] = ()) -> UseCase:
    return UseCase(
        container_id=container_id,
        trigger_kind="HTTP",
        trigger="/orders",
        entry=E2,
        title="Place order",
        steps=(UseCaseStep(text="Validates the order", evidence=E2),),
        touches=touches,
        confidence=0.7,
    )


def test_add_use_case_requires_existing_container_and_touched_nodes() -> None:
    graph = ArchitectureGraph([system(), container("c1")])
    with pytest.raises(DomainError):
        graph.add_use_case(use_case("missing"))
    with pytest.raises(DomainError):
        graph.add_use_case(use_case(touches=("datastore:none",)))
    graph.add_use_case(use_case(touches=("system:a",)))
    graph.add_use_case(use_case(touches=("system:a",)))  # same trigger replaces
    assert graph.use_cases() == [use_case(touches=("system:a",))]


def test_use_cases_round_trip_through_json_and_old_documents_load() -> None:
    graph = ArchitectureGraph([system(), container("c1")])
    graph.add_use_case(use_case())
    restored = ArchitectureGraph.from_document(
        GraphDocument.model_validate_json(graph.to_document().model_dump_json())
    )
    assert restored.use_cases() == graph.use_cases()
    old = GraphDocument.model_validate_json('{"schema_version": "1.3", "nodes": []}')
    assert ArchitectureGraph.from_document(old).use_cases() == []
