"""Tree-sitter facts for Python source files."""

from collections.abc import Iterable
from pathlib import PurePosixPath

from exodus.application.ports import SourceFile
from exodus.domain.facts import Fact, ModuleDeclared
from exodus.infrastructure.parsing.tree_sitter_extractor import TreeSitterExtractor

PYTHON_QUERIES = """
(import_statement name: (dotted_name) @import)
(import_from_statement module_name: (dotted_name) @import)
(class_definition name: (identifier) @class)
"""


class PythonExtractor:
    """Python modules are named by their source path, unlike C#/Java packages in the source."""

    def __init__(self) -> None:
        self._tree_sitter = TreeSitterExtractor("Python", "python", (".py",), PYTHON_QUERIES)

    def matches(self, path: PurePosixPath) -> bool:
        return self._tree_sitter.matches(path)

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        facts = iter(self._tree_sitter.extract(file))
        yield next(facts)  # SourceFileDetected is always the first tree-sitter fact.
        if module := _module_name(file.path):
            yield ModuleDeclared(name=module, evidence=file.evidence(1))
        yield from facts


def _module_name(path: PurePosixPath) -> str | None:
    parts = list(path.with_suffix("").parts)
    for root in ("src", "app"):
        if root in parts:
            parts = parts[parts.index(root) + 1 :]
            break
    else:
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or None
