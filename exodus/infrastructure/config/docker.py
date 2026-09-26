"""Docker: the runtime image of each service (Dockerfile) and the services of docker-compose files.

- Dockerfile (Dockerfile, *.Dockerfile, Dockerfile.*): the last FROM is the runtime image; the
  project is the one published (`dotnet publish <path>`) or run (`dotnet <Project>.dll`).
- docker-compose: any YAML file with a top-level `services:` mapping (compose files are often
  not named docker-compose*.yml); each service with an `image:` is reported. Read line by line:
  the format is regular and each fact keeps its exact line.
"""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath, PureWindowsPath

from exodus.application.ports import SourceFile
from exodus.domain.facts import ComposeService, Fact, ImageBuilt

_FROM = re.compile(r"^\s*FROM\s+(?:--\S+\s+)*(\S+)", re.IGNORECASE)
_PUBLISH = re.compile(r"dotnet\s+publish\s+(\S+)", re.IGNORECASE)
_RUN_DLL = re.compile(r"dotnet\s+\"?([\w.]+)\.dll", re.IGNORECASE)
_SERVICE = re.compile(r"^  ([\w.-]+):\s*$")  # a service: two-space indent, a key alone
_IMAGE = re.compile(r"^\s+image:\s*[\"']?([^\"'\s]+)")


class DockerfileExtractor:
    def matches(self, path: PurePosixPath) -> bool:
        name = path.name
        return (
            name == "Dockerfile"
            or name.endswith(".Dockerfile")
            or (name.startswith("Dockerfile.") and path.suffix.lower() not in (".md", ".txt"))
        )

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        runtime: tuple[str, int] | None = None
        project: str | None = None
        for number, line in enumerate(file.lines, start=1):
            if match := _FROM.match(line):
                runtime = (match.group(1), number)
            elif match := _RUN_DLL.search(line):
                project = match.group(1)
            elif (match := _PUBLISH.search(line)) and project is None:
                project = PureWindowsPath(match.group(1).strip("\"'")).stem or None
        if runtime is not None:
            yield ImageBuilt(image=runtime[0], project=project, evidence=file.evidence(runtime[1]))


class ComposeExtractor:
    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() in (".yml", ".yaml")

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        in_services, service = False, None
        for number, line in enumerate(file.lines, start=1):
            if line and not line[0].isspace():  # a top-level key starts or ends the section
                in_services, service = line.rstrip() == "services:", None
                continue
            if not in_services:
                continue
            if match := _SERVICE.match(line):
                service = match.group(1)
            elif (match := _IMAGE.match(line)) and service is not None:
                yield ComposeService(
                    name=service, image=match.group(1), evidence=file.evidence(number)
                )
                service = None
