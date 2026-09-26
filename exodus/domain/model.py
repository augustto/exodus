"""Core entities of the architecture graph.

Pydantic is allowed in the domain (see CLAUDE.md): entities are frozen models, so validation,
JSON serialization and JSON Schema come from the same definition. No IO or parsing here.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DomainError(ValueError):
    """Raised when an aggregate invariant is violated (entity field rules raise ValidationError)."""


class Entity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Evidence(Entity):
    """Where a fact came from: file (relative to the scanned roots' parent), line and snippet."""

    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    snippet: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


class Inference(Entity):
    """A conclusion generated from extracted evidence, never a replacement for it."""

    text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence: tuple[Evidence, ...] = Field(min_length=1)


class NodeKind(StrEnum):
    SYSTEM = "system"
    CONTAINER = "container"
    COMPONENT = "component"
    DATA_STORE = "data_store"
    QUEUE = "queue"
    EXTERNAL_SYSTEM = "external_system"
    PLATFORM = "platform"  # service discovery, secrets, tracing, logging, metrics, broker


class RelKind(StrEnum):
    CALLS = "calls"
    READS = "reads"
    WRITES = "writes"
    PUBLISHES = "publishes"
    CONSUMES = "consumes"
    DEPENDS_ON = "depends_on"


class Node(Entity):
    id: str = Field(min_length=1)
    kind: NodeKind
    name: str
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    parent_id: str | None = None
    technology: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    description: Inference | None = None


class Relationship(Entity):
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    kind: RelKind
    label: str
    evidence: tuple[Evidence, ...] = Field(min_length=1)

    @property
    def key(self) -> tuple[str, str, RelKind]:
        return (self.source_id, self.target_id, self.kind)


def merge_evidence(*groups: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    """Concatenate evidence groups, dropping duplicates while keeping first-seen order."""
    return tuple(dict.fromkeys(e for group in groups for e in group))


class UseCaseStep(Entity):
    text: str = Field(min_length=1)
    evidence: Evidence


class UseCase(Entity):
    """An inferred walk-through of what happens when an entry point is triggered. Every step
    cites the file and line it was read from; touches are ids of graph nodes it uses."""

    container_id: str = Field(min_length=1)
    trigger_kind: str
    trigger: str
    entry: Evidence
    title: str = Field(min_length=1)
    steps: tuple[UseCaseStep, ...] = Field(min_length=1)
    touches: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.container_id, self.trigger_kind, self.trigger)


class RefactorChoice(Entity):
    node_id: str
    piece_type: str
    option_id: str
    service: str
    justification: str
    confidence: float = Field(ge=0, le=1)
    inferred: bool = True  # False: the default option, no model decided


class Merge(Entity):
    source_id: str
    into_id: str
    justification: str


class SharedDataChoice(Entity):
    store_id: str
    option_id: str
    justification: str


class RefactorPlan(Entity):
    choices: tuple[RefactorChoice, ...] = ()
    merges: tuple[Merge, ...] = ()
    shared: tuple[SharedDataChoice, ...] = ()

    def node_ids(self) -> set[str]:
        ids = {c.node_id for c in self.choices} | {s.store_id for s in self.shared}
        return ids | {i for m in self.merges for i in (m.source_id, m.into_id)}


class InferredItem(Entity):
    """Something inferred, with the extracted fact it is based on."""

    text: str = Field(min_length=1)
    basis: str = ""


class GlossaryTerm(Entity):
    term: str = Field(min_length=1)
    meaning: str = Field(min_length=1)


class ProjectContext(Entity):
    """What the code cannot state about a system (why it exists, its goals, principles,
    assumptions and vocabulary), inferred by a model from the extracted facts."""

    system_id: str = Field(min_length=1)
    problem: str = ""
    goals: tuple[str, ...] = ()
    principles: tuple[InferredItem, ...] = ()
    assumptions: tuple[str, ...] = ()
    glossary: tuple[GlossaryTerm, ...] = ()
    confidence: float = Field(ge=0, le=1)
    sources: tuple[str, ...] = ()  # file:line of the written documentation consulted
