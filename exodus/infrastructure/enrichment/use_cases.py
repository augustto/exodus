"""Local Ollama adapter that drafts use cases, with a content-addressed answer cache."""

from collections.abc import Callable
from pathlib import Path

from exodus.application.ports import DraftStep, Language, UseCaseDraft, UseCaseRequest
from exodus.infrastructure.enrichment.cache import ask_cached
from exodus.infrastructure.enrichment.ollama import ANSWER_LANGUAGE, DEFAULT_MODEL


class OllamaUseCaseWriter:
    def __init__(
        self, cache_path: Path, language: Language = Language.PT_BR, model: str = DEFAULT_MODEL
    ) -> None:
        self.cache_path = cache_path
        self.language = language
        self.model = model

    def draft(
        self,
        request: UseCaseRequest,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> UseCaseDraft | None:
        what = f"use case {request.entry.kind} {request.entry.name}"
        return ask_cached(
            self.cache_path,
            self.model,
            _prompt(request, self.language),
            _draft,
            what,
            progress,
            thinking,
        )


def _prompt(request: UseCaseRequest, language: Language) -> str:
    entry = request.entry
    answer = ANSWER_LANGUAGE[language]
    parts = [
        "You document legacy software. Describe what happens when the entry point below is "
        "triggered, using only the numbered code below. Write the title and every step in "
        f"{answer}. Describe the behavior (validations, reads, writes, calls, "
        "published messages), not the plumbing: skip constructors, dependency injection and "
        "fields. Keep code identifiers and domain terms (class, entity, message and enum names) "
        "exactly as written in the code, never translated. Every step cites the file and the "
        "line number it comes from, exactly as numbered, in the file and line fields only "
        "(not in the text). Do not "
        'invent steps or details. "touches" lists only the names, among the elements the '
        "container uses, that this code clearly reads, writes, calls or publishes to; leave it "
        'empty when unsure. Return JSON exactly: {"title": string, "steps": [{"text": string, '
        '"file": string, "line": number}], "touches": [string], "confidence": number}.',
        f"Entry point: {entry.kind} {entry.name} at {entry.file}:{entry.line} "
        f"(container {request.container}).",
        "Elements the container uses: " + (", ".join(request.candidates) or "none") + ".",
        f"Answer in {answer}.",
    ]
    for source in request.sources:
        parts.append(f"--- {source.path}")
        parts += [
            f"{number}: {line}" for number, line in enumerate(source.lines, start=source.first_line)
        ]
    return "\n".join(parts)


def _draft(answer: dict[str, object]) -> UseCaseDraft | None:
    """The draft in a model answer; malformed steps are dropped, a malformed answer is None."""
    steps = answer.get("steps")
    touches = answer.get("touches", [])
    if not isinstance(steps, list) or not isinstance(touches, list):
        return None
    try:
        confidence = float(str(answer.get("confidence", 0.6)))
    except ValueError:
        return None
    return UseCaseDraft(
        title=str(answer.get("title", "")),
        steps=tuple(step for step in map(_step, steps) if step is not None),
        touches=tuple(str(name) for name in touches),
        confidence=confidence,
    )


def _step(raw: object) -> DraftStep | None:
    if not isinstance(raw, dict):
        return None
    try:
        return DraftStep(text=str(raw["text"]), file=str(raw["file"]), line=int(raw["line"]))
    except (KeyError, TypeError, ValueError):
        return None
