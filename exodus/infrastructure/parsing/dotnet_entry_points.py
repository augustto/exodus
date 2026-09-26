"""Entry points found in .NET source and legacy ASP.NET files."""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath

from exodus.application.ports import SourceFile
from exodus.domain.facts import EntryPoint, Fact

_PAGES = {".svc": "SOAP", ".asmx": "SOAP", ".aspx": "HTTP", ".ashx": "HTTP"}
_HTTP_ATTRIBUTE = re.compile(
    r"\[(?:Http(?:Get|Post|Put|Delete|Patch)|Route)\s*"
    r"(?:\(\s*(?:\"([^\"]+)\"|'([^']+)'|([^)]+))\s*\))?"
)
_OPERATION = re.compile(
    r"\[OperationContract(?:\s*\([^\]]*\))?\]\s*(?:public\s+)?[\w<>,.?\[\] ]+\s+(\w+)\s*\("
)
_QUEUE_CONSUMER = re.compile(
    r"(?:IConsumer|IHandleMessages|ICommandHandler|IEventHandler)\s*<\s*([\w.]+)"
)
_GENERIC_PARAMETER = re.compile(r"T(?:[A-Z]\w*)?")  # ICommandHandler<TCommand> in a decorator
_JOB = re.compile(r"class\s+(\w+)\s*:\s*(?:\w+\.)?IJob\b|new\s+(?:System\.Threading\.)?Timer\s*\(")
_WINDOWS_SERVICE = re.compile(r"class\s+(\w+)\s*:\s*(?:\w+\.)?ServiceBase\b")


class DotNetEntryPointExtractor:
    """HTTP/SOAP handlers, message consumers and scheduled/background .NET work."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() in (*_PAGES, ".cs")

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        suffix = file.path.suffix.lower()
        if suffix in _PAGES:
            yield EntryPoint(
                kind=_PAGES[suffix], name=f"/{file.path.name}", evidence=file.evidence(1)
            )
            return
        for match in _HTTP_ATTRIBUTE.finditer(file.text):
            path = next((group for group in match.groups() if group), "controller").strip()
            yield EntryPoint(
                kind="HTTP",
                name=path if path.startswith("/") else f"/{path}",
                evidence=file.evidence(file.line_at(match.start())),
            )
        for match in _OPERATION.finditer(file.text):
            yield EntryPoint(
                kind="SOAP",
                name=match.group(1),
                evidence=file.evidence(file.line_at(match.start())),
            )
        for match in _QUEUE_CONSUMER.finditer(file.text):
            message = match.group(1).rsplit(".", 1)[-1]
            if _GENERIC_PARAMETER.fullmatch(message):
                continue
            yield EntryPoint(
                kind="queue consumer",
                name=message,
                evidence=file.evidence(file.line_at(match.start())),
            )
        for match in _JOB.finditer(file.text):
            name = match.group(1) or "Timer"
            yield EntryPoint(
                kind="scheduled job", name=name, evidence=file.evidence(file.line_at(match.start()))
            )
        for match in _WINDOWS_SERVICE.finditer(file.text):
            yield EntryPoint(
                kind="Windows service",
                name=match.group(1),
                evidence=file.evidence(file.line_at(match.start())),
            )
