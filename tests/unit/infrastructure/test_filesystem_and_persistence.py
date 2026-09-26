import json
from pathlib import Path, PurePosixPath

import pytest

from exodus.domain.graph import SCHEMA_VERSION, ArchitectureGraph
from exodus.domain.model import DomainError, Evidence, Node, NodeKind
from exodus.infrastructure.filesystem import LocalFileSource, decode
from exodus.infrastructure.persistence.json_repository import JsonGraphRepository


def test_local_file_source_skips_build_and_vendor_folders(tmp_path: Path) -> None:
    root = tmp_path / "app"
    for rel in [
        "Web/Default.aspx",
        "Web/bin/Web.dll",
        "Web/obj/x.cs",
        "packages/P/lib.dll",
        "a.cs",
    ]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x")
    source = LocalFileSource()
    paths = list(source.iter_paths(root))
    assert paths == [PurePosixPath("app/a.cs"), PurePosixPath("app/Web/Default.aspx")]
    assert source.read_text(root, paths[0]) == "x"


def test_local_file_source_does_not_follow_links_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("private data")
    linked = root / "linked.py"
    linked.symlink_to(outside)
    source = LocalFileSource()

    assert list(source.iter_paths(root)) == []
    with pytest.raises(ValueError, match="outside the scanned root"):
        source.read_text(root, PurePosixPath("app/linked.py"))
    with pytest.raises(ValueError, match="outside the scanned root"):
        source.read_text(root, PurePosixPath("app/../outside.py"))


def test_decode_handles_legacy_encodings() -> None:
    assert decode("ação".encode("utf-16")) == "ação"
    assert decode(b"\xef\xbb\xbfhello") == "hello"
    assert decode("ação".encode("cp1252")) == "ação"


def test_json_repository_round_trip_and_schema(tmp_path: Path) -> None:
    graph = ArchitectureGraph(
        [
            Node(
                id="system:a",
                kind=NodeKind.SYSTEM,
                name="a",
                evidence=(Evidence(file="a/x", line=1, snippet="s"),),
            )
        ]
    )
    repository = JsonGraphRepository(tmp_path / "out")
    repository.save(graph)

    assert repository.load().nodes() == graph.nodes()
    saved = json.loads((tmp_path / "out" / "graph.json").read_text())
    assert saved["schema_version"] == SCHEMA_VERSION
    schema = json.loads((tmp_path / "out" / "graph.schema.json").read_text())
    assert "nodes" in schema["properties"]


def test_json_repository_rejects_future_major_version(tmp_path: Path) -> None:
    (tmp_path / "graph.json").write_text(
        '{"schema_version": "2.0", "nodes": [], "relationships": []}'
    )
    with pytest.raises(DomainError):
        JsonGraphRepository(tmp_path).load()
