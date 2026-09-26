"""End-to-end over .NET Core microservices: a service laid out in layers (Api -> Application ->
Core) with a test project and a solution listing a repository that is not in the folder
(micro-shop), and services linked by HTTP calls by name, events, gateway routes, MongoDB and
platform services (micro-services)."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from typer.testing import CliRunner

from exodus.main import app

FIXTURES = Path(__file__).parents[1] / "fixtures"
runner = CliRunner()


def test_only_the_deployable_project_is_a_container(tmp_path: Path) -> None:
    result = runner.invoke(app, ["scan", str(FIXTURES / "micro-shop"), "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    graph = json.loads((tmp_path / "micro-shop/graph.json").read_text())
    nodes = {n["id"]: n for n in graph["nodes"]}
    [container] = [n for n in graph["nodes"] if n["kind"] == "container"]
    assert container["id"] == "container:micro-shop/orders-api"
    assert container["technology"] == "C# / .NET Core 3.1"
    assert container["attributes"]["test-project:Orders.Tests"] == (
        "micro-shop/Orders/tests/Orders.Tests/Orders.Tests.csproj"
    )
    components = {n["name"] for n in nodes.values() if n["kind"] == "component"}
    assert components == {"Orders.Api", "Orders.Application", "Orders.Core"}
    imports = {(r["source_id"], r["target_id"]) for r in graph["relationships"]}
    assert (
        "component:micro-shop/orders-api/Orders.Application",
        "component:micro-shop/orders-api/Orders.Core",
    ) in imports


def test_projects_listed_by_the_solution_but_missing_are_reported(tmp_path: Path) -> None:
    result = runner.invoke(app, ["scan", str(FIXTURES / "micro-shop"), "-o", str(tmp_path)])
    assert (
        "warning: micro-shop/MicroShop.sln lists 1 projects not found in micro-shop: Payments.Api "
        "(../Payments/src/Payments.Api/Payments.Api.csproj, line 10)"
    ) in result.output


def test_nothing_recognized_writes_nothing(tmp_path: Path) -> None:
    empty = tmp_path / "docs-only"
    empty.mkdir()
    (empty / "README.md").write_text("# nothing to scan")
    result = runner.invoke(app, ["scan", str(empty), "-o", str(tmp_path / "out")])
    assert result.exit_code == 1
    assert "warning: nothing recognized in docs-only" in result.output
    assert not (tmp_path / "out").exists()


def test_services_linked_by_http_names_events_gateway_routes_and_platform(tmp_path: Path) -> None:
    fixture = FIXTURES / "micro-services"
    scan = runner.invoke(app, ["scan", str(fixture), "-o", str(tmp_path)])
    assert scan.exit_code == 0, scan.output
    assert "no communication detected" not in scan.output
    graph = json.loads((tmp_path / "micro-services/graph.json").read_text())
    stores = {n["id"]: n for n in graph["nodes"] if n["kind"] == "data_store"}
    assert stores["datastore:mongodb:localhost/parcels-service"]["attributes"][
        "collection:parcels"
    ].endswith("ParcelsStore.cs:10")
    links = {
        (r["source_id"], r["target_id"], r["kind"], r["label"]) for r in graph["relationships"]
    }
    gateway, orders, parcels = (
        "container:micro-services/gateway",
        "container:micro-services/orders-api",
        "container:micro-services/parcels-api",
    )
    assert {
        (gateway, orders, "calls", "HTTP"),
        (orders, parcels, "calls", "HTTP"),
        (gateway, orders, "publishes", "CreateOrder (RabbitMQ)"),
        (orders, parcels, "publishes", "OrderCreated (RabbitMQ)"),
        (orders, "datastore:mongodb:localhost/orders-service", "depends_on", "reads/writes"),
        (orders, "platform:consul", "depends_on", "uses"),
        (parcels, "platform:rabbitmq", "depends_on", "uses"),
    } <= links
    render = runner.invoke(app, ["render", "--as-is", "-o", str(tmp_path)])
    assert render.exit_code == 0, render.output
    drawio = ET.parse(tmp_path / "micro-services/as-is/c4.drawio")
    [page] = [d for d in drawio.iter("diagram") if d.attrib["id"] == "container-micro-services"]
    ids = {c.attrib["id"] for c in page.iter() if "id" in c.attrib}
    assert {"platform", "platform:consul", "platform:rabbitmq"} <= ids
    assert "boundary:system:micro-services->platform" in ids
