"""ArchitectureGraph: the aggregate that holds nodes and relationships and keeps them consistent."""

from collections.abc import Iterable

from pydantic import Field

from exodus.domain.model import (
    DomainError,
    Entity,
    Node,
    NodeKind,
    ProjectContext,
    RefactorPlan,
    Relationship,
    RelKind,
    UseCase,
    merge_evidence,
)

SCHEMA_VERSION = "1.7"  # 1.4: use cases; 1.5: refactor; 1.6: project context; 1.7: its sources


class GraphDocument(Entity):
    """Serializable snapshot of the graph (the shape of graph.json)."""

    schema_version: str = SCHEMA_VERSION
    nodes: list[Node] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    use_cases: list[UseCase] = Field(default_factory=list)
    refactor: RefactorPlan | None = None
    project_contexts: list[ProjectContext] = Field(default_factory=list)


class ArchitectureGraph:
    def __init__(
        self,
        nodes: Iterable[Node] = (),
        relationships: Iterable[Relationship] = (),
        use_cases: Iterable[UseCase] = (),
        refactor: RefactorPlan | None = None,
        project_contexts: Iterable[ProjectContext] = (),
    ) -> None:
        self._nodes: dict[str, Node] = {}
        self._relationships: dict[tuple[str, str, RelKind], Relationship] = {}
        self._use_cases: dict[tuple[str, str, str], UseCase] = {}
        for node in nodes:
            self.add_node(node)
        for relationship in relationships:
            self.add_relationship(relationship)
        for use_case in use_cases:
            self.add_use_case(use_case)
        self.refactor: RefactorPlan | None = None
        if refactor is not None:
            self.set_refactor(refactor)
        self._contexts: dict[str, ProjectContext] = {}
        for project_context in project_contexts:
            self.set_project_context(project_context)

    def add_node(self, node: Node) -> Node:
        """Add a node; re-adding the same id merges evidence and attributes (first values win)."""
        if node.parent_id is not None and node.parent_id not in self._nodes:
            raise DomainError(f"parent {node.parent_id} of {node.id} is not in the graph")
        existing = self._nodes.get(node.id)
        if existing is None:
            self._nodes[node.id] = node
            return node
        if existing.kind != node.kind:
            raise DomainError(
                f"node {node.id} already exists as {existing.kind}, cannot re-add as {node.kind}"
            )
        merged = existing.model_copy(
            update={
                "evidence": merge_evidence(existing.evidence, node.evidence),
                "parent_id": existing.parent_id or node.parent_id,
                "technology": existing.technology or node.technology,
                "attributes": {**node.attributes, **existing.attributes},
                "description": node.description or existing.description,
            }
        )
        self._nodes[node.id] = merged
        return merged

    def add_relationship(self, relationship: Relationship) -> Relationship:
        """Add a relationship; same (source, target, kind) merges evidence (first label wins)."""
        for end in (relationship.source_id, relationship.target_id):
            if end not in self._nodes:
                raise DomainError(f"relationship end {end} is not in the graph")
        if relationship.source_id == relationship.target_id:
            raise DomainError(f"self relationship on {relationship.source_id} is not allowed")
        existing = self._relationships.get(relationship.key)
        if existing is not None:
            relationship = existing.model_copy(
                update={"evidence": merge_evidence(existing.evidence, relationship.evidence)}
            )
        self._relationships[relationship.key] = relationship
        return relationship

    def add_use_case(self, use_case: UseCase) -> UseCase:
        """Add a use case; one with the same container and trigger replaces it."""
        for node_id in (use_case.container_id, *use_case.touches):
            if node_id not in self._nodes:
                raise DomainError(f"use case node {node_id} is not in the graph")
        self._use_cases[use_case.key] = use_case
        return use_case

    def set_refactor(self, plan: RefactorPlan) -> None:
        """Keep the refactor plan; every element it names must be in the graph."""
        missing = sorted(i for i in plan.node_ids() if i not in self._nodes)
        if missing:
            raise DomainError(f"refactor plan names elements not in the graph: {missing}")
        self.refactor = plan

    def set_project_context(self, context: ProjectContext) -> None:
        """Keep the inferred context of a system (one per system: a new one replaces it)."""
        system = self._nodes.get(context.system_id)
        if system is None or system.kind is not NodeKind.SYSTEM:
            raise DomainError(f"project context of {context.system_id}: not a system")
        self._contexts[context.system_id] = context

    def project_context(self, system_id: str) -> ProjectContext | None:
        return self._contexts.get(system_id)

    def get(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def node(self, node_id: str) -> Node:
        found = self._nodes.get(node_id)
        if found is None:
            raise DomainError(f"node {node_id} is not in the graph")
        return found

    def nodes(self, kind: NodeKind | None = None) -> list[Node]:
        return [n for n in self._nodes.values() if kind is None or n.kind == kind]

    def children(self, parent_id: str, kind: NodeKind | None = None) -> list[Node]:
        return [n for n in self.nodes(kind) if n.parent_id == parent_id]

    def ancestor(self, node_id: str, kind: NodeKind) -> Node | None:
        """The node itself or its closest ancestor of the given kind."""
        current: Node | None = self.node(node_id)
        while current is not None:
            if current.kind == kind:
                return current
            current = self._nodes.get(current.parent_id) if current.parent_id else None
        return None

    def relationships(self, kind: RelKind | None = None) -> list[Relationship]:
        return [r for r in self._relationships.values() if kind is None or r.kind == kind]

    def use_cases(self) -> list[UseCase]:
        return list(self._use_cases.values())

    def to_document(self) -> GraphDocument:
        return GraphDocument(
            nodes=self.nodes(),
            relationships=self.relationships(),
            use_cases=self.use_cases(),
            refactor=self.refactor,
            project_contexts=list(self._contexts.values()),
        )

    @classmethod
    def from_document(cls, document: GraphDocument) -> "ArchitectureGraph":
        major = document.schema_version.split(".", 1)[0]
        if major != SCHEMA_VERSION.split(".", 1)[0]:
            raise DomainError(
                f"unsupported schema version {document.schema_version} (expected {SCHEMA_VERSION})"
            )
        return cls(
            document.nodes,
            document.relationships,
            document.use_cases,
            document.refactor,
            document.project_contexts,
        )
