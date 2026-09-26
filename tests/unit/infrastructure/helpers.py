from collections.abc import Iterable
from pathlib import PurePosixPath

from exodus.application.ports import FactExtractor, SourceFile
from exodus.domain.facts import Fact
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence, Node, NodeKind, Relationship, RelKind


def extract(extractor: FactExtractor, path: str, text: str) -> list[Fact]:
    posix = PurePosixPath(path)
    assert extractor.matches(posix), f"{extractor} should match {path}"
    result: Iterable[Fact] = extractor.extract(SourceFile(path=posix, text=text))
    return list(result)


def ev(line: int) -> Evidence:
    return Evidence(file="s/web.config", line=line, snippet="")


def sample_graph() -> ArchitectureGraph:
    """Two systems sharing a database and a queue, a private database, an external API and
    two components."""
    g = ArchitectureGraph()
    for n in [
        Node(id="system:s", kind=NodeKind.SYSTEM, name="shop", evidence=(ev(1),)),
        Node(id="system:o", kind=NodeKind.SYSTEM, name="other", evidence=(ev(1),)),
        Node(
            id="container:s/web",
            kind=NodeKind.CONTAINER,
            name="Web",
            evidence=(ev(1),),
            parent_id="system:s",
            technology="C# / .NET Framework 4.0",
            attributes={
                "package:log4net": "1.2",
                "endpoint:/Default.aspx": "HTTP",
                "unresolved-datasource:X": "???",
            },
        ),
        Node(
            id="container:o/api",
            kind=NodeKind.CONTAINER,
            name="Api",
            evidence=(ev(1),),
            parent_id="system:o",
        ),
        Node(
            id="component:s/web/Shop.Web",
            kind=NodeKind.COMPONENT,
            name="Shop.Web",
            evidence=(ev(2),),
            parent_id="container:s/web",
            attributes={"class:Home": "f"},
        ),
        Node(
            id="component:s/web/Shop.Core",
            kind=NodeKind.COMPONENT,
            name="Shop.Core",
            evidence=(ev(2),),
            parent_id="container:s/web",
        ),
        Node(
            id="datastore:sqlserver:db/erp",
            kind=NodeKind.DATA_STORE,
            name="erp",
            evidence=(ev(3),),
            technology="SQL Server",
            attributes={"host": "db"},
        ),
        Node(
            id="datastore:mysql:m/local",
            kind=NodeKind.DATA_STORE,
            name="local",
            evidence=(ev(3),),
            technology="MySQL",
        ),
        Node(
            id="queue:msmq:q", kind=NodeKind.QUEUE, name="q", evidence=(ev(4),), technology="MSMQ"
        ),
        Node(
            id="external:api.x.com",
            kind=NodeKind.EXTERNAL_SYSTEM,
            name="api.x.com",
            evidence=(ev(5),),
            attributes={"url:https://api.x.com/v1": "HTTPS"},
        ),
    ]:
        g.add_node(n)
    for src, tgt, kind, label in [
        ("container:s/web", "datastore:sqlserver:db/erp", RelKind.DEPENDS_ON, "reads/writes"),
        ("container:o/api", "datastore:sqlserver:db/erp", RelKind.DEPENDS_ON, "reads/writes"),
        ("container:s/web", "datastore:mysql:m/local", RelKind.DEPENDS_ON, "reads/writes"),
        ("container:s/web", "queue:msmq:q", RelKind.PUBLISHES, "publishes"),
        ("container:o/api", "queue:msmq:q", RelKind.CONSUMES, "consumes"),
        ("container:s/web", "container:o/api", RelKind.CALLS, "SOAP"),
        ("container:s/web", "external:api.x.com", RelKind.CALLS, "HTTPS"),
        ("component:s/web/Shop.Web", "component:s/web/Shop.Core", RelKind.DEPENDS_ON, "imports"),
    ]:
        g.add_relationship(
            Relationship(source_id=src, target_id=tgt, kind=kind, label=label, evidence=(ev(9),))
        )
    return g
