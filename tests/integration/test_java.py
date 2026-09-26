"""Java fixture produces the same graph vocabulary as the .NET readers."""

import json
from pathlib import Path

from typer.testing import CliRunner

from exodus.main import app

FIXTURE = Path(__file__).parents[1] / "fixtures" / "java-shop"


def test_java_project_is_scanned_into_components_endpoints_and_dependencies(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["scan", str(FIXTURE), "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    graph = json.loads((tmp_path / "java-shop" / "graph.json").read_text())
    nodes = {node["id"]: node for node in graph["nodes"]}
    container = nodes["container:java-shop/orders-api"]
    assert container["technology"] == "Java / Java 17"
    assert container["attributes"]["endpoint:/orders"] == "HTTP"
    assert (
        container["attributes"]["entry-point:HTTP:/orders"]
        == "java-shop/src/main/java/com/acme/orders/OrdersController.java:5"
    )
    assert nodes["datastore:postgresql:db/orders"]["technology"] == "PostgreSQL"
    assert "component:java-shop/orders-api/com.acme.orders" in nodes
    relationships = {
        (rel["source_id"], rel["target_id"], rel["kind"]) for rel in graph["relationships"]
    }
    assert relationships == {
        ("container:java-shop/orders-api", "datastore:postgresql:db/orders", "depends_on"),
        ("container:java-shop/orders-api", "external:billing", "calls"),
    }
