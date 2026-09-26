"""API gateway routes: the entry points a gateway exposes and which services it calls.

- Ntrada (ntrada*.yml): `use: downstream` routes call `downstream: <service>/<path>` over HTTP
  (service discovery name); `use: rabbitmq` routes send a message (routing key, snake_case as
  Convey's conventions, named back in PascalCase like its class) to an exchange.
  Read line by line: the format is regular and each fact keeps its exact line.
- Ocelot (ocelot.json): each route calls its downstream host (a service name) or, when the host
  is local, the service listening on its port.
"""

import json
import re
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

from exodus.application.ports import SourceFile
from exodus.domain.facts import EntryPoint, Fact, MessageSent, ServiceCalled

_NTRADA_FILE = re.compile(r"ntrada(-[\w]+)?\.ya?ml", re.IGNORECASE)
_KEY = re.compile(r"^\s*-?\s*([\w-]+):\s*(.*?)\s*$")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"}


class NtradaExtractor:
    def matches(self, path: PurePosixPath) -> bool:
        return _NTRADA_FILE.fullmatch(path.name) is not None

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        exchange: tuple[str, int] | None = None  # of the rabbitmq route being read
        prefix = ""  # path of the module being read
        for number, line in enumerate(file.lines, start=1):
            match = _KEY.match(line)
            if match is None:
                continue
            key, value = match.group(1), match.group(2).strip("'\"")
            if line.startswith("  ") and not line.startswith("   ") and not value:
                prefix = ""  # a new module starts (two-space key under modules:)
            elif key == "path" and not line.lstrip().startswith("-"):
                prefix = value.strip("/")
            if key == "downstream" and value:
                service = value.split("/", 1)[0]
                yield ServiceCalled(
                    service=service, protocol="HTTP", evidence=file.evidence(number)
                )
            elif key == "upstream":
                exchange = None  # a new route starts
                route = "/".join(part for part in (prefix, value.strip("/")) if part)
                yield EntryPoint(kind="HTTP", name=f"/{route}", evidence=file.evidence(number))
            elif key == "exchange" and value:
                exchange = (value, number)
            elif key == "routing_key" and value and exchange is not None:
                message = "".join(part.capitalize() for part in value.split("_"))
                yield MessageSent(
                    exchange=exchange[0], message=message, evidence=file.evidence(number)
                )


class OcelotExtractor:
    def matches(self, path: PurePosixPath) -> bool:
        return path.name.lower() == "ocelot.json"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        try:
            config: Any = json.loads(file.text)
        except ValueError:
            return
        routes = (
            (config.get("Routes") or config.get("ReRoutes") or [])
            if isinstance(config, dict)
            else []
        )
        searched_from = upstream_from = 0  # separate cursors: keys may come in any order
        for route in routes:
            upstream = route.get("UpstreamPathTemplate") if isinstance(route, dict) else None
            if isinstance(upstream, str):
                upstream_from = _line_of(
                    file.lines, "UpstreamPathTemplate", upstream, upstream_from
                )
                yield EntryPoint(
                    kind="HTTP", name=upstream, evidence=file.evidence(upstream_from + 1)
                )
            for target in (
                route.get("DownstreamHostAndPorts", []) if isinstance(route, dict) else []
            ):
                host, port = str(target.get("Host", "")), target.get("Port")
                searched_from = _line_of_port(file.lines, port, searched_from)
                local = host.lower() in _LOCAL_HOSTS
                yield ServiceCalled(
                    service=None if local else host,
                    port=port if isinstance(port, int) else None,
                    protocol="HTTP",
                    evidence=file.evidence(searched_from + 1),
                )


def _line_of_port(lines: list[str], port: Any, start: int) -> int:
    """Index of the next line (from start) mentioning this port as a "Port" value."""
    pattern = re.compile(rf'"Port"\s*:\s*{re.escape(str(port))}\b')
    return next((i for i in range(start, len(lines)) if pattern.search(lines[i])), start)


def _line_of(lines: list[str], key: str, value: str, start: int) -> int:
    """Index of the next line (from start) holding this "key": "value" pair."""
    pattern = re.compile(rf'"{key}"\s*:\s*"{re.escape(value)}"')
    return next((i for i in range(start, len(lines)) if pattern.search(lines[i])), start)
