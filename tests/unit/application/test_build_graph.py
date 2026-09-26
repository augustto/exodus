from exodus.application.use_cases.build_graph import build_graph
from exodus.application.use_cases.scan_projects import ProjectScan
from exodus.domain.facts import (
    DataObjectUsed,
    DataSourceUsed,
    DocumentSection,
    EndpointCalled,
    EndpointExposed,
    ExchangeOwned,
    Fact,
    ImportFound,
    MessageConsumed,
    MessageDeclared,
    MessagePublished,
    MessageSent,
    ModuleDeclared,
    PackageDependency,
    ProjectDeclared,
    ProjectReference,
    ProjectRole,
    ServiceCalled,
    ServiceDeclared,
    SourceFileDetected,
)
from exodus.domain.model import Evidence, NodeKind, RelKind


def ev(file: str, line: int = 1) -> Evidence:
    return Evidence(file=file, line=line, snippet=f"snippet {file}:{line}")


def web_project() -> list[Fact]:
    return [
        ProjectDeclared(
            name="Billing.Web",
            language="C#",
            framework=".NET Framework 4.0",
            evidence=ev("billing/Web/Web.csproj"),
        ),
        PackageDependency(
            name="Newtonsoft.Json", version="6.0.8", evidence=ev("billing/Web/packages.config", 3)
        ),
    ]


def test_facts_outside_projects_go_to_root_container_with_majority_language() -> None:
    scan = ProjectScan(
        "portal",
        (
            SourceFileDetected(language="PHP", evidence=ev("portal/index.php")),
            SourceFileDetected(language="PHP", evidence=ev("portal/lib/db.php")),
            SourceFileDetected(language="JavaScript", evidence=ev("portal/app.js")),
        ),
    )
    graph = build_graph([scan])
    container = graph.node("container:portal/portal")
    assert container.technology == "PHP"
    assert container.parent_id == "system:portal"


def test_nearest_project_owns_the_fact() -> None:
    scan = ProjectScan(
        "sys",
        (
            ProjectDeclared(
                name="Outer", language="C#", framework=None, evidence=ev("sys/Outer.csproj")
            ),
            ProjectDeclared(
                name="Inner", language="C#", framework=None, evidence=ev("sys/inner/Inner.csproj")
            ),
            PackageDependency(
                name="Lib", version="1.0", evidence=ev("sys/inner/deep/packages.config")
            ),
        ),
    )
    graph = build_graph([scan])
    assert "package:Lib" in graph.node("container:sys/inner").attributes
    assert "package:Lib" not in graph.node("container:sys/outer").attributes


def test_project_reference_links_containers() -> None:
    scan = ProjectScan(
        "billing",
        (
            *web_project(),
            ProjectDeclared(
                name="Billing.Services",
                language="C#",
                framework=None,
                evidence=ev("billing/Svc/Svc.csproj"),
            ),
            ProjectReference(target="Billing.Services", evidence=ev("billing/Web/Web.csproj", 40)),
            ProjectReference(target="Missing.Project", evidence=ev("billing/Web/Web.csproj", 41)),
        ),
    )
    graph = build_graph([scan])
    [rel] = graph.relationships(RelKind.DEPENDS_ON)
    assert (rel.source_id, rel.target_id) == (
        "container:billing/billing-web",
        "container:billing/billing-services",
    )


def test_shared_database_is_a_single_node_used_by_both_systems() -> None:
    dotnet = ProjectScan(
        "billing",
        (
            *web_project(),
            DataSourceUsed(
                raw="Data Source=dbsrv01;Initial Catalog=ERP",
                evidence=ev("billing/Web/web.config", 5),
                name="ERP",
            ),
        ),
    )
    java = ProjectScan(
        "orders",
        (
            ProjectDeclared(
                name="orders-app",
                language="Java",
                framework="Java 6",
                evidence=ev("orders/pom.xml"),
            ),
            DataSourceUsed(
                raw="jdbc:sqlserver://DBSRV01:1433;databaseName=erp",
                evidence=ev("orders/db.properties"),
            ),
        ),
    )
    graph = build_graph([dotnet, java])
    [store] = graph.nodes(NodeKind.DATA_STORE)
    assert store.id == "datastore:sqlserver:dbsrv01/erp"
    assert store.technology == "SQL Server"
    users = {r.source_id for r in graph.relationships() if r.target_id == store.id}
    assert users == {"container:billing/billing-web", "container:orders/orders-app"}
    assert all(r.label == "reads/writes" for r in graph.relationships(RelKind.DEPENDS_ON))


def test_unresolved_datasource_is_kept_as_attribute() -> None:
    scan = ProjectScan(
        "billing",
        (
            *web_project(),
            DataSourceUsed(raw="???", evidence=ev("billing/Web/web.config"), name="Weird"),
        ),
    )
    graph = build_graph([scan])
    assert graph.nodes(NodeKind.DATA_STORE) == []
    assert (
        graph.node("container:billing/billing-web").attributes["unresolved-datasource:Weird"]
        == "billing/Web/web.config:1"
    )


def test_unresolved_datasource_does_not_store_raw_credential() -> None:
    canary = "audit-canary-123"
    scan = ProjectScan(
        "billing",
        (
            *web_project(),
            DataSourceUsed(raw=f"unknown:{canary}", name="Legacy", evidence=ev("billing/x")),
        ),
    )
    assert canary not in build_graph([scan]).to_document().model_dump_json()


def test_called_url_matches_endpoint_exposed_by_other_project() -> None:
    dotnet = ProjectScan(
        "billing",
        (
            ProjectDeclared(
                name="Billing.Services",
                language="C#",
                framework=None,
                evidence=ev("billing/Svc/Svc.csproj"),
            ),
            EndpointExposed(
                path="/BillingService.svc",
                protocol="SOAP",
                evidence=ev("billing/Svc/BillingService.svc"),
            ),
            EndpointExposed(
                path="/Default.aspx", protocol="HTTP", evidence=ev("billing/Svc/Default.aspx")
            ),
        ),
    )
    call = EndpointCalled(
        url="http://billing.intranet/billing/BillingService.svc",
        protocol="SOAP",
        evidence=ev("orders/Client.java", 9),
    )
    java = ProjectScan(
        "orders",
        (
            ProjectDeclared(
                name="orders", language="Java", framework=None, evidence=ev("orders/pom.xml")
            ),
            call,
        ),
    )
    graph = build_graph([dotnet, java])
    [rel] = graph.relationships(RelKind.CALLS)
    assert rel.source_id == "container:orders/orders"
    assert rel.target_id == "container:billing/billing-services"
    assert rel.label == "SOAP"
    assert rel.evidence == (ev("orders/Client.java", 9), ev("billing/Svc/BillingService.svc"))
    assert graph.nodes(NodeKind.EXTERNAL_SYSTEM) == []
    svc = graph.node("container:billing/billing-services")
    assert svc.attributes["endpoint:/BillingService.svc"] == "SOAP"


def test_most_specific_exposed_endpoint_wins() -> None:
    scan_a = ProjectScan(
        "a",
        (
            ProjectDeclared(name="a", language="Java", framework=None, evidence=ev("a/pom.xml")),
            EndpointExposed(path="/api/*", protocol="HTTP", evidence=ev("a/web.xml", 1)),
        ),
    )
    scan_b = ProjectScan(
        "b",
        (
            ProjectDeclared(name="b", language="Java", framework=None, evidence=ev("b/pom.xml")),
            EndpointExposed(path="/api/orders/*", protocol="HTTP", evidence=ev("b/web.xml", 1)),
        ),
    )
    caller = ProjectScan(
        "c",
        (
            ProjectDeclared(
                name="c", language="PHP", framework=None, evidence=ev("c/composer.json")
            ),
            EndpointCalled(url="http://x/api/orders/1", protocol="HTTP", evidence=ev("c/x.php")),
        ),
    )
    graph = build_graph([scan_a, scan_b, caller])
    assert [r.target_id for r in graph.relationships(RelKind.CALLS)] == ["container:b/b"]


def test_unmatched_call_becomes_external_system_and_self_calls_are_ignored() -> None:
    scan = ProjectScan(
        "billing",
        (
            ProjectDeclared(
                name="Web", language="C#", framework=None, evidence=ev("billing/Web.csproj")
            ),
            EndpointExposed(
                path="/Default.aspx", protocol="HTTP", evidence=ev("billing/Default.aspx")
            ),
            EndpointCalled(
                url="https://api.correios.com.br/cep/v1",
                protocol="HTTPS",
                evidence=ev("billing/web.config", 8),
            ),
            EndpointCalled(
                url="http://localhost/Default.aspx", protocol="HTTP", evidence=ev("billing/x.cs", 2)
            ),
            EndpointCalled(url="relative/path", protocol="HTTP", evidence=ev("billing/x.cs", 3)),
        ),
    )
    graph = build_graph([scan])
    [external] = graph.nodes(NodeKind.EXTERNAL_SYSTEM)
    assert external.id == "external:api.correios.com.br"
    assert external.attributes["url:https://api.correios.com.br"] == "HTTPS"
    [rel] = graph.relationships(RelKind.CALLS)
    assert (rel.source_id, rel.target_id) == ("container:billing/web", external.id)


def project(path: str, role: ProjectRole, *refs: str) -> list[Fact]:
    """A .NET project at path (folder/Name.csproj) with the given role and references."""
    name = path.rsplit("/", 1)[-1].removesuffix(".csproj")
    facts: list[Fact] = [
        ProjectDeclared(
            name=name, language="C#", framework=".NET Core 3.1", role=role, evidence=ev(path)
        )
    ]
    facts += [ProjectReference(target=r, evidence=ev(path, 5 + i)) for i, r in enumerate(refs)]
    return facts


def module(file: str, name: str, *imports: str) -> list[Fact]:
    return [ModuleDeclared(name=name, evidence=ev(file, 3))] + [
        ImportFound(module=i, evidence=ev(file, 1)) for i in imports
    ]


def microservice() -> list[Fact]:
    """Orders.Api (web) -> Orders.Application -> Orders.Core, plus a test project."""
    return [
        *project("shop/Orders/Orders.Api/Orders.Api.csproj", ProjectRole.APPLICATION,
                 "Orders.Application"),
        *project("shop/Orders/Orders.Application/Orders.Application.csproj", ProjectRole.LIBRARY,
                 "Orders.Core"),
        *project("shop/Orders/Orders.Core/Orders.Core.csproj", ProjectRole.LIBRARY),
        *project("shop/Orders/Orders.Tests/Orders.Tests.csproj", ProjectRole.TEST, "Orders.Api"),
        *module("shop/Orders/Orders.Api/Program.cs", "Orders.Api", "Orders.Application"),
        *module("shop/Orders/Orders.Application/Handler.cs", "Orders.Application", "Orders.Core"),
        *module("shop/Orders/Orders.Core/Order.cs", "Orders.Core"),
        *module("shop/Orders/Orders.Tests/Test.cs", "Orders.Tests", "Orders.Api"),
        DataSourceUsed(raw="Server=db;Database=Orders", engine_hint="sqlserver",
                       evidence=ev("shop/Orders/Orders.Core/Repo.cs", 9)),
    ]  # fmt: skip


def test_libraries_become_part_of_the_application_that_references_them() -> None:
    graph = build_graph([ProjectScan("shop", tuple(microservice()))])
    [api] = graph.nodes(NodeKind.CONTAINER)
    assert api.id == "container:shop/orders-api"
    components = {c.name for c in graph.children(api.id, NodeKind.COMPONENT)}
    assert components == {"Orders.Api", "Orders.Application", "Orders.Core"}  # no test code
    kinds = {(r.source_id, r.target_id, r.label) for r in graph.relationships()}
    assert ("container:shop/orders-api", "datastore:sqlserver:db/orders", "reads/writes") in kinds
    assert (
        "component:shop/orders-api/Orders.Application",
        "component:shop/orders-api/Orders.Core",
        "imports",
    ) in kinds
    assert (
        api.attributes["test-project:Orders.Tests"]
        == "shop/Orders/Orders.Tests/Orders.Tests.csproj"
    )


def test_a_library_shared_by_two_applications_is_part_of_both() -> None:
    facts = [
        *project("shop/A/A.csproj", ProjectRole.APPLICATION, "Common"),
        *project("shop/B/B.csproj", ProjectRole.APPLICATION, "Common"),
        *project("shop/Common/Common.csproj", ProjectRole.LIBRARY),
        *module("shop/A/A.cs", "A", "Common"),
        *module("shop/Common/C.cs", "Common"),
    ]
    graph = build_graph([ProjectScan("shop", tuple(facts))])
    assert {c.id for c in graph.nodes(NodeKind.CONTAINER)} == {
        "container:shop/a", "container:shop/b",
    }  # fmt: skip
    assert graph.get("component:shop/a/Common") and graph.get("component:shop/b/Common")
    imports = {(r.source_id, r.target_id) for r in graph.relationships() if r.label == "imports"}
    assert imports == {("component:shop/a/A", "component:shop/a/Common")}  # same container first


def test_a_library_only_tests_use_is_test_support_not_a_container() -> None:
    facts = [
        *microservice(),
        *project("shop/Orders/Tests.Shared/Tests.Shared.csproj", ProjectRole.LIBRARY),
        *project("shop/Orders/Orders.E2E/Orders.E2E.csproj", ProjectRole.TEST, "Tests.Shared"),
        *module("shop/Orders/Tests.Shared/Fixture.cs", "Tests.Shared"),
    ]
    graph = build_graph([ProjectScan("shop", tuple(facts))])
    assert [c.id for c in graph.nodes(NodeKind.CONTAINER)] == ["container:shop/orders-api"]
    assert not graph.get("component:shop/tests-shared/Tests.Shared")


def test_a_layered_service_has_one_component_per_project_named_by_its_root_namespace() -> None:
    facts = [
        *microservice(),
        *module(
            "shop/Orders/Orders.Application/Commands/Create.cs",
            "Orders.Application.Commands.Handlers",
            "Orders.Core.Entities",
        ),
        *module("shop/Orders/Orders.Core/Entities/Order.cs", "Orders.Core.Entities"),
    ]
    graph = build_graph([ProjectScan("shop", tuple(facts))])
    components = graph.children("container:shop/orders-api", NodeKind.COMPONENT)
    assert {c.name for c in components} == {"Orders.Api", "Orders.Application", "Orders.Core"}
    handlers = graph.node("component:shop/orders-api/Orders.Application")
    assert ev("shop/Orders/Orders.Application/Commands/Create.cs", 3) in handlers.evidence
    imports = {(r.source_id, r.target_id) for r in graph.relationships() if r.label == "imports"}
    assert (
        "component:shop/orders-api/Orders.Application",
        "component:shop/orders-api/Orders.Core",
    ) in imports


def test_a_single_project_container_groups_namespaces_one_level_below_its_root() -> None:
    facts = [
        *project("shop/Legacy/Legacy.csproj", ProjectRole.APPLICATION),
        *module("shop/Legacy/Global.cs", "Legacy"),
        *module("shop/Legacy/Web/Controllers/Home.cs", "Legacy.Web.Controllers", "Legacy.Data"),
        *module("shop/Legacy/Web/Models/Cart.cs", "Legacy.Web.Models"),
        *module("shop/Legacy/Data/Repos/Carts.cs", "Legacy.Data.Repos"),
    ]
    graph = build_graph([ProjectScan("shop", tuple(facts))])
    names = {c.name for c in graph.children("container:shop/legacy", NodeKind.COMPONENT)}
    assert names == {"Legacy", "Legacy.Web", "Legacy.Data"}
    imports = {(r.source_id, r.target_id) for r in graph.relationships() if r.label == "imports"}
    assert imports == {("component:shop/legacy/Legacy.Web", "component:shop/legacy/Legacy.Data")}


def service(folder: str, name: str, port: int) -> list[Fact]:
    """An application project known by service discovery as `name`, listening on `port`."""
    return [
        *project(f"{folder}/{folder.rsplit('/', 1)[-1]}.csproj", ProjectRole.APPLICATION),
        ServiceDeclared(name=name, port=port, evidence=ev(f"{folder}/appsettings.json", 3)),
    ]


def test_services_call_each_other_by_name_or_port() -> None:
    facts = [
        *service("shop/Orders", "orders-service", 5006),
        *service("shop/Parcels", "parcels-service", 5007),
        *service("shop/Gateway", "gateway", 5000),
        ServiceCalled(service="parcels-service", protocol="HTTP",
                      evidence=ev("shop/Orders/appsettings.json", 8)),
        ServiceCalled(port=5006, protocol="HTTP", evidence=ev("shop/Gateway/ocelot.json", 9)),
        ServiceCalled(service="billing-service", protocol="HTTP",
                      evidence=ev("shop/Orders/appsettings.json", 8)),
    ]  # fmt: skip
    graph = build_graph([ProjectScan("shop", tuple(facts))])
    calls = {(r.source_id, r.target_id, r.label) for r in graph.relationships(RelKind.CALLS)}
    assert calls == {
        ("container:shop/orders", "container:shop/parcels", "HTTP"),
        ("container:shop/gateway", "container:shop/orders", "HTTP"),
        ("container:shop/orders", "external:billing-service", "HTTP"),
    }
    [to_parcels] = [r for r in graph.relationships() if r.target_id == "container:shop/parcels"]
    assert ev("shop/Parcels/appsettings.json", 3) in to_parcels.evidence  # both ends traced
    assert graph.node("container:shop/orders").attributes["service:orders-service"] == "5006"


def exchange(folder: str, name: str) -> ExchangeOwned:
    return ExchangeOwned(
        name=name, technology="RabbitMQ", evidence=ev(f"{folder}/appsettings.json", 14)
    )


def test_messages_link_who_sends_them_to_who_consumes_them() -> None:
    facts = [
        *service("shop/Orders", "orders-service", 5006), exchange("shop/Orders", "orders"),
        *service("shop/Deliveries", "deliveries-service", 5003),
        exchange("shop/Deliveries", "deliveries"),
        *service("shop/Maker", "maker-service", 5015),
        *service("shop/Gateway", "gateway", 5000),
        # deliveries consumes two events of orders
        MessageDeclared(message="OrderApproved", exchange="orders",
                        evidence=ev("shop/Deliveries/Events/OrderApproved.cs", 7)),
        MessageConsumed(message="OrderApproved", evidence=ev("shop/Deliveries/Ext.cs", 20)),
        MessageDeclared(message="OrderCanceled", exchange="orders",
                        evidence=ev("shop/Deliveries/Events/OrderCanceled.cs", 7)),
        MessageConsumed(message="OrderCanceled", evidence=ev("shop/Deliveries/Ext.cs", 21)),
        # orders consumes its own commands, sent by the maker and by the gateway
        MessageConsumed(message="ApproveOrder", evidence=ev("shop/Orders/Ext.cs", 30)),
        MessageDeclared(message="ApproveOrder", exchange="orders", is_command=True,
                        evidence=ev("shop/Maker/Commands/ApproveOrder.cs", 7)),
        # an event type routed to orders that the maker neither subscribes nor sends
        MessageDeclared(message="OrderDeleted", exchange="orders",
                        evidence=ev("shop/Maker/Events/OrderDeleted.cs", 7)),
        MessageSent(exchange="orders", message="CreateOrder",
                    evidence=ev("shop/Gateway/ntrada.yml", 40)),
        # an exchange nobody owns becomes a queue node
        MessageDeclared(message="LegacyPing", exchange="legacy",
                        evidence=ev("shop/Orders/Events/LegacyPing.cs", 7)),
        MessageConsumed(message="LegacyPing", evidence=ev("shop/Orders/Ext.cs", 31)),
    ]  # fmt: skip
    graph = build_graph([ProjectScan("shop", tuple(facts))])
    sent = {(r.source_id, r.target_id, r.label) for r in graph.relationships(RelKind.PUBLISHES)}
    assert sent == {
        ("container:shop/orders", "container:shop/deliveries",
         "OrderApproved, OrderCanceled (RabbitMQ)"),
        ("container:shop/maker", "container:shop/orders", "ApproveOrder (RabbitMQ)"),
        ("container:shop/gateway", "container:shop/orders", "CreateOrder (RabbitMQ)"),
    }  # fmt: skip
    [legacy] = graph.relationships(RelKind.CONSUMES)
    assert (legacy.source_id, legacy.target_id) == (
        "container:shop/orders",
        "queue:rabbitmq:legacy",
    )
    [to_deliveries] = [r for r in graph.relationships(RelKind.PUBLISHES)
                       if r.target_id == "container:shop/deliveries"]  # fmt: skip
    assert ev("shop/Orders/appsettings.json", 14) in to_deliveries.evidence  # the owned exchange
    assert ev("shop/Deliveries/Ext.cs", 20) in to_deliveries.evidence  # the subscription


def test_messages_without_exchange_routing_link_publishers_and_consumers_by_type() -> None:
    def bus_service(folder: str) -> list[Fact]:
        return [
            *project(f"{folder}/{folder.rsplit('/', 1)[-1]}.csproj", ProjectRole.APPLICATION),
            PackageDependency(name="MassTransit.RabbitMQ", version="7.0.0",
                              evidence=ev(f"{folder}/{folder.rsplit('/', 1)[-1]}.csproj", 9)),
        ]  # fmt: skip

    facts = [
        *bus_service("shop/Sales"),
        *bus_service("shop/Billing"),
        MessagePublished(message="OrderSubmitted", evidence=ev("shop/Sales/Checkout.cs", 12)),
        MessageConsumed(message="OrderSubmitted", evidence=ev("shop/Billing/Consumer.cs", 3)),
        MessageConsumed(message="Unpublished", evidence=ev("shop/Billing/Other.cs", 3)),
    ]
    graph = build_graph([ProjectScan("shop", tuple(facts))])
    [link] = graph.relationships(RelKind.PUBLISHES)
    assert (link.source_id, link.target_id, link.label) == (
        "container:shop/sales", "container:shop/billing", "OrderSubmitted (MassTransit)",
    )  # fmt: skip


def test_tables_and_collections_go_to_the_database_of_their_family() -> None:
    facts = [
        *web_project(),
        DataSourceUsed(raw="Server=db01;Database=ERP", engine_hint="sqlserver",
                       evidence=ev("billing/Web/web.config", 5)),
        DataSourceUsed(raw="mongodb://mongo/docs", evidence=ev("billing/Web/web.config", 6)),
        DataObjectUsed(kind="table", name="Invoices", evidence=ev("billing/Web/Repo.cs", 3)),
        DataObjectUsed(kind="table", name="Invoices", evidence=ev("billing/Web/Repo.cs", 9)),
        DataObjectUsed(kind="procedure", name="usp_Close", evidence=ev("billing/Web/Repo.cs", 4)),
        DataObjectUsed(kind="collection", name="orders", evidence=ev("billing/Web/Mongo.cs", 2)),
    ]  # fmt: skip
    graph = build_graph([ProjectScan("billing", tuple(facts))])
    erp = graph.node("datastore:sqlserver:db01/erp").attributes
    assert erp["table:Invoices"] == "billing/Web/Repo.cs:3, billing/Web/Repo.cs:9"
    assert erp["procedure:usp_Close"] == "billing/Web/Repo.cs:4"
    assert "collection:orders" not in erp
    assert graph.node("datastore:mongodb:mongo/docs").attributes["collection:orders"] == (
        "billing/Web/Mongo.cs:2"
    )


def test_table_of_a_container_with_no_or_several_databases_is_undetermined() -> None:
    facts = [
        *web_project(),
        DataSourceUsed(raw="Server=db01;Database=ERP", engine_hint="sqlserver",
                       evidence=ev("billing/Web/web.config", 5)),
        DataSourceUsed(raw="Server=db01;Database=CRM", engine_hint="sqlserver",
                       evidence=ev("billing/Web/web.config", 6)),
        DataObjectUsed(kind="table", name="Invoices", evidence=ev("billing/Web/Repo.cs", 3)),
        DataObjectUsed(kind="collection", name="orders", evidence=ev("billing/Web/Mongo.cs", 2)),
    ]  # fmt: skip
    graph = build_graph([ProjectScan("billing", tuple(facts))])
    container = graph.node("container:billing/billing-web").attributes
    assert container["undetermined-table:Invoices"] == "billing/Web/Repo.cs:3"
    assert container["undetermined-collection:orders"] == "billing/Web/Mongo.cs:2"
    assert "table:Invoices" not in graph.node("datastore:sqlserver:db01/erp").attributes


def test_written_documentation_never_becomes_part_of_the_architecture() -> None:
    readme = DocumentSection(title="Billing", text="What it does", evidence=ev("billing/README.md"))
    graph = build_graph([ProjectScan("billing", (*web_project(), readme))])
    assert [n.id for n in graph.nodes(NodeKind.CONTAINER)] == ["container:billing/billing-web"]
    assert build_graph([ProjectScan("docs-only", (readme,))]).nodes() == []
