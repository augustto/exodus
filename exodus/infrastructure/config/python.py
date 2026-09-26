"""Extract Python project metadata, database URLs and common web endpoints."""

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

_ASSIGNMENT = re.compile(r"^\s*([\w-]+)\s*=\s*[\"']([^\"']+)[\"']\s*$")
_REQUIREMENT = re.compile(r"^\s*([\w.-]+)(?:\[.*?\])?\s*(?:([=~!<>]{1,2})\s*([^;\s]+))?")
_QUOTED = re.compile(r"[\"']([^\"']+)[\"']")
_DATABASE_URL = re.compile(
    r"(?:DATABASE_URL|create_engine\s*\()\s*(?:=\s*)?[\"']([^\"']+)[\"']", re.IGNORECASE
)
_HTTP_URL = re.compile(r"https?://[^\s\"'<>()\[\]{};,`]+", re.IGNORECASE)
# Shared with PythonEntryPointExtractor: same routes feed EndpointExposed (graph linking) and
# EntryPoint (inventory) facts.
ROUTE = re.compile(
    r"@(?:\w+\.)?(?:app|router|blueprint)\.(?:route|get|post|put|patch|delete)\s*\(\s*[\"']([^\"']+)[\"']"
)
DJANGO_ROUTE = re.compile(r"\b(?:path|re_path)\s*\(\s*[\"']([^\"']+)[\"']")


class PythonProjectExtractor:
    """``pyproject.toml``, ``setup.py`` and ``Pipfile`` declare Python containers."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.name.lower() in ("pyproject.toml", "setup.py", "pipfile")

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        name, version, dependencies = _project_metadata(file)
        if name is None:
            return
        yield ProjectDeclared(
            name=name,
            language="Python",
            framework=f"Python {version}" if version else None,
            evidence=file.evidence(1),
            role=(
                ProjectRole.TEST
                if name.lower().endswith(("-test", "-tests"))
                else ProjectRole.APPLICATION
            ),
        )
        yield from _packages(dependencies, file)


class RequirementsExtractor:
    """Dependencies in a standalone ``requirements.txt`` or alongside a project manifest."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.name.lower().startswith("requirements") and path.suffix.lower() == ".txt"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        for line, text in enumerate(file.lines, start=1):
            value = text.split("#", 1)[0].strip()
            if not value or value.startswith(("-", "git+", "http:")):
                continue
            if match := _REQUIREMENT.match(value):
                yield PackageDependency(
                    name=match.group(1), version=match.group(3) or "", evidence=file.evidence(line)
                )


class PythonConfigExtractor:
    """Django/SQLAlchemy config and simple INI/YAML values containing database or HTTP URLs."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.name.lower() in (
            "settings.py",
            "settings.ini",
            "application.yml",
            "application.yaml",
        )

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        for match in _DATABASE_URL.finditer(file.text):
            raw = match.group(1)
            yield DataSourceUsed(
                raw=raw, name="database", evidence=file.evidence(file.line_at(match.start(1)))
            )
        for match in _HTTP_URL.finditer(file.text):
            url = match.group(0).rstrip(".")
            yield EndpointCalled(
                url=url,
                protocol=url_protocol(url),
                evidence=file.evidence(file.line_at(match.start())),
            )


class PythonEndpointExtractor:
    """Flask/FastAPI decorators and Django ``path`` declarations."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() == ".py"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        for pattern in (ROUTE, DJANGO_ROUTE):
            for match in pattern.finditer(file.text):
                path = match.group(1)
                yield EndpointExposed(
                    path=path if path.startswith("/") else f"/{path}",
                    protocol="HTTP",
                    evidence=file.evidence(file.line_at(match.start())),
                )


def _project_metadata(file: SourceFile) -> tuple[str | None, str | None, list[str]]:
    name = version = None
    dependencies: list[str] = []
    if file.path.name == "setup.py":
        name = _keyword(file.text, "name")
        version = _keyword(file.text, "python_requires")
        dependencies = _quoted_after(file.text, "install_requires")
    elif file.path.name == "Pipfile":
        name = file.path.parent.name
        version = _toml_value(file.text, "python_version") or _toml_value(
            file.text, "python_full_version"
        )
        dependencies = _toml_section_values(file.text, "packages")
    else:
        name = _toml_value(file.text, "name")
        version = _toml_value(file.text, "requires-python")
        dependencies = _quoted_after(file.text, "dependencies")
    return name, version, dependencies


def _toml_value(text: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE)
    return match.group(1) if match else None


def _keyword(text: str, key: str) -> str | None:
    match = re.search(rf"\b{re.escape(key)}\s*=\s*[\"']([^\"']+)[\"']", text)
    return match.group(1) if match else None


def _quoted_after(text: str, key: str) -> list[str]:
    match = re.search(rf"\b{re.escape(key)}\s*=\s*\[(.*?)\]", text, re.DOTALL)
    return _QUOTED.findall(match.group(1)) if match else []


def _toml_section_values(text: str, section: str) -> list[str]:
    match = re.search(
        rf"^\s*\[{re.escape(section)}\]\s*(.*?)(?=^\s*\[|\Z)", text, re.DOTALL | re.MULTILINE
    )
    if match is None:
        return []
    values = re.findall(r"^\s*([\w.-]+)\s*=\s*[\"']([^\"']+)", match.group(1), re.MULTILINE)
    return [value for _, value in values]


def _packages(values: Iterable[str], file: SourceFile) -> Iterator[Fact]:
    for value in values:
        if match := _REQUIREMENT.match(value):
            yield PackageDependency(
                name=match.group(1), version=match.group(3) or "", evidence=file.evidence(1)
            )
