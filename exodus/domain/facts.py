"""Atomic facts emitted by extractors. Each one carries the evidence that originated it.

Extractors only see one file, so they emit facts; build_graph turns facts into nodes and links
them across projects.
"""

from enum import StrEnum

from pydantic import Field

from exodus.domain.model import Entity, Evidence, RelKind


class ProjectRole(StrEnum):
    APPLICATION = "application"  # deployable: a web app, service, worker or executable
    LIBRARY = "library"  # part of the applications that reference it
    TEST = "test"  # tests of the projects it references; not part of the architecture


class ProjectDeclared(Entity):
    """A project manifest (.csproj, pom.xml, ...). Its directory delimits its files; an
    application is a container, a library belongs to the applications referencing it."""

    name: str
    language: str
    framework: str | None
    evidence: Evidence
    role: ProjectRole = ProjectRole.APPLICATION


class SolutionEntry(Entity):
    """A project listed by a solution (.sln); path is relative to the solution."""

    name: str
    path: str
    evidence: Evidence


class SourceFileDetected(Entity):
    """A source file of a known language; used to infer the language of manifest-less projects."""

    language: str
    evidence: Evidence


class ModuleDeclared(Entity):
    """Namespace / package / module declared in a file."""

    name: str
    evidence: Evidence


class ClassDeclared(Entity):
    name: str
    evidence: Evidence


class ImportFound(Entity):
    module: str
    evidence: Evidence


class PackageDependency(Entity):
    name: str
    version: str
    evidence: Evidence


class ProjectReference(Entity):
    """Reference to another project by name (e.g. csproj ProjectReference)."""

    target: str
    evidence: Evidence


class DataSourceUsed(Entity):
    """A connection string / JDBC URL / DSN. engine_hint comes from config (e.g. providerName)."""

    raw: str
    evidence: Evidence
    name: str | None = None
    engine_hint: str | None = None


class EndpointExposed(Entity):
    """An HTTP/SOAP/WCF path served by the project (e.g. /BillingService.svc)."""

    path: str
    protocol: str
    evidence: Evidence


class EndpointCalled(Entity):
    url: str
    protocol: str
    evidence: Evidence


class EntryPoint(Entity):
    """A trigger that starts work in a container: HTTP/SOAP route, queue consumer, CLI command
    or scheduled job/task."""

    kind: str
    name: str
    evidence: Evidence


class TechnologyUsed(Entity):
    """A legacy technology identified in source or configuration."""

    name: str
    evidence: Evidence


class SecretFound(Entity):
    """A plaintext secret-like configuration value (the value is never retained)."""

    name: str
    evidence: Evidence


class QueueUsed(Entity):
    raw: str
    direction: RelKind  # PUBLISHES or CONSUMES
    evidence: Evidence


class ServiceDeclared(Entity):
    """The project runs as a service known by this name (service discovery, app settings) and,
    when known, listens on this port."""

    name: str
    evidence: Evidence
    port: int | None = None


class ServiceCalled(Entity):
    """A call to another service by its name (service discovery) or, when only that is known,
    by its port."""

    protocol: str
    evidence: Evidence
    service: str | None = None
    port: int | None = None


class ExchangeOwned(Entity):
    """The exchange/topic of a message broker where the project publishes its own messages."""

    name: str
    technology: str
    evidence: Evidence


class PlatformUsed(Entity):
    """A platform service the project relies on: service discovery, secrets, tracing, logging,
    metrics, message broker (Consul, Vault, Jaeger, Seq, Prometheus, RabbitMQ, ...)."""

    name: str
    evidence: Evidence


class MessageSent(Entity):
    """A message (event or command) the project sends to a broker exchange/topic."""

    exchange: str
    message: str
    evidence: Evidence


class MessageDeclared(Entity):
    """A message type routed to a broker exchange/topic (e.g. Convey's [Message("orders")]):
    consumed from there when subscribed; a command not subscribed is sent there."""

    message: str
    exchange: str
    evidence: Evidence
    is_command: bool = False


class MessagePublished(Entity):
    """A message the project publishes or sends by its type (MassTransit, NServiceBus, ...),
    without naming an exchange: it reaches the projects consuming that type."""

    message: str
    evidence: Evidence


class MessageConsumed(Entity):
    """A message the project subscribes to, from a broker exchange/topic (None: its own)."""

    message: str
    evidence: Evidence
    exchange: str | None = None


class ImageBuilt(Entity):
    """A container image built from a Dockerfile: its runtime base image and, when the file says
    so, the project it publishes/runs (the Dockerfile may live outside that project's folder)."""

    image: str
    evidence: Evidence
    project: str | None = None


class ComposeService(Entity):
    """A service of a docker-compose file and its image. Not owned by a project: it belongs to
    the container known by that service name, or else to the scanned system."""

    name: str
    image: str
    evidence: Evidence


class DataObjectUsed(Entity):
    """A table, stored procedure or document collection named in code or a SQL script."""

    kind: str  # "table" | "procedure" | "collection"
    name: str
    evidence: Evidence


class DocumentSection(Entity):
    """A piece of the legacy's written documentation (README, docs/): not architecture, it
    feeds the retrieval of the inferred sections and never becomes a node."""

    title: str
    text: str = Field(min_length=1)
    evidence: Evidence


type Fact = (
    ProjectDeclared
    | SourceFileDetected
    | ModuleDeclared
    | ClassDeclared
    | ImportFound
    | PackageDependency
    | ProjectReference
    | DataSourceUsed
    | EndpointExposed
    | EndpointCalled
    | EntryPoint
    | TechnologyUsed
    | SecretFound
    | QueueUsed
    | SolutionEntry
    | ServiceDeclared
    | ServiceCalled
    | ExchangeOwned
    | PlatformUsed
    | MessageSent
    | MessageDeclared
    | MessagePublished
    | MessageConsumed
    | ImageBuilt
    | ComposeService
    | DataObjectUsed
    | DocumentSection
)
