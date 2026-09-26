"""Language-agnostic extractor for the tables, procedures and collections code talks to.

Only what is common to each kind of database, never an ORM or framework: SQL (in string
literals that start with a SQL verb, or in whole .sql scripts) and the way Mongo names a
collection in its shell and drivers.
"""

import re
from collections.abc import Iterable, Iterator
from pathlib import PurePosixPath

from exodus.application.ports import SourceFile
from exodus.domain.facts import DataObjectUsed, Fact

_PART = r'(?:\[[^\]\n]+\]|"[^"\n]+"|`[^`\n]+`|[A-Za-z_]\w*)'
_NAME = rf"({_PART}(?:\s*\.\s*{_PART})*)"
_TABLE = re.compile(rf"\b(?:FROM|JOIN|INTO|UPDATE)\s+{_NAME}", re.IGNORECASE)
_CREATE_TABLE = re.compile(rf"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{_NAME}", re.IGNORECASE)
_PROCEDURE = re.compile(rf"\b(?:EXEC|EXECUTE|CALL)\s+{_NAME}", re.IGNORECASE)
_CREATE_PROCEDURE = re.compile(
    rf"\bCREATE\s+(?:OR\s+(?:ALTER|REPLACE)\s+)?PROC(?:EDURE)?\s+{_NAME}", re.IGNORECASE
)
_SQL_START = re.compile(
    r"\s*(?:SELECT|INSERT|UPDATE|DELETE|MERGE|WITH|EXEC|EXECUTE|CALL)\b", re.IGNORECASE
)
_STRING = re.compile(r'@"(?:[^"]|"")*"|"""[\s\S]*?"""|"(?:\\.|[^"\\\n])*"')
_PYTHON_STRING = re.compile(r"'''[\s\S]*?'''|'(?:\\.|[^'\\\n])*'")
_COLLECTION = re.compile(
    r"\bdb\.(\w+)\.(?:find|insert|update|delete|remove|replace|aggregate|count)\w*\s*\("
    r"""|\b(?:get|Get)Collection\s*(?:<[^>\n]*>)?\s*\(\s*["'](\w+)["']"""
    r"""|\.collection\s*\(\s*["'](\w+)["']"""
)
_NOT_TABLES = frozenset({"dual", "set", "values", "select"})


class DataAccessExtractor:
    def __init__(self, extensions: tuple[str, ...]) -> None:
        self.extensions = extensions

    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() in (*self.extensions, ".sql")

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        if file.path.suffix.lower() == ".sql":
            yield from _sql(file, 0, file.text, script=True)
            return
        strings = [*_STRING.finditer(file.text)]
        if file.path.suffix.lower() == ".py":
            strings += _PYTHON_STRING.finditer(file.text)
        for literal in sorted(strings, key=lambda m: m.start()):
            if _SQL_START.match(literal.group(0).lstrip('@"').lstrip("'")):
                yield from _sql(file, literal.start(), literal.group(0), script=False)
        for match in _COLLECTION.finditer(file.text):
            name = next(group for group in match.groups() if group)
            yield _fact(file, "collection", name, match.start())


def _sql(file: SourceFile, offset: int, text: str, script: bool) -> Iterator[DataObjectUsed]:
    patterns = [(_TABLE, "table"), (_PROCEDURE, "procedure")]
    if script:
        patterns += [(_CREATE_TABLE, "table"), (_CREATE_PROCEDURE, "procedure")]
    found = sorted(
        (match.start(1), kind, _normalized(match.group(1)))
        for pattern, kind in patterns
        for match in pattern.finditer(text)
    )
    for start, kind, name in found:
        if name.lower() not in _NOT_TABLES:
            yield _fact(file, kind, name, offset + start)


def _normalized(name: str) -> str:
    """dbo . [Invoices] -> dbo.Invoices"""
    return ".".join(part.strip().strip('[]"`') for part in name.split("."))


def _fact(file: SourceFile, kind: str, name: str, offset: int) -> DataObjectUsed:
    return DataObjectUsed(kind=kind, name=name, evidence=file.evidence(file.line_at(offset)))
