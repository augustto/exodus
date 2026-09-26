"""Language-agnostic extractor for URLs hard-coded in source files."""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath

from exodus.application.ports import SourceFile
from exodus.domain.facts import EndpointCalled, Fact
from exodus.domain.identity import url_host, url_protocol

_URL = re.compile(r"""(?:https?|net\.tcp|net\.pipe)://[^\s"'<>()\[\]{};,`]+""", re.IGNORECASE)

# XML namespaces and schema URIs that look like URLs but are never called
_NOISE_HOSTS = {
    "tempuri.org",
    "schemas.microsoft.com",
    "schemas.xmlsoap.org",
    "www.w3.org",
    "w3.org",
    "xmlns.jcp.org",
    "java.sun.com",
    "maven.apache.org",
    "www.apache.org",
    "json-schema.org",
}


class UrlLiteralExtractor:
    def __init__(self, extensions: tuple[str, ...]) -> None:
        self.extensions = extensions

    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() in self.extensions

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        for match in _URL.finditer(file.text):
            url = match.group(0).rstrip(".")
            host = url_host(url)
            if host and host not in _NOISE_HOSTS:
                yield EndpointCalled(
                    url=url,
                    protocol=url_protocol(url),
                    evidence=file.evidence(file.line_at(match.start())),
                )
