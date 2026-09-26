"""Sections of the project documentation that need more than reading the graph as it is:
what drives the migration and what is still open for a person to confirm."""

from enum import StrEnum

from exodus.domain.graph import ArchitectureGraph
from exodus.domain.migration import NO_RULE, Strategy, plan_migration
from exodus.domain.model import Entity, Node, NodeKind
from exodus.domain.refactor import shared_databases
from exodus.domain.risks import Severity, assess_risks


class Question(StrEnum):
    UNRESOLVED_DATASOURCE = "unresolved data source"
    UNDETERMINED_DATABASE = "undetermined database"
    NO_AWS_TARGET = "no AWS target rule"
    NO_MIGRATION_RULE = "no migration rule"
    RETIRE_CANDIDATE = "retire candidate"


class OpenQuestion(Entity):
    """Something the extraction could not settle, about an element; worded by the renderer.

    detail is the data source, "<table|collection|procedure>:<name>", the engine or the reason.
    """

    kind: Question
    subject: str
    detail: str = ""


class Driver(Entity):
    """A HIGH risk that shapes the migration, with the elements it affects."""

    title: str
    detail: str
    where: tuple[str, ...]


def _containers(graph: ArchitectureGraph, system: Node) -> list[Node]:
    return graph.children(system.id, NodeKind.CONTAINER)


def drivers(graph: ArchitectureGraph, system: Node) -> list[Driver]:
    names = {c.id: c.name for c in _containers(graph, system)}
    grouped: dict[tuple[str, str], set[str]] = {}
    for risk in assess_risks(graph):
        if risk.severity is Severity.HIGH and risk.container_id in names:
            grouped.setdefault((risk.title, risk.detail), set()).add(names[risk.container_id])
    found = [
        Driver(title=title, detail=detail, where=tuple(sorted(where)))
        for (title, detail), where in grouped.items()
    ]
    for store_id in shared_databases(graph):
        systems = {
            s.name
            for r in graph.relationships()
            if r.target_id == store_id
            and (s := graph.ancestor(r.source_id, NodeKind.SYSTEM)) is not None
        }
        if len(systems) > 1 and system.name in systems:
            others = ", ".join(sorted(systems - {system.name}))
            found.append(
                Driver(
                    title="Shared database",
                    detail=f"shared with {others}",
                    where=(graph.node(store_id).name,),
                )
            )
    return found


def open_questions(graph: ArchitectureGraph, system: Node) -> list[OpenQuestion]:
    """What the extraction could not settle and a person has to confirm."""
    containers = _containers(graph, system)
    ids = {c.id for c in containers}
    questions: list[OpenQuestion] = []
    for c in containers:
        for key in c.attributes:
            if key.startswith("unresolved-datasource:"):
                name = key.removeprefix("unresolved-datasource:")
                questions.append(
                    OpenQuestion(kind=Question.UNRESOLVED_DATASOURCE, subject=c.name, detail=name)
                )
            elif key.startswith("undetermined-"):
                detail = key.removeprefix("undetermined-")
                questions.append(
                    OpenQuestion(kind=Question.UNDETERMINED_DATABASE, subject=c.name, detail=detail)
                )
    plan = plan_migration(graph)
    used = {
        r.target_id
        for r in graph.relationships()
        if (user := graph.ancestor(r.source_id, NodeKind.CONTAINER)) is not None and user.id in ids
    }
    for infra in plan.infrastructure:
        if infra.node_id in used and infra.fast == NO_RULE:
            node = graph.node(infra.node_id)
            kind = node.attributes.get("engine") or node.technology or node.kind.value
            questions.append(
                OpenQuestion(kind=Question.NO_AWS_TARGET, subject=node.name, detail=kind)
            )
    for path in plan.containers:
        if path.container_id not in ids:
            continue
        name = graph.node(path.container_id).name
        if path.fast.strategy is Strategy.NO_RULE:
            questions.append(
                OpenQuestion(kind=Question.NO_MIGRATION_RULE, subject=name, detail=path.fast.reason)
            )
        if path.retire_candidate:
            questions.append(OpenQuestion(kind=Question.RETIRE_CANDIDATE, subject=name))
    return questions
