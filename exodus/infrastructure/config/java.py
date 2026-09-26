"""Extract Maven/Gradle metadata and common Java application configuration."""

import re
from collections.abc import Iterable, Iterator
from pathlib import PurePosixPath

from exodus.application.ports import SourceFile
from exodus.domain.facts import (
    DataSourceUsed,
    EndpointCalled,
    EndpointExposed,
    Fact,
    PackageDependency,
    ProjectDeclared,
    ProjectRole,
)
from exodus.domain.identity import url_protocol
from exodus.infrastructure.config.xml_tree import XmlElement, parse_xml

_GRADLE_DEPENDENCY = re.compile(
    r"(?:implementation|api|compileOnly|runtimeOnly|testImplementation|testCompile)\s*\(?\s*[\"']([^\"']+)[\"']"
)
_GRADLE_JAVA = re.compile(
    r"(?:sourceCompatibility|targetCompatibility)\s*=\s*(?:JavaVersion\.VERSION_|[\"'])?([\d._]+)"
)
_PROPERTY = re.compile(r"^\s*([\w.-]+)\s*[=:]\s*(.*?)\s*$")
_ANNOTATION = re.compile(
    r"@(?:RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|Path)\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?[\"']([^\"']+)[\"']"
)


def _text(element: XmlElement | None) -> str | None:
    return element.text.strip() if element is not None and element.text.strip() else None


def _child(root: XmlElement, tag: str) -> XmlElement | None:
    return next((child for child in root.children if child.tag == tag), None)


class MavenExtractor:
    """``pom.xml``: deployable project, Java version and Maven dependencies."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.name.lower() == "pom.xml"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        root = parse_xml(file.text)
        if root is None or root.tag != "project":
            return
        artifact = _text(_child(root, "artifactId")) or file.path.parent.name
        properties = _child(root, "properties")
        java = next(
            (
                child.text.strip()
                for child in (properties.children if properties else [])
                if child.tag in ("java.version", "maven.compiler.release", "maven.compiler.source")
                and child.text.strip()
            ),
            None,
        )
        packaging = _text(_child(root, "packaging"))
        dependencies = list(root.iter("dependency"))
        is_test = artifact.lower().endswith(("-test", "-tests"))
        role = ProjectRole.TEST if is_test else ProjectRole.APPLICATION
        yield ProjectDeclared(
            name=artifact,
            language="Java",
            framework=f"Java {java}" if java else None,
            evidence=file.evidence(root.line),
            role=role,
        )
        if packaging:
            # Preserve the packaging even when no dependency is declared; it is useful inventory.
            yield PackageDependency(
                name="packaging", version=packaging, evidence=file.evidence(root.line)
            )
        for dependency in dependencies:
            group = _text(_child(dependency, "groupId"))
            name = _text(_child(dependency, "artifactId"))
            version = _text(_child(dependency, "version")) or ""
            if name:
                yield PackageDependency(
                    name=f"{group}:{name}" if group else name,
                    version=version,
                    evidence=file.evidence(dependency.line),
                )


class GradleExtractor:
    """``build.gradle``/``build.gradle.kts``: project, configured Java and dependencies."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.name.lower() in ("build.gradle", "build.gradle.kts")

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        framework = None
        if match := _GRADLE_JAVA.search(file.text):
            framework = f"Java {match.group(1).replace('_', '.')}"
        name = file.path.parent.name
        is_test = name.lower().endswith(("-test", "-tests"))
        yield ProjectDeclared(
            name=name,
            language="Java",
            framework=framework,
            evidence=file.evidence(1),
            role=ProjectRole.TEST if is_test else ProjectRole.APPLICATION,
        )
        for match in _GRADLE_DEPENDENCY.finditer(file.text):
            value = match.group(1)
            parts = value.split(":")
            if len(parts) >= 2:
                yield PackageDependency(
                    name=":".join(parts[:2]),
                    version=parts[2] if len(parts) >= 3 else "",
                    evidence=file.evidence(file.line_at(match.start())),
                )


class JavaConfigExtractor:
    """Spring-style ``application.properties`` and YAML: JDBC URLs and HTTP calls."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.name.lower() in (
            "application.properties",
            "application.yml",
            "application.yaml",
        )

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        values = _properties(file) if file.path.suffix == ".properties" else _yaml_values(file)
        for key, value, line in values:
            lowered = key.lower()
            if value.lower().startswith("jdbc:"):
                yield DataSourceUsed(raw=value, name=key, evidence=file.evidence(line))
            elif value.lower().startswith(("http://", "https://")) and any(
                token in lowered for token in ("url", "uri", "endpoint")
            ):
                yield EndpointCalled(
                    url=value, protocol=url_protocol(value), evidence=file.evidence(line)
                )


class JavaEndpointExtractor:
    """HTTP paths declared by Spring MVC and JAX-RS annotations."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() == ".java"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        for match in _ANNOTATION.finditer(file.text):
            yield EndpointExposed(
                path=match.group(1),
                protocol="HTTP",
                evidence=file.evidence(file.line_at(match.start())),
            )


def _properties(file: SourceFile) -> Iterator[tuple[str, str, int]]:
    for line, text in enumerate(file.lines, start=1):
        if match := _PROPERTY.match(text):
            yield match.group(1), match.group(2).strip().strip("\"'"), line


def _yaml_values(file: SourceFile) -> Iterator[tuple[str, str, int]]:
    """Small, dependency-free YAML reader for nested scalar settings relevant to Java apps."""
    parents: list[tuple[int, str]] = []
    for line, text in enumerate(file.lines, start=1):
        if not text.strip() or text.lstrip().startswith("#") or ":" not in text:
            continue
        indent = len(text) - len(text.lstrip())
        key, _, value = text.strip().partition(":")
        key = key.strip("\"' ")
        while parents and indent <= parents[-1][0]:
            parents.pop()
        if not value.strip():
            parents.append((indent, key))
            continue
        path = ".".join([part for _, part in parents] + [key])
        yield path, value.strip().strip("\"'"), line
