"""Generic tree-sitter extractor: each language only provides a grammar name and queries.

Query capture names map to facts: @module -> ModuleDeclared, @class -> ClassDeclared,
@import -> ImportFound, @consumes -> MessageConsumed and @publishes -> MessagePublished (last
segment of the captured type).
Facts made of several captures of one match: @message + @exchange (+ @base, the base types)
-> MessageDeclared, a command when a base type is named like ICommand.
Captures starting with "_" only serve predicates.
"""

from collections.abc import Callable, Iterable
from functools import cached_property
from pathlib import PurePosixPath

from tree_sitter import Node, Parser, Query, QueryCursor
from tree_sitter_language_pack import SupportedLanguage, get_language, get_parser

from exodus.application.ports import SourceFile
from exodus.domain.facts import (
    ClassDeclared,
    Fact,
    ImportFound,
    MessageConsumed,
    MessageDeclared,
    MessagePublished,
    ModuleDeclared,
    SourceFileDetected,
)
from exodus.domain.model import Evidence

_CAPTURES: dict[str, Callable[[str, Evidence], Fact]] = {
    "module": lambda text, ev: ModuleDeclared(name=text, evidence=ev),
    "class": lambda text, ev: ClassDeclared(name=text, evidence=ev),
    "import": lambda text, ev: ImportFound(module=text, evidence=ev),
    "consumes": lambda text, ev: MessageConsumed(message=text.rsplit(".", 1)[-1], evidence=ev),
    "publishes": lambda text, ev: MessagePublished(message=text.rsplit(".", 1)[-1], evidence=ev),
}

# facts made of several captures of one match, by their required captures; the factory gets
# the text of every capture of the match (joined by spaces when repeated) and the evidence of
# the first required one
_MATCH_CAPTURES: dict[tuple[str, ...], Callable[[dict[str, str], Evidence], Fact]] = {
    ("exchange", "message"): lambda t, ev: MessageDeclared(
        message=t["message"],
        exchange=t["exchange"],
        is_command=any(b.endswith("ICommand") for b in t.get("base", "").split()),
        evidence=ev,
    ),
}


class TreeSitterExtractor:
    def __init__(
        self, language: str, grammar: SupportedLanguage, extensions: tuple[str, ...], queries: str
    ) -> None:
        self.language = language
        self.grammar = grammar
        self.extensions = extensions
        self.queries = queries

    @cached_property
    def _parser(self) -> Parser:
        return get_parser(self.grammar)

    @cached_property
    def _query(self) -> Query:
        return Query(get_language(self.grammar), self.queries)

    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() in self.extensions

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        yield SourceFileDetected(language=self.language, evidence=file.evidence(1))
        tree = self._parser.parse(file.text.encode("utf-8"))
        for _, captures in QueryCursor(self._query).matches(tree.root_node):
            for names, build in _MATCH_CAPTURES.items():
                if all(name in captures for name in names):
                    texts = {k: " ".join(_text(n) for n in found) for k, found in captures.items()}
                    line = captures[names[0]][0].start_point.row + 1
                    yield build(texts, file.evidence(line))
            for name, found in captures.items():
                factory = _CAPTURES.get(name)
                if factory is None:
                    continue
                for node in found:
                    yield factory(_text(node), file.evidence(node.start_point.row + 1))


def _text(node: Node) -> str:
    return (node.text or b"").decode("utf-8", errors="replace")
