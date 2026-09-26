from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from exodus.application.ports import FactExtractor, FileSource, SourceFile
from exodus.domain.facts import Fact


@dataclass(frozen=True)
class ProjectScan:
    """All facts found under one scanned root."""

    name: str
    facts: tuple[Fact, ...]


def scan_projects(
    roots: Sequence[Path], file_source: FileSource, extractors: Sequence[FactExtractor]
) -> list[ProjectScan]:
    scans = []
    for root in roots:
        facts: list[Fact] = []
        for path in file_source.iter_paths(root):
            matching = [e for e in extractors if e.matches(path)]
            if not matching:
                continue
            file = SourceFile(path, file_source.read_text(root, path))
            for extractor in matching:
                facts.extend(extractor.extract(file))
        scans.append(ProjectScan(root.name, tuple(facts)))
    return scans
