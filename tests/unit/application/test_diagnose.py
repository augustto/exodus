from exodus.application.use_cases.diagnose import diagnose_graph
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence, Node, NodeKind, Relationship, RelKind


def ev(file: str, line: int = 1) -> Evidence:
    return Evidence(file=file, line=line, snippet="")


def test_a_system_whose_containers_do_not_communicate_is_reported() -> None:
    graph = ArchitectureGraph()
    graph.add_node(Node(id="system:p", kind=NodeKind.SYSTEM, name="p", evidence=(ev("p"),)))
    for name in ("a", "b"):
        graph.add_node(Node(id=f"container:p/{name}", kind=NodeKind.CONTAINER, name=name,
                            evidence=(ev(name),), parent_id="system:p"))  # fmt: skip
    [warning] = diagnose_graph(graph)
    assert warning.startswith("p: 2 containers but no communication detected")
    graph.add_relationship(
        Relationship(source_id="container:p/a", target_id="container:p/b", kind=RelKind.CALLS,
                     label="HTTP", evidence=(ev("a"),))
    )  # fmt: skip
    assert diagnose_graph(graph) == []
