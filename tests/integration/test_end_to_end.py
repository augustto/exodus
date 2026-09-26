"""End-to-end: `exodus scan` + `exodus render --as-is` over the tiny .NET fixture."""

import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from typer.testing import CliRunner

from exodus.main import app

FIXTURES = Path(__file__).parents[1] / "fixtures"
runner = CliRunner()


@pytest.fixture(scope="module")
def output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("exodus-output")
    scan = runner.invoke(app, ["scan", str(FIXTURES / "tiny-shop"), "-o", str(out)])
    assert scan.exit_code == 0, scan.output
    assert scan.output.rstrip().splitlines()[-1].startswith("Total processing time: ")
    render = runner.invoke(app, ["render", "--as-is", "-o", str(out)])
    assert render.exit_code == 0, render.output
    assert render.output.rstrip().splitlines()[-1].startswith("Total processing time: ")
    return out / "tiny-shop"


@pytest.fixture(scope="module")
def graph(output: Path) -> dict:  # type: ignore[type-arg]
    return json.loads((output / "graph.json").read_text())  # type: ignore[no-any-return]


WEB, API = "container:tiny-shop/web", "container:tiny-shop/api"


def test_outputs_are_written(output: Path) -> None:
    for name in ["graph.json", "graph.schema.json", "inventory.md", "risks.md", "migration.md",
                 "as-is/c4.drawio"]:  # fmt: skip
        assert (output / name).is_file(), name
    drawio = ET.parse(output / "as-is/c4.drawio")
    assert [d.attrib["id"] for d in drawio.iter("diagram")] == [
        "context", "container-tiny-shop", "component-tiny-shop-api", "component-tiny-shop-web",
    ]  # fmt: skip


def test_projects_are_linked_through_the_service_call_and_the_shared_database(
    graph: dict,  # type: ignore[type-arg]
) -> None:
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes[WEB]["technology"] == nodes[API]["technology"] == "C# / .NET Framework 4.0"
    assert nodes[API]["attributes"]["endpoint:/Orders.svc"] == "SOAP"
    database = "datastore:sqlserver:dbsrv/shop"
    rels = {(r["source_id"], r["target_id"], r["kind"]) for r in graph["relationships"]}
    assert rels == {
        (WEB, API, "calls"),
        (WEB, database, "depends_on"),
        (API, database, "depends_on"),
        (WEB, "external:reports.intranet", "calls"),
    }


def test_inventory_lists_entry_points(output: Path) -> None:
    inventory = (output / "inventory.md").read_text()
    assert "**Entry points**" in inventory
    assert "| SOAP | /Orders.svc | " in inventory
    assert "Orders.svc:1 |" in inventory


def test_every_node_and_relationship_is_traceable_to_a_real_line(graph: dict) -> None:  # type: ignore[type-arg]
    for item in graph["nodes"] + graph["relationships"]:
        assert item["evidence"], item
        for evidence in item["evidence"]:
            lines = (FIXTURES / evidence["file"]).read_text(encoding="utf-8-sig").splitlines()
            assert 1 <= evidence["line"] <= len(lines), evidence
            source_line = lines[evidence["line"] - 1].strip()[:200]
            expected = "[REDACTED]" if "Password=" in source_line else source_line
            assert evidence["snippet"] == expected


def test_component_diagram_attributes_calls_to_the_component_that_makes_them(
    output: Path,
) -> None:
    drawio = ET.parse(output / "as-is/c4.drawio")
    [page] = [d for d in drawio.iter("diagram") if d.attrib["id"] == "component-tiny-shop-web"]
    edges = {o.attrib["id"]: o for o in page.iter("object")}
    call = edges["component:tiny-shop/web/Shop.Web->external:reports.intranet"]
    assert call.attrib["evidence"] == "tiny-shop/Web/Default.aspx.cs:5"


def test_each_scanned_project_gets_its_own_output_folder(tmp_path: Path) -> None:
    other = tmp_path / "src" / "zeta-shop"
    shutil.copytree(FIXTURES / "tiny-shop", other)
    out = tmp_path / "out"
    for paths in ([FIXTURES / "tiny-shop"], [other], [other, FIXTURES / "tiny-shop"]):
        scan = runner.invoke(app, ["scan", *map(str, paths), "-o", str(out)])
        assert scan.exit_code == 0, scan.output
    render = runner.invoke(app, ["render", "--as-is", "-o", str(out)])
    assert render.exit_code == 0, render.output
    for name in ["tiny-shop", "zeta-shop", "tiny-shop+zeta-shop"]:
        assert (out / name / "graph.json").is_file(), name
        assert (out / name / "as-is/c4.drawio").is_file(), name


def test_render_requires_view_and_existing_graph(tmp_path: Path) -> None:
    assert runner.invoke(app, ["render", "-o", str(tmp_path)]).exit_code != 0
    missing = runner.invoke(app, ["render", "--as-is", "-o", str(tmp_path)])
    assert missing.exit_code == 1
    assert "Run `python -m exodus scan` first" in missing.output
    absent = runner.invoke(app, ["render", "--as-is", "-o", str(tmp_path / "absent")])
    assert absent.exit_code == 1


@pytest.fixture
def input_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """./exodus-input with two projects plus entries that are not projects."""
    monkeypatch.chdir(tmp_path)
    for name in ("tiny-shop", "zeta-shop"):
        shutil.copytree(FIXTURES / "tiny-shop", tmp_path / "exodus-input" / name)
    (tmp_path / "exodus-input" / ".hidden").mkdir()
    (tmp_path / "exodus-input" / "notes.txt").write_text("not a project")
    return tmp_path


def test_without_command_lists_input_projects_and_runs_the_chosen_one(input_folder: Path) -> None:
    result = runner.invoke(app, [], input="0\nx\n2\n")
    assert result.exit_code == 0, result.output
    assert "1) tiny-shop\n  2) zeta-shop\n" in result.output
    assert ".hidden" not in result.output
    assert result.output.count("Invalid choice") == 2
    outputs = [p.name for p in (input_folder / "exodus-output").iterdir()]
    assert outputs == ["zeta-shop"]
    assert (input_folder / "exodus-output/zeta-shop/as-is/c4.drawio").is_file()


def test_without_command_runs_the_chosen_projects_together(input_folder: Path) -> None:
    for choice in ("2, 1", ""):  # empty = all
        result = runner.invoke(app, [], input=f"{choice}\n")
        assert result.exit_code == 0, result.output
    outputs = [p.name for p in (input_folder / "exodus-output").iterdir()]
    assert outputs == ["tiny-shop+zeta-shop"]


def test_without_command_runs_a_single_input_project_without_asking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    shutil.copytree(FIXTURES / "tiny-shop", tmp_path / "exodus-input" / "tiny-shop")
    result = runner.invoke(app, [])
    assert result.exit_code == 0, result.output
    assert "Choose" not in result.output
    assert (tmp_path / "exodus-output/tiny-shop/as-is/c4.drawio").is_file()


def test_without_command_creates_the_input_folder_when_there_is_no_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for _ in range(2):  # missing, then empty
        result = runner.invoke(app, [])
        assert result.exit_code == 1
        assert "Put the legacy projects in" in result.output
        assert (tmp_path / "exodus-input").is_dir()
    assert not (tmp_path / "exodus-output").exists()


def test_inventory_lists_tables_and_procedures_of_each_database(output: Path) -> None:
    inventory = (output / "inventory.md").read_text()
    assert "### Server `dbsrv`" in inventory
    assert "  - Tables (2): dbo.Orders, dbo.Customers" in inventory
    assert "  - Procedures (1): dbo.usp_CloseOrder" in inventory


def test_migration_recommends_rehost_now_and_refactor_later(output: Path) -> None:
    migration = (output / "migration.md").read_text()
    assert "**Rehost** → EC2 Windows (IIS)" in migration
    assert "**Refactor** → .NET 8+ on ECS Fargate" in migration
    assert "| shop | SQL Server | Amazon RDS for SQL Server |" in migration


def test_render_to_be_writes_the_replatform_diagram(output: Path) -> None:
    render = runner.invoke(app, ["render", "--to-be", "-o", str(output.parent)])
    assert render.exit_code == 0, render.output
    diagram = ET.parse(output / "to-be/replatform.drawio")
    assert [d.attrib["id"] for d in diagram.iter("diagram")] == ["replatform-tiny-shop"]
    styles = " ".join(c.attrib.get("style", "") for c in diagram.iter("mxCell"))
    assert "resIcon=mxgraph.aws4.ec2;" in styles  # .NET Framework: rehost on EC2 Windows
    assert "resIcon=mxgraph.aws4.rds;" in styles
    # Ollama is offline in tests: the refactor proposal falls back to the catalog defaults
    refactor = ET.parse(output / "to-be/refactor.drawio")
    assert [d.attrib["id"] for d in refactor.iter("diagram")] == ["refactor-tiny-shop"]
    graph = json.loads((output / "graph.json").read_text())
    assert graph["refactor"]["choices"]
    assert not any(choice["inferred"] for choice in graph["refactor"]["choices"])
    adrs = sorted(p.name for p in (output / "to-be" / "adr").glob("*.md"))
    assert adrs == ["001-compute.md", "002-data.md"]
    stale = output / "to-be" / "adr" / "009-old.md"
    stale.write_text("old")
    assert runner.invoke(app, ["render", "--to-be", "-o", str(output.parent)]).exit_code == 0
    assert not stale.exists()


def test_render_writes_the_html_report(output: Path) -> None:
    report = (output / "report.html").read_text()
    assert report.startswith("<!doctype html>")
    assert "Content-Security-Policy\" content=\"default-src 'none'" in report
    assert "Relatório de migração para AWS — tiny-shop" in report


def test_scan_writes_the_project_documentation(output: Path) -> None:
    documentation = (output / "documentation.md").read_text()
    assert documentation.startswith("# tiny-shop — documentação do projeto")
    assert "## 14. Glossário" in documentation


def test_lang_en_writes_the_documents_in_english(tmp_path: Path) -> None:
    scan = runner.invoke(
        app, ["scan", str(FIXTURES / "tiny-shop"), "-o", str(tmp_path), "--lang", "en"]
    )
    assert scan.exit_code == 0, scan.output
    render = runner.invoke(app, ["render", "--as-is", "-o", str(tmp_path), "--lang", "en"])
    assert render.exit_code == 0, render.output
    documentation = (tmp_path / "tiny-shop" / "documentation.md").read_text()
    assert documentation.startswith("# tiny-shop — project documentation")
    report = (tmp_path / "tiny-shop" / "report.html").read_text()
    assert "AWS migration report — tiny-shop" in report


def test_without_qdrant_the_scan_warns_and_goes_on(tmp_path: Path) -> None:
    scan = runner.invoke(app, ["scan", str(FIXTURES / "tiny-shop"), "-o", str(tmp_path)])
    assert scan.exit_code == 0, scan.output
    assert "RAG unavailable" in scan.output
    assert not (tmp_path / "tiny-shop" / "rag-trace.md").exists()
