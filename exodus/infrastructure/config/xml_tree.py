"""Minimal XML tree that keeps line numbers (xml.etree drops them, and evidence needs them)."""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from xml.parsers import expat

_DECLARATION = re.compile(r"^\s*<\?xml[^?]*\?>")


@dataclass
class XmlElement:
    tag: str  # local name, namespace stripped
    attrs: dict[str, str]
    line: int
    children: list["XmlElement"] = field(default_factory=list)
    text: str = ""

    def iter(self, tag: str) -> Iterator["XmlElement"]:
        """This element and all descendants with the given local name."""
        if self.tag == tag:
            yield self
        for child in self.children:
            yield from child.iter(tag)

    def find_all(self, path: str) -> list["XmlElement"]:
        """Descendants matching a child path like 'client/endpoint', searched from any depth."""
        first, *rest = path.split("/")
        current = list(self.iter(first))
        for tag in rest:
            current = [c for element in current for c in element.children if c.tag == tag]
        return current

    def child_text(self, tag: str) -> str | None:
        found = next((c for c in self.children if c.tag == tag), None)
        return found.text.strip() if found is not None else None


def parse_xml(text: str) -> XmlElement | None:
    """Parse XML text; returns None for malformed files (legacy configs are often broken)."""
    # the declared encoding may not match the already-decoded text, so drop the declaration
    # while keeping line numbers intact
    text = _DECLARATION.sub(lambda m: "\n" * m.group(0).count("\n"), text.lstrip("\ufeff"))
    parser = expat.ParserCreate(namespace_separator=" ")
    stack: list[XmlElement] = []
    roots: list[XmlElement] = []

    def start(name: str, attrs: dict[str, str]) -> None:
        element = XmlElement(
            _local(name), {_local(k): v for k, v in attrs.items()}, parser.CurrentLineNumber
        )
        (stack[-1].children if stack else roots).append(element)
        stack.append(element)

    def end(_name: str) -> None:
        stack.pop()

    def data(chunk: str) -> None:
        if stack:
            stack[-1].text += chunk

    def reject_doctype(*_args: object) -> None:
        raise ValueError("DTD is not supported")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = data
    parser.StartDoctypeDeclHandler = reject_doctype
    try:
        parser.Parse(text, True)
    except (expat.ExpatError, ValueError):
        return None
    return roots[0] if roots else None


def _local(name: str) -> str:
    return name.rsplit(" ", 1)[-1]
