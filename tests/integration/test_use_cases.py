"""`exodus scan` with a stand-in model: use-cases.md cites the real lines of the fixture."""

import json
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from exodus.application.ports import DraftStep, UseCaseDraft, UseCaseRequest
from exodus.infrastructure.filesystem import LocalFileSource
from exodus.infrastructure.persistence.json_repository import JsonGraphRepository
from exodus.infrastructure.rendering.use_cases import UseCasesRenderer
from exodus.interfaces.cli.app import create_app
from exodus.main import EXTRACTORS

FIXTURE = Path(__file__).parents[1] / "fixtures" / "tiny-shop"


class StandInWriter:
    def __init__(self) -> None:
        self.requests: list[UseCaseRequest] = []

    def draft(
        self,
        request: UseCaseRequest,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> UseCaseDraft:
        self.requests.append(request)
        return UseCaseDraft(
            title="Atender pedido SOAP",
            steps=(
                DraftStep(text="O IIS ativa o serviço", file="tiny-shop/Api/Orders.svc", line=1),
                DraftStep(text="A classe Orders", file="tiny-shop/Api/Orders.svc.cs", line=3),
            ),
            touches=(),
            confidence=0.5,
        )


def test_scan_writes_use_cases_citing_the_fixture(tmp_path: Path) -> None:
    writer = StandInWriter()
    app = create_app(
        file_source=LocalFileSource(),
        extractors=EXTRACTORS,
        repository_factory=JsonGraphRepository,
        inventory_renderers=lambda language: [UseCasesRenderer()],
        diagram_renderers=[],
        use_case_writer_factory=lambda target, language: writer,
    )

    result = CliRunner().invoke(app, ["scan", str(FIXTURE), "-o", str(tmp_path)])

    assert result.exit_code == 0, result.output
    [request] = writer.requests
    assert [s.path for s in request.sources] == [
        "tiny-shop/Api/Orders.svc",
        "tiny-shop/Api/Orders.svc.cs",
    ]
    content = (tmp_path / "tiny-shop" / "use-cases.md").read_text()
    assert "- **Trigger:** SOAP `/Orders.svc` — `tiny-shop/Api/Orders.svc:1`" in content
    assert "2. A classe Orders — `tiny-shop/Api/Orders.svc.cs:3`" in content
    graph = json.loads((tmp_path / "tiny-shop" / "graph.json").read_text())
    assert graph["use_cases"][0]["steps"][1]["evidence"]["snippet"] == "public class Orders"
