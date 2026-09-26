"""Python projects feed the common architecture graph."""

import json
from pathlib import Path

from typer.testing import CliRunner

from exodus.main import app

FIXTURE = Path(__file__).parents[1] / "fixtures" / "python-shop"


def test_python_project_is_scanned_into_components_endpoints_and_dependencies(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(app, ["scan", str(FIXTURE), "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    graph = json.loads((tmp_path / "python-shop" / "graph.json").read_text())
    nodes = {node["id"]: node for node in graph["nodes"]}
    container = nodes["container:python-shop/shop-api"]
    assert container["technology"] == "Python / Python >=3.12"
    assert container["attributes"]["endpoint:/orders"] == "HTTP"
    assert container["attributes"]["entry-point:HTTP:/orders"] == "python-shop/src/shop/api.py:6"
    assert (
        container["attributes"]["entry-point:scheduled task:send_receipt"]
        == "python-shop/src/shop/tasks.py:4"
    )
    assert (
        container["attributes"]["entry-point:CLI command:sync"]
        == "python-shop/src/shop/management/commands/sync.py:6"
    )
    assert nodes["datastore:postgresql:db/shop"]["technology"] == "PostgreSQL"
    assert nodes["datastore:postgresql:db/shop"]["attributes"]["table:orders"] == (
        "python-shop/src/shop/repository.py:5"
    )
    assert "component:python-shop/shop-api/shop.api" in nodes
    relationships = {
        (relationship["source_id"], relationship["target_id"], relationship["kind"])
        for relationship in graph["relationships"]
    }
    assert relationships == {
        ("container:python-shop/shop-api", "datastore:postgresql:db/shop", "depends_on"),
        ("container:python-shop/shop-api", "external:payments", "calls"),
    }
