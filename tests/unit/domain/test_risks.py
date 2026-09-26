from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence, Node, NodeKind, Relationship, RelKind
from exodus.domain.risks import Severity, assess_risks


def ev(file: str, line: int = 1) -> Evidence:
    return Evidence(file=file, line=line, snippet="evidence")


def test_assesses_legacy_stacks_packages_configuration_and_shared_data() -> None:
    graph = ArchitectureGraph(
        [
            Node(id="system:billing", kind=NodeKind.SYSTEM, name="billing", evidence=(ev("a"),)),
            Node(
                id="container:billing/web",
                kind=NodeKind.CONTAINER,
                name="web",
                parent_id="system:billing",
                technology="C# / .NET Framework 4.0",
                evidence=(ev("billing/Web.csproj"), ev("billing/Web.config", 8)),
                attributes={
                    "language": "C#",
                    "framework": ".NET Framework 4.0",
                    "package:Convey": "1.0.0",
                    "technology:WCF": "WCF",
                    "secret:ApiKey": "ApiKey",
                    "unresolved-datasource:Legacy": "Name=Legacy",
                },
            ),
            Node(id="system:orders", kind=NodeKind.SYSTEM, name="orders", evidence=(ev("b"),)),
            Node(
                id="container:orders/api",
                kind=NodeKind.CONTAINER,
                name="api",
                parent_id="system:orders",
                technology="Java / Java 8",
                evidence=(ev("orders/pom.xml"),),
                attributes={
                    "language": "Java",
                    "framework": "Java 8",
                    "package:javax.xml.ws:jaxws-api": "2.3.1",
                    "package:weblogic": "12.1",
                },
            ),
            Node(
                id="datastore:sqlserver:db/erp",
                kind=NodeKind.DATA_STORE,
                name="ERP",
                evidence=(ev("billing/Web.config", 3),),
            ),
        ],
        [
            Relationship(
                source_id="container:billing/web",
                target_id="datastore:sqlserver:db/erp",
                kind=RelKind.DEPENDS_ON,
                label="reads/writes",
                evidence=(ev("billing/Web.config", 3),),
            ),
            Relationship(
                source_id="container:orders/api",
                target_id="datastore:sqlserver:db/erp",
                kind=RelKind.DEPENDS_ON,
                label="reads/writes",
                evidence=(ev("orders/application.yml", 4),),
            ),
        ],
    )

    risks = assess_risks(graph)

    assert [(r.rule, r.severity) for r in risks] == [
        ("dotnet-unsupported-runtime", Severity.HIGH),
        ("dotnet-legacy-technology", Severity.HIGH),
        ("dotnet-abandoned-package", Severity.MEDIUM),
        ("secret-in-configuration", Severity.HIGH),
        ("unresolved-datasource", Severity.MEDIUM),
        ("java-unsupported-runtime", Severity.HIGH),
        ("java-legacy-api", Severity.HIGH),
        ("java-application-server", Severity.HIGH),
        ("shared-database", Severity.HIGH),
    ]
    assert risks[0].container_id == "container:billing/web"
    assert risks[-1].container_id is None
    assert risks[-1].evidence == (ev("billing/Web.config", 3), ev("orders/application.yml", 4))


def test_assesses_old_python_frameworks() -> None:
    graph = ArchitectureGraph(
        [
            Node(id="system:shop", kind=NodeKind.SYSTEM, name="shop", evidence=(ev("a"),)),
            Node(
                id="container:shop/api",
                kind=NodeKind.CONTAINER,
                name="api",
                parent_id="system:shop",
                evidence=(ev("shop/pyproject.toml"),),
                attributes={
                    "language": "Python",
                    "framework": "Python >=3.7",
                    "package:Django": "2.2.0",
                    "package:Flask": "1.0.4",
                },
            ),
        ]
    )

    risks = assess_risks(graph)

    assert [(r.rule, r.severity) for r in risks] == [
        ("python-unsupported-runtime", Severity.HIGH),
        ("python-unsupported-framework", Severity.HIGH),
        ("python-unsupported-framework", Severity.HIGH),
    ]
