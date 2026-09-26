from exodus.domain.graph import ArchitectureGraph
from exodus.domain.migration import plan_migration
from exodus.domain.model import Evidence, Node, NodeKind, Relationship, RelKind

EV = Evidence(file="s/x", line=1, snippet="")


def node(node_id: str, kind: NodeKind, parent: str | None = None, **attributes: str) -> Node:
    return Node(
        id=node_id, kind=kind, name=node_id, evidence=(EV,), parent_id=parent, attributes=attributes
    )


def app(node_id: str, language: str, framework: str, **attributes: str) -> Node:
    return node(
        node_id,
        NodeKind.CONTAINER,
        "S",
        language=language,
        framework=framework,
        **{"entry-point:HTTP:/": "s/x:1", **attributes},
    )


def rel(source: str, target: str, kind: RelKind = RelKind.CALLS, label: str = "HTTP") -> None:
    GRAPH.add_relationship(
        Relationship(source_id=source, target_id=target, kind=kind, label=label, evidence=(EV,))
    )


GRAPH = ArchitectureGraph()


def graph_of(*nodes: Node) -> ArchitectureGraph:
    global GRAPH
    GRAPH = ArchitectureGraph([node("S", NodeKind.SYSTEM), *nodes])
    return GRAPH


def paths(graph: ArchitectureGraph) -> dict[str, tuple[str, str, str, str]]:
    return {
        plan.container_id: (
            plan.fast.strategy,
            plan.fast.target,
            plan.modern.strategy if plan.modern else "=",
            plan.modern.target if plan.modern else "=",
        )
        for plan in plan_migration(graph).containers
    }


def test_container_paths_follow_the_rules_table() -> None:
    graph = graph_of(
        app("wcf", "C#", ".NET Framework 4.0", **{"technology:WCF": "WCF"}),
        app("framework48", "C#", ".NET Framework 4.8"),
        app("core31", "C#", ".NET Core 3.1"),
        app("net8", "C#", ".NET 8.0"),
        app("ejb", "Java", "Java 17", **{"package:javax.ejb": "3.0"}),
        app("java8", "Java", "Java 8"),
        app("java21", "Java", "Java 21"),
        app("py2", "Python", "Python 2.7"),
        app("django", "Python", "Python >=3.12", **{"package:django": "3.2"}),
        app("py312", "Python", "Python >=3.12"),
        app("cobol", "COBOL", ""),
    )

    assert paths(graph) == {
        "wcf": ("Rehost", "EC2 Windows (IIS)", "Refactor", ".NET 8+ on ECS Fargate"),
        "framework48": ("Rehost", "EC2 Windows (IIS)", "Refactor", ".NET 8+ on ECS Fargate"),
        "core31": ("Replatform", "ECS Fargate", "Refactor", ".NET 8+ on ECS Fargate"),
        "net8": ("Replatform", "ECS Fargate", "=", "="),
        "ejb": (
            "Rehost",
            "EC2 (same application server)",
            "Refactor",
            "Spring Boot / Jakarta EE on ECS Fargate",
        ),
        "java8": ("Replatform", "ECS Fargate", "Refactor", "Java 21 on ECS Fargate"),
        "java21": ("Replatform", "ECS Fargate", "=", "="),
        "py2": ("Rehost", "EC2", "Refactor", "Current Python 3 on ECS Fargate"),
        "django": ("Replatform", "ECS Fargate", "Refactor", "Current Python 3 on ECS Fargate"),
        "py312": ("Replatform", "ECS Fargate", "=", "="),
        "cobol": ("No rule", "Evaluate", "=", "="),
    }
    wcf = plan_migration(graph).containers[0]
    assert wcf.fast.reason == ".NET Framework 4.0; WCF"
    assert wcf.modern is not None
    assert wcf.modern.reason == "WCF → ASP.NET Core / gRPC; .NET Framework → .NET 8+"


def test_retire_candidate_has_no_entry_point_nor_inbound_call() -> None:
    graph = graph_of(
        node("idle", NodeKind.CONTAINER, "S", language="C#", framework=".NET 8.0"),
        node("called", NodeKind.CONTAINER, "S", language="C#", framework=".NET 8.0"),
        node("caller", NodeKind.CONTAINER, "S", language="C#", framework=".NET 8.0"),
    )
    rel("caller", "called")
    candidates = {p.container_id for p in plan_migration(graph).containers if p.retire_candidate}
    assert candidates == {"idle", "caller"}


def test_infrastructure_is_mapped_by_engine_queue_technology_and_platform_name() -> None:
    graph = graph_of(
        node("db", NodeKind.DATA_STORE, engine="sqlserver"),
        node("docs", NodeKind.DATA_STORE, engine="mongodb"),
        node("lite", NodeKind.DATA_STORE, engine="sqlite"),
        node("queue:msmq:invoices", NodeKind.QUEUE),
        node("platform:consul", NodeKind.PLATFORM),
    )
    mapped = {p.node_id: (p.fast, p.modern) for p in plan_migration(graph).infrastructure}
    assert mapped["db"][0] == "Amazon RDS for SQL Server"
    assert mapped["db"][1].startswith("Amazon Aurora PostgreSQL")
    assert mapped["docs"] == ("Amazon DocumentDB", "Amazon DocumentDB")
    assert mapped["lite"] == ("No rule: evaluate", "No rule: evaluate")
    assert mapped["queue:msmq:invoices"] == (
        "No equivalent: stays on the rehosted VM",
        "Amazon SQS",
    )
    assert mapped["platform:consul"] == ("AWS Cloud Map", "Amazon ECS Service Connect")


def test_waves_foundation_then_called_before_callers_grouped_by_shared_data() -> None:
    graph = graph_of(
        app("web", "C#", ".NET 8.0"),
        app("api", "C#", ".NET 8.0"),
        app("worker", "C#", ".NET 8.0"),
        app("billing", "C#", ".NET Framework 4.0"),
        app("ping", "C#", ".NET 8.0"),
        app("pong", "C#", ".NET 8.0"),
        app("risky", "C#", ".NET Core 3.1"),
        app("edge", "C#", ".NET 8.0"),
        node("db", NodeKind.DATA_STORE, engine="sqlserver"),
        node("queue:msmq:jobs", NodeKind.QUEUE),
        node("platform:consul", NodeKind.PLATFORM),
        node("platform:rabbitmq", NodeKind.PLATFORM),
    )
    rel("web", "api")  # web goes after api
    rel("edge", "web")
    rel("edge", "api")  # the reason names only what holds edge in its wave
    rel("api", "db", RelKind.DEPENDS_ON, "reads/writes")
    rel("worker", "db", RelKind.DEPENDS_ON, "reads/writes")  # api + worker share db
    rel("web", "queue:msmq:jobs", RelKind.PUBLISHES, "publishes")
    rel("billing", "queue:msmq:jobs", RelKind.CONSUMES, "consumes")  # queue goes with billing
    rel("ping", "pong")
    rel("pong", "ping")  # mutual calls: one group
    rel("web", "platform:consul", RelKind.DEPENDS_ON, "uses")  # platform does not order
    rel("risky", "billing", RelKind.PUBLISHES, "Evt (RabbitMQ)")  # events do not order

    plan = plan_migration(graph)

    assert plan.foundation == ("platform:consul", "platform:rabbitmq")
    waves = [
        [(g.container_ids, g.store_ids, g.queue_ids) for g in wave.groups] for wave in plan.waves
    ]
    assert waves == [
        [
            (("api", "worker"), ("db",), ()),  # no HIGH risk first, then name
            (("ping", "pong"), (), ()),
            (("billing",), (), ("queue:msmq:jobs",)),  # unsupported runtimes: HIGH risk
            (("risky",), (), ()),
        ],
        [(("web",), (), ())],
        [(("edge",), (), ())],
    ]
    assert plan.waves[0].groups[0].reasons == ("share db",)
    assert plan.waves[0].groups[1].reasons == ("call each other: ping, pong",)
    assert plan.waves[1].groups[0].reasons == ("calls api (wave 1)",)
    assert plan.waves[2].groups[0].reasons == ("calls web (wave 2); +1 in earlier waves",)
