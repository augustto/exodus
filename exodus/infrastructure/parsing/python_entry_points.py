"""Entry points found in Python source, Celery tasks, schedulers and CLI commands."""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath

from exodus.application.ports import SourceFile
from exodus.domain.facts import EntryPoint, Fact
from exodus.infrastructure.config.python import DJANGO_ROUTE, ROUTE

_CELERY_TASK = re.compile(r"@(?:\w+\.)?(?:task|shared_task)\b[^\n]*\n\s*def\s+(\w+)\s*\(")
_APSCHEDULER = re.compile(r"@(?:\w+\.)?scheduled_job\s*\([^)]*\)\s*\n\s*def\s+(\w+)\s*\(")
_APSCHEDULER_ADD_JOB = re.compile(r"\badd_job\s*\(\s*(\w+)")
_QUEUE_CONSUMER = re.compile(r"\bbasic_consume\s*\([^)]*queue\s*=\s*[\"']([^\"']+)[\"']")
_DJANGO_COMMAND = re.compile(r"class\s+Command\s*\(\s*BaseCommand\s*\)")


class PythonEntryPointExtractor:
    """Flask/FastAPI/Django routes, Celery tasks, APScheduler jobs and pika consumers."""

    def matches(self, path: PurePosixPath) -> bool:
        return path.suffix.lower() == ".py"

    def extract(self, file: SourceFile) -> Iterable[Fact]:
        for pattern in (ROUTE, DJANGO_ROUTE):
            for match in pattern.finditer(file.text):
                path = match.group(1)
                yield EntryPoint(
                    kind="HTTP",
                    name=path if path.startswith("/") else f"/{path}",
                    evidence=file.evidence(file.line_at(match.start())),
                )
        for match in _CELERY_TASK.finditer(file.text):
            yield EntryPoint(
                kind="scheduled task",
                name=match.group(1),
                evidence=file.evidence(file.line_at(match.start())),
            )
        for match in _APSCHEDULER.finditer(file.text):
            yield EntryPoint(
                kind="scheduled job",
                name=match.group(1),
                evidence=file.evidence(file.line_at(match.start())),
            )
        for match in _APSCHEDULER_ADD_JOB.finditer(file.text):
            yield EntryPoint(
                kind="scheduled job",
                name=match.group(1),
                evidence=file.evidence(file.line_at(match.start())),
            )
        for match in _QUEUE_CONSUMER.finditer(file.text):
            yield EntryPoint(
                kind="queue consumer",
                name=match.group(1),
                evidence=file.evidence(file.line_at(match.start())),
            )
        if file.path.parent.name == "commands" and (command := _DJANGO_COMMAND.search(file.text)):
            yield EntryPoint(
                kind="CLI command",
                name=file.path.stem,
                evidence=file.evidence(file.line_at(command.start())),
            )
