"""Small language-agnostic scanner for legacy technology and plaintext-secret signals."""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath

from exodus.application.ports import SourceFile
from exodus.domain.facts import Fact, SecretFound, TechnologyUsed

_TECHNOLOGIES = {
    "WCF": re.compile(
        r"system\.serviceModel|\[\s*(?:ServiceContract|OperationContract)\b|\bServiceHost\b"
    ),
    "MSMQ": re.compile(r"net\.msmq://|\bSystem\.Messaging\b"),
    "Web Forms": re.compile(r"\bSystem\.Web\.UI\b|<%@\s*Page\b", re.IGNORECASE),
    "Remoting": re.compile(r"\bSystem\.Runtime\.Remoting\b"),
}
_SECRET = re.compile(
    r"(?P<name>[\w.-]*(?:key|secret|password|token|pwd)[\w.-]*)"
    r"[\"']?\s*[=:]\s*[\"']?(?P<value>[^\"'\s<>]+)",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(
    r"^(?:\$\{|%|<|\{|env:|environment\b|os\.getenv\b|process\.env\b|changeme$|your[-_])",
    re.IGNORECASE,
)
_XML_SECRET = re.compile(
    r"(?:key|name)=[\"']([^\"']*(?:key|secret|password|token)[^\"']*)[\"'][^>]*\bvalue=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)


class RiskSignalExtractor:
    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() in {
            ".cs",
            ".config",
            ".json",
            ".yml",
            ".yaml",
            ".properties",
            ".py",
        }

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        for line, text in enumerate(file.lines, start=1):
            for name, pattern in _TECHNOLOGIES.items():
                if pattern.search(text):
                    yield TechnologyUsed(name=name, evidence=file.evidence(line))
            if match := _XML_SECRET.search(text):
                if not _PLACEHOLDER.search(match.group(2)):
                    yield SecretFound(name=match.group(1), evidence=file.evidence(line))
            elif match := _SECRET.search(text):
                name, value = match.group("name", "value")
                if not _PLACEHOLDER.search(value):
                    yield SecretFound(name=name, evidence=file.evidence(line))
