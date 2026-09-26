"""The legacy's written documentation (READMEs, docs/ folders) cut into pieces for retrieval.

Only text formats (no new dependency). Markdown is cut at its headings; every section, and
plain text files, are cut between paragraphs into pieces of at most MAX_CHARS, each keeping the
line it starts at. Paragraphs too short to say anything are skipped.
"""

import re
from collections.abc import Iterable, Iterator
from pathlib import PurePosixPath

from exodus.application.ports import SourceFile, redact_sensitive_line
from exodus.domain.facts import DocumentSection, Fact

MAX_CHARS = 800
MIN_CHARS = 20
_SUFFIXES = (".md", ".txt", ".rst", ".adoc")
_NOT_DOCUMENTATION = ("requirements", "license", "notice")  # dependencies and legal text
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_UNDERLINE = re.compile(r"^\s*(=+|-+)\s*$")  # "Title" over a line of = or -: also a heading


class DocumentExtractor:
    def matches(self, path: PurePosixPath) -> bool:
        name = path.name.lower()
        if name.startswith(_NOT_DOCUMENTATION):
            return False
        return name.startswith("readme") or path.suffix.lower() in _SUFFIXES

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        markdown = file.path.suffix.lower() == ".md" or file.path.name.lower() == "readme"
        title = file.path.name
        paragraph: list[str] = []
        start = 0
        paragraphs: list[tuple[str, int, str]] = []  # (title, first line, text)
        lines = [*(redact_sensitive_line(line) for line in file.lines), ""]
        for number, line in enumerate(lines, start=1):
            underlined = (
                markdown
                and line.strip()
                and len(line.strip()) < 3 * MIN_CHARS
                and _UNDERLINE.match(lines[number])  # the next line
                and len(lines[number].strip()) >= 3
            )
            if underlined:
                lines[number] = ""  # the underline itself says nothing
            heading = (_HEADING.match(line) or underlined) if markdown else None
            if heading or not line.strip():
                text = "\n".join(paragraph).strip()
                if len(text) >= MIN_CHARS:  # "ok", "TODO", a lone link: nothing to retrieve
                    paragraphs.append((title, start, text))
                paragraph = []
                if isinstance(heading, re.Match):
                    title = heading.group(1)
                elif heading:
                    title = line.strip().strip("*_").strip()
                continue
            if not paragraph:
                start = number
            paragraph.append(line.rstrip())
        yield from _pieces(file, paragraphs)


def _pieces(file: SourceFile, paragraphs: list[tuple[str, int, str]]) -> Iterator[Fact]:
    """Consecutive paragraphs of the same section joined while they fit in MAX_CHARS."""
    current: list[str] = []
    current_title, current_line = "", 0
    for title, line, text in [*paragraphs, ("", 0, "")]:
        joined = "\n\n".join([*current, text])
        if current and (title != current_title or len(joined) > MAX_CHARS or not text):
            yield DocumentSection(
                title=current_title,
                text="\n\n".join(current)[:MAX_CHARS],
                evidence=file.evidence(current_line),
            )
            current = []
        if text:
            if not current:
                current_title, current_line = title, line
            current.append(text)
