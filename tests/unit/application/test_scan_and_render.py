from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from exodus.application.ports import Document, SourceExcerpt, SourceFile
from exodus.application.use_cases.render_diagrams import render_diagrams
from exodus.application.use_cases.scan_projects import ProjectScan, scan_projects
from exodus.domain.facts import Fact, ModuleDeclared
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence, Node, NodeKind


class FakeFileSource:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = files
        self.reads: list[str] = []

    def iter_paths(self, root: Path) -> Iterable[PurePosixPath]:
        return [PurePosixPath(p) for p in self.files if p.startswith(root.name + "/")]

    def read_text(self, root: Path, path: PurePosixPath) -> str:
        self.reads.append(str(path))
        return self.files[str(path)]


class NamespaceExtractor:
    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix == ".cs"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        for number, line in enumerate(file.lines, start=1):
            if line.startswith("namespace "):
                yield ModuleDeclared(name=line.split()[1], evidence=file.evidence(number))


def test_scan_dispatches_matching_files_and_groups_facts_per_root() -> None:
    source = FakeFileSource(
        {
            "a/x.cs": "using System;\nnamespace A.X\n",
            "a/logo.png": "binary",
            "b/y.cs": "namespace B\n",
        }
    )
    scans = scan_projects([Path("/src/a"), Path("/src/b")], source, [NamespaceExtractor()])
    assert scans == [
        ProjectScan(
            "a",
            (
                ModuleDeclared(
                    name="A.X", evidence=Evidence(file="a/x.cs", line=2, snippet="namespace A.X")
                ),
            ),
        ),
        ProjectScan(
            "b",
            (
                ModuleDeclared(
                    name="B", evidence=Evidence(file="b/y.cs", line=1, snippet="namespace B")
                ),
            ),
        ),
    ]
    assert "a/logo.png" not in source.reads


def test_source_file_helpers() -> None:
    file = SourceFile(PurePosixPath("r/f.txt"), "one\n  two  \nthree")
    assert file.line_at(0) == 1
    assert file.line_at(file.text.index("three")) == 3
    assert file.evidence(2) == Evidence(file="r/f.txt", line=2, snippet="two")
    assert file.evidence(99).snippet == ""


def test_evidence_keeps_location_but_redacts_credential_lines() -> None:
    line = '<add key="ApiKey" value="audit-canary-123" />'
    source = SourceFile(PurePosixPath("app/Web.config"), line)
    excerpt = SourceExcerpt("app/Web.config", 1, (line,))
    for evidence in (source.evidence(1), excerpt.evidence(1)):
        assert (evidence.file, evidence.line, evidence.snippet) == (
            "app/Web.config",
            1,
            "[REDACTED]",
        )
    url = SourceFile(PurePosixPath("app/settings.py"), "https://user:pass@example.test/db")
    assert url.evidence(1).snippet == "[REDACTED]"
    config = SourceFile(PurePosixPath("app/settings.json"), '"password": "audit-canary-123"')
    assert config.evidence(1).snippet == "[REDACTED]"
    for line in ("DB_PASSWORD=audit-canary-123", '"jwtToken": "audit-canary-123"'):
        assert SourceFile(PurePosixPath("app/settings.yml"), line).evidence(1).snippet == (
            "[REDACTED]"
        )


class InMemoryRepository:
    def __init__(self, graph: ArchitectureGraph) -> None:
        self.graph = graph

    def save(self, graph: ArchitectureGraph) -> None:
        self.graph = graph

    def load(self) -> ArchitectureGraph:
        return self.graph


class CountingRenderer:
    def __init__(self, name: str) -> None:
        self.name = name

    def render(self, graph: ArchitectureGraph) -> list[Document]:
        return [Document(self.name, str(len(graph.nodes())))]


def test_render_diagrams_loads_graph_and_collects_documents() -> None:
    graph = ArchitectureGraph(
        [
            Node(
                id="system:a",
                kind=NodeKind.SYSTEM,
                name="a",
                evidence=(Evidence(file="a/x", line=1, snippet=""),),
            )
        ]
    )
    docs = render_diagrams(
        InMemoryRepository(graph), [CountingRenderer("x.md"), CountingRenderer("y.md")]
    )
    assert docs == [Document("x.md", "1"), Document("y.md", "1")]
