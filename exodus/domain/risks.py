"""Deterministic, evidence-backed migration risks projected from the architecture graph."""

import re
from enum import StrEnum

from pydantic import Field

from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Entity, Evidence, Node, NodeKind, RelKind


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Risk(Entity):
    rule: str
    severity: Severity
    title: str
    detail: str
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    container_id: str | None = None


def assess_risks(graph: ArchitectureGraph) -> list[Risk]:
    risks: list[Risk] = []
    for container in graph.nodes(NodeKind.CONTAINER):
        risks.extend(_container_risks(container))
    risks.extend(_shared_database_risks(graph))
    return risks


def _container_risks(container: Node) -> list[Risk]:
    risks: list[Risk] = []
    language = container.attributes.get("language", "").lower()
    framework = container.attributes.get("framework", "")
    packages = _attributes(container, "package:")
    runtime = {
        "dotnet": (language in {"c#", "vb"} and _old_dotnet(framework), "Unsupported .NET runtime"),
        "java": (language == "java" and _old_java(framework), "Unsupported Java runtime"),
        "python": (language == "python" and _old_python(framework), "Unsupported Python runtime"),
    }
    for rule, (matched, title) in runtime.items():
        if matched:
            risks.append(
                _risk(f"{rule}-unsupported-runtime", Severity.HIGH, title, framework, container)
            )
    for technology, _ in _attributes(container, "technology:"):
        if technology in {"WCF", "MSMQ", "Web Forms", "Remoting"}:
            risks.append(
                _risk(
                    "dotnet-legacy-technology",
                    Severity.HIGH,
                    "Legacy .NET technology",
                    technology,
                    container,
                )
            )
    for package, version in packages:
        lowered = package.lower()
        if language in {"c#", "vb"} and (
            lowered == "convey" or (lowered == "masstransit" and _version_before(version, (7,)))
        ):
            risks.append(
                _risk(
                    "dotnet-abandoned-package",
                    Severity.MEDIUM,
                    "Legacy .NET package",
                    f"{package} {version}".strip(),
                    container,
                )
            )
        if language == "java" and (
            lowered.startswith("javax.")
            or any(term in lowered for term in ("ejb", "jsf", "jaxws", "jax-ws"))
        ):
            risks.append(
                _risk("java-legacy-api", Severity.HIGH, "Legacy Java EE API", package, container)
            )
        if language == "java" and any(
            server in lowered for server in ("weblogic", "websphere", "jboss")
        ):
            risks.append(
                _risk(
                    "java-application-server",
                    Severity.HIGH,
                    "Coupled application server",
                    package,
                    container,
                )
            )
        old_python_framework = (lowered == "django" and _version_before(version, (4, 2))) or (
            lowered == "flask" and _version_before(version, (2, 2))
        )
        if language == "python" and old_python_framework:
            risks.append(
                _risk(
                    "python-unsupported-framework",
                    Severity.HIGH,
                    "Unsupported Python framework",
                    f"{package} {version}".strip(),
                    container,
                )
            )
    for secret, _ in _attributes(container, "secret:"):
        risks.append(
            _risk(
                "secret-in-configuration",
                Severity.HIGH,
                "Secret in configuration",
                secret,
                container,
            )
        )
    for name, value in _attributes(container, "unresolved-datasource:"):
        risks.append(
            _risk(
                "unresolved-datasource",
                Severity.MEDIUM,
                "Unresolved data source",
                f"{name}: {value}",
                container,
            )
        )
    return risks


def _shared_database_risks(graph: ArchitectureGraph) -> list[Risk]:
    risks: list[Risk] = []
    for store in graph.nodes(NodeKind.DATA_STORE):
        users = [
            r
            for r in graph.relationships(RelKind.DEPENDS_ON)
            if r.target_id == store.id and r.label == "reads/writes"
        ]
        systems = {
            system.id for r in users if (system := graph.ancestor(r.source_id, NodeKind.SYSTEM))
        }
        if len(systems) > 1:
            risks.append(
                Risk(
                    rule="shared-database",
                    severity=Severity.HIGH,
                    title="Shared database",
                    detail=f"{store.name} is used by {len(systems)} systems",
                    evidence=tuple(e for r in users for e in r.evidence),
                )
            )
    return risks


def _risk(rule: str, severity: Severity, title: str, detail: str, container: Node) -> Risk:
    return Risk(
        rule=rule,
        severity=severity,
        title=title,
        detail=detail,
        evidence=container.evidence,
        container_id=container.id,
    )


def _attributes(node: Node, prefix: str) -> list[tuple[str, str]]:
    return [
        (key.removeprefix(prefix), value)
        for key, value in node.attributes.items()
        if key.startswith(prefix)
    ]


def _version_before(value: str, limit: tuple[int, ...]) -> bool:
    numbers = tuple(int(part) for part in re.findall(r"\d+", value))
    return bool(numbers) and numbers < limit


def _old_dotnet(value: str) -> bool:
    pattern = r"\.NET Framework 4\.[0-6](?:\.1)?$|\.NET Core [1-3](?:\.|$)|\.NET [5-7](?:\.|$)"
    return bool(re.search(pattern, value))


def _old_java(value: str) -> bool:
    return bool(re.search(r"Java [6-8](?:\.|$)", value))


def _old_python(value: str) -> bool:
    match = re.search(r"Python\s*(?:[<>=~! ]*)?(\d+)(?:\.(\d+))?", value)
    if match is None:
        return False
    major, minor = int(match.group(1)), int(match.group(2) or 0)
    return major < 3 or (major == 3 and minor <= 8)
