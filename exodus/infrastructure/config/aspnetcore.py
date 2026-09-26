"""ASP.NET Core appsettings.json: service identity, data stores, calls to other services by name,
own message exchange and the platform services in use (service discovery, secrets, tracing,
logging, metrics, message broker).

Only the base appsettings.json is read; environment overrides (appsettings.docker.json, ...)
mostly repeat it with other host names. Keys are case-insensitive, as in .NET configuration;
comments and trailing commas are tolerated, as the .NET JSON reader does.
"""

import json
import re
from collections.abc import Iterable, Iterator
from pathlib import PurePosixPath
from typing import Any

from exodus.application.ports import SourceFile
from exodus.domain.facts import (
    DataSourceUsed,
    ExchangeOwned,
    Fact,
    PlatformUsed,
    ServiceCalled,
    ServiceDeclared,
)

# (path of a section, name of the platform service); used when the section is enabled
_PLATFORM_SECTIONS = [
    (("consul",), "Consul"),
    (("fabio",), "Fabio"),
    (("vault",), "Vault"),
    (("jaeger",), "Jaeger"),
    (("logger", "seq"), "Seq"),
    (("logger", "elk"), "Elasticsearch"),
    (("rabbitMq",), "RabbitMQ"),
]
_PLATFORM_FLAGS = [(("metrics", "prometheusEnabled"), "Prometheus"),
                   (("metrics", "influxEnabled"), "InfluxDB")]  # fmt: skip


class AppSettingsExtractor:
    def matches(self, path: PurePosixPath) -> bool:
        return path.name.lower() == "appsettings.json"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        settings = _parse(file.text)
        if not isinstance(settings, dict):
            return
        reader = _Reader(settings, file)
        yield from reader.service()
        yield from reader.data_stores()
        yield from reader.service_calls()
        yield from reader.messaging()
        yield from reader.platform()


class _Reader:
    def __init__(self, settings: dict[str, Any], file: SourceFile) -> None:
        self.settings = settings
        self.file = file

    def service(self) -> Iterator[Fact]:
        for path in (("app", "service"), ("consul", "service"), ("fabio", "service")):
            if isinstance(name := _get(self.settings, *path), str) and name:
                port = _get(self.settings, "consul", "port")
                yield ServiceDeclared(
                    name=name,
                    port=int(port) if str(port).isdigit() else None,
                    evidence=self._evidence(*path),
                )
                return

    def data_stores(self) -> Iterator[Fact]:
        mongo = _get(self.settings, "mongo", "connectionString")
        if isinstance(mongo, str) and mongo:
            database = _get(self.settings, "mongo", "database")
            raw = mongo.rstrip("/")
            if isinstance(database, str) and database and raw.count("/") < 3:
                raw = f"{raw}/{database}"
            yield DataSourceUsed(
                raw=raw, name="mongo", engine_hint="mongodb", evidence=self._evidence("mongo")
            )
        redis = _get(self.settings, "redis", "connectionString")
        if isinstance(redis, str) and redis:
            host = redis.split(",", 1)[0]
            instance = str(_get(self.settings, "redis", "instance") or "").strip(":")
            yield DataSourceUsed(
                raw=f"redis://{host}/{instance}",
                name="redis",
                engine_hint="redis",
                evidence=self._evidence("redis"),
            )
        strings = _get(self.settings, "ConnectionStrings")
        for name, raw in (strings or {}).items() if isinstance(strings, dict) else []:
            if isinstance(raw, str) and raw:
                yield DataSourceUsed(
                    raw=raw, name=name, evidence=self._evidence("ConnectionStrings", name)
                )

    def service_calls(self) -> Iterator[Fact]:
        services = _get(self.settings, "httpClient", "services")
        for target in services.values() if isinstance(services, dict) else []:
            if isinstance(target, str) and target:
                yield ServiceCalled(
                    service=target,
                    protocol="HTTP",
                    evidence=self._evidence("httpClient", "services"),
                )

    def messaging(self) -> Iterator[Fact]:
        exchange = _get(self.settings, "rabbitMq", "exchange", "name")
        if isinstance(exchange, str) and exchange:
            yield ExchangeOwned(
                name=exchange,
                technology="RabbitMQ",
                evidence=self._evidence("rabbitMq", "exchange"),
            )

    def platform(self) -> Iterator[Fact]:
        for path, name in _PLATFORM_SECTIONS:
            section = _get(self.settings, *path)
            if isinstance(section, dict) and _enabled(_get(section, "enabled"), default=True):
                yield PlatformUsed(name=name, evidence=self._evidence(*path))
        for path, name in _PLATFORM_FLAGS:
            if _enabled(_get(self.settings, *path), default=False):
                yield PlatformUsed(name=name, evidence=self._evidence(*path))

    def _evidence(self, *path: str) -> Any:
        return self.file.evidence(_line_of(self.file.lines, path))


def _parse(text: str) -> Any:
    """JSON with // and /* */ comments and trailing commas, as .NET configuration accepts."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = "\n".join("" if line.lstrip().startswith("//") else line for line in text.splitlines())
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    try:
        return json.loads(text)
    except ValueError:
        return None


def _get(settings: Any, *path: str) -> Any:
    """Value at a path of keys, matched ignoring case; None when absent."""
    for key in path:
        if not isinstance(settings, dict):
            return None
        settings = next((v for k, v in settings.items() if k.lower() == key.lower()), None)
    return settings


def _enabled(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return value is True or str(value).lower() == "true"


def _line_of(lines: list[str], path: tuple[str, ...]) -> int:
    """Line of the last key of a path, found key by key from the top (1 when not found)."""
    start, found = 0, 1
    for key in path:
        quoted = f'"{key.lower()}"'
        for number in range(start, len(lines)):
            if quoted in lines[number].lower():
                start, found = number, number + 1
                break
    return found
