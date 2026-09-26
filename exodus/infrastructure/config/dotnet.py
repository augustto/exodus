"""Extractors for .NET project, solution and config files (.NET Framework and .NET Core/5+)."""

import re
from collections.abc import Iterable, Iterator
from pathlib import PurePosixPath, PureWindowsPath

from exodus.application.ports import SourceFile
from exodus.domain.facts import (
    DataSourceUsed,
    EndpointCalled,
    EndpointExposed,
    Fact,
    PackageDependency,
    ProjectDeclared,
    ProjectReference,
    ProjectRole,
    QueueUsed,
    SolutionEntry,
)
from exodus.domain.identity import engine_from_provider, url_protocol
from exodus.domain.model import RelKind
from exodus.infrastructure.config.xml_tree import XmlElement, parse_xml

_PROJECT_LANGUAGES = {".csproj": "C#", ".vbproj": "VB.NET"}

# SDKs and legacy project type GUIDs of deployable projects (web apps, WCF services, workers)
_APPLICATION_SDKS = ("Microsoft.NET.Sdk.Web", "Microsoft.NET.Sdk.Worker", "Microsoft.NET.Sdk.Razor")
_APPLICATION_TYPE_GUIDS = {
    "349c5851-65df-11da-9384-00065b846f21",  # ASP.NET web application
    "3d9ad99f-2412-4246-b90b-4eaa41c64699",  # WCF service application
    "e3e379df-f4c6-4180-9b81-6769533abe47",  # ASP.NET MVC 4
    "e53f8fea-eae0-44a6-8774-ffd645390401",  # ASP.NET MVC 3
    "f85e285d-a4e0-4152-9332-ab1d724d3325",  # ASP.NET MVC 2
    "603c0e0b-db56-11dc-be95-000d561079b0",  # ASP.NET MVC 1
}
_TEST_PACKAGES = ("microsoft.net.test.sdk", "xunit", "nunit", "mstest.testframework")
_TEST_ASSEMBLIES = ("nunit.framework", "microsoft.visualstudio.qualitytools.unittestframework")
_PROJECT_FILE = re.compile(
    r'^Project\("\{[^}]+\}"\)\s*=\s*"([^"]+)",\s*"([^"]+\.(?:cs|vb)proj)"', re.I
)

_BINDING_PROTOCOLS = {
    "basichttpbinding": "SOAP",
    "wshttpbinding": "SOAP",
    "ws2007httpbinding": "SOAP",
    "nettcpbinding": "WCF net.tcp",
    "netnamedpipebinding": "WCF net.pipe",
    "webhttpbinding": "HTTP/REST",
}

_PAGE_PROTOCOLS = {".svc": "SOAP", ".asmx": "SOAP", ".aspx": "HTTP", ".ashx": "HTTP"}

_URL_PREFIXES = ("http://", "https://", "net.tcp://", "net.pipe://")


def framework_label(value: str) -> str:
    """'v4.0'/'net48' -> '.NET Framework 4.x'; 'netcoreapp3.1' -> '.NET Core 3.1';
    'net5.0'/'net8.0-windows' -> '.NET 5.0'/'.NET 8.0'; 'netstandard2.0' -> '.NET Standard 2.0';
    others unchanged."""
    value = value.strip()
    if match := re.fullmatch(r"v(\d+(?:\.\d+)*)", value):
        return f".NET Framework {match.group(1)}"
    if match := re.fullmatch(r"net(\d)(\d)(\d?)", value):
        return ".NET Framework " + ".".join(d for d in match.groups() if d)
    if match := re.fullmatch(r"netcoreapp(\d+\.\d+)", value):
        return f".NET Core {match.group(1)}"
    if match := re.fullmatch(r"netstandard(\d+\.\d+)", value):
        return f".NET Standard {match.group(1)}"
    if match := re.fullmatch(r"net(\d+\.\d+)(?:-\w+)?", value):
        return f".NET {match.group(1)}"
    return value


def project_role(root: XmlElement) -> ProjectRole:
    """Test project (test framework packages/assemblies or IsTestProject), application (web/
    worker SDK, executable output or web/WCF project type) or library."""
    packages = [p.attrs.get("Include", "").lower() for p in root.iter("PackageReference")]
    assemblies = [r.attrs.get("Include", "").lower() for r in root.iter("Reference")]
    is_test = any(e.text.strip().lower() == "true" for e in root.iter("IsTestProject"))
    if (
        is_test
        or any(p in _TEST_PACKAGES for p in packages)
        or any(a.split(",")[0] in _TEST_ASSEMBLIES for a in assemblies)
    ):
        return ProjectRole.TEST
    output = next((e.text.strip().lower() for e in root.iter("OutputType")), "")
    guids = {
        g.strip("{} ").lower() for e in root.iter("ProjectTypeGuids") for g in e.text.split(";")
    }
    if (
        root.attrs.get("Sdk", "") in _APPLICATION_SDKS
        or output in ("exe", "winexe")
        or guids & _APPLICATION_TYPE_GUIDS
    ):
        return ProjectRole.APPLICATION
    return ProjectRole.LIBRARY


class CsprojExtractor:
    """.csproj/.vbproj: project and its role, framework version, project references,
    PackageReference."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() in _PROJECT_LANGUAGES

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        root = parse_xml(file.text)
        if root is None:
            return
        framework_el = next(
            (
                e
                for tag in ("TargetFrameworkVersion", "TargetFramework", "TargetFrameworks")
                for e in root.iter(tag)
            ),
            None,
        )
        framework = framework_label(framework_el.text.split(";")[0]) if framework_el else None
        yield ProjectDeclared(
            name=file.path.stem,
            language=_PROJECT_LANGUAGES[file.path.suffix.lower()],
            framework=framework,
            evidence=file.evidence(framework_el.line if framework_el else root.line),
            role=project_role(root),
        )
        for ref in root.iter("ProjectReference"):
            include = ref.attrs.get("Include", "")
            if include:
                yield ProjectReference(
                    target=PureWindowsPath(include).stem, evidence=file.evidence(ref.line)
                )
        for pkg in root.iter("PackageReference"):
            name = pkg.attrs.get("Include", "")
            version = pkg.attrs.get("Version") or pkg.child_text("Version") or ""
            if name:
                yield PackageDependency(
                    name=name, version=version, evidence=file.evidence(pkg.line)
                )


class SolutionExtractor:
    """.sln: the projects it lists (solution folders are skipped)."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() == ".sln"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        for number, line in enumerate(file.lines, start=1):
            if match := _PROJECT_FILE.match(line.strip()):
                path = PureWindowsPath(match.group(2)).as_posix()
                yield SolutionEntry(name=match.group(1), path=path, evidence=file.evidence(number))


class PackagesConfigExtractor:
    """Legacy NuGet packages.config."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.name.lower() == "packages.config"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        root = parse_xml(file.text)
        if root is None:
            return
        for pkg in root.iter("package"):
            if name := pkg.attrs.get("id"):
                yield PackageDependency(
                    name=name,
                    version=pkg.attrs.get("version", ""),
                    evidence=file.evidence(pkg.line),
                )


class WebConfigExtractor:
    """web.config / app.config: connection strings, WCF client/service endpoints, MSMQ, URLs."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.name.lower() in ("web.config", "app.config")

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        root = parse_xml(file.text)
        if root is None:
            return
        yield from self._connection_strings(root, file)
        yield from self._app_settings(root, file)
        yield from self._wcf_client(root, file)
        yield from self._wcf_services(root, file)

    def _connection_strings(self, root: XmlElement, file: SourceFile) -> Iterator[Fact]:
        for add in root.find_all("connectionStrings/add"):
            raw = add.attrs.get("connectionString", "")
            if raw:
                yield DataSourceUsed(
                    raw=raw,
                    name=add.attrs.get("name"),
                    engine_hint=engine_from_provider(add.attrs.get("providerName")),
                    evidence=file.evidence(add.line),
                )

    def _app_settings(self, root: XmlElement, file: SourceFile) -> Iterator[Fact]:
        for add in root.find_all("appSettings/add"):
            value = add.attrs.get("value", "").strip()
            if value.lower().startswith(_URL_PREFIXES):
                yield EndpointCalled(
                    url=value, protocol=url_protocol(value), evidence=file.evidence(add.line)
                )

    def _wcf_client(self, root: XmlElement, file: SourceFile) -> Iterator[Fact]:
        for endpoint in root.find_all("client/endpoint"):
            address = endpoint.attrs.get("address", "").strip()
            evidence = file.evidence(endpoint.line)
            if address.lower().startswith("net.msmq://"):
                yield QueueUsed(raw=address, direction=RelKind.PUBLISHES, evidence=evidence)
            elif address.lower().startswith(_URL_PREFIXES):
                protocol = _binding_protocol(endpoint) or url_protocol(address)
                yield EndpointCalled(url=address, protocol=protocol, evidence=evidence)

    def _wcf_services(self, root: XmlElement, file: SourceFile) -> Iterator[Fact]:
        for endpoint in root.find_all("services/service/endpoint"):
            address = endpoint.attrs.get("address", "").strip()
            if address.lower().startswith("net.msmq://"):
                yield QueueUsed(
                    raw=address, direction=RelKind.CONSUMES, evidence=file.evidence(endpoint.line)
                )
        for activation in root.find_all("serviceActivations/add"):
            if relative := activation.attrs.get("relativeAddress", "").strip("~/ "):
                yield EndpointExposed(
                    path=f"/{relative}", protocol="SOAP", evidence=file.evidence(activation.line)
                )


def _binding_protocol(endpoint: XmlElement) -> str | None:
    return _BINDING_PROTOCOLS.get(endpoint.attrs.get("binding", "").lower())


class AspNetEndpointExtractor:
    """.svc/.asmx (SOAP) and .aspx/.ashx (HTTP) files are endpoints served at their file name."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() in _PAGE_PROTOCOLS

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        # only the file name is used: the virtual directory is unknown statically, and matching
        # looks for the exposed segments anywhere in the called URL path
        yield EndpointExposed(
            path=f"/{file.path.name}",
            protocol=_PAGE_PROTOCOLS[file.path.suffix.lower()],
            evidence=file.evidence(1),
        )
