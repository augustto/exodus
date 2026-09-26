"""Entry points found in Java source and deployment descriptors."""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath

from exodus.application.ports import SourceFile
from exodus.domain.facts import EntryPoint, Fact
from exodus.infrastructure.config.xml_tree import parse_xml

_HTTP = re.compile(
    r"@(?:RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|Path)\s*"
    r"\(\s*(?:value\s*=\s*|path\s*=\s*)?[\"']([^\"']+)[\"']"
)
_SERVLET = re.compile(r"@WebServlet\s*\(\s*(?:urlPatterns\s*=\s*)?[\"']([^\"']+)[\"']")
_WEB_SERVICE = re.compile(r"@WebService\b\s*(?:\([^)]*\))?\s*(?:public\s+)?class\s+(\w+)")
_JMS = re.compile(r"@JmsListener\s*\([^)]*?destination\s*=\s*[\"']([^\"']+)[\"']")
_SCHEDULED = re.compile(
    r"@Scheduled\s*\([^)]*\)\s*(?:public|protected|private)?\s*[\w<>?,.\[\] ]+\s+(\w+)\s*\(",
    re.DOTALL,
)


class JavaEntryPointExtractor:
    """Spring/JAX-RS/Servlet/JAX-WS endpoints, JMS listeners and scheduled methods."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() == ".java"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        for match in _HTTP.finditer(file.text):
            path = match.group(1)
            yield EntryPoint(
                kind="HTTP",
                name=path if path.startswith("/") else f"/{path}",
                evidence=file.evidence(file.line_at(match.start())),
            )
        for match in _SERVLET.finditer(file.text):
            path = match.group(1)
            yield EntryPoint(
                kind="HTTP",
                name=path if path.startswith("/") else f"/{path}",
                evidence=file.evidence(file.line_at(match.start())),
            )
        for match in _WEB_SERVICE.finditer(file.text):
            yield EntryPoint(
                kind="SOAP",
                name=match.group(1),
                evidence=file.evidence(file.line_at(match.start())),
            )
        for match in _JMS.finditer(file.text):
            yield EntryPoint(
                kind="queue consumer",
                name=match.group(1),
                evidence=file.evidence(file.line_at(match.start())),
            )
        for match in _SCHEDULED.finditer(file.text):
            yield EntryPoint(
                kind="scheduled job",
                name=match.group(1),
                evidence=file.evidence(file.line_at(match.start())),
            )


class WebXmlEntryPointExtractor:
    """Servlet routes declared in legacy ``web.xml`` deployment descriptors."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.name.lower() == "web.xml"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        root = parse_xml(file.text)
        if root is None:
            return
        for mapping in root.iter("servlet-mapping"):
            for pattern in (child for child in mapping.children if child.tag == "url-pattern"):
                if name := pattern.text.strip():
                    yield EntryPoint(kind="HTTP", name=name, evidence=file.evidence(pattern.line))
