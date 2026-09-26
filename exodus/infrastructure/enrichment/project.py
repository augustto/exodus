"""Local Ollama adapter that infers a system's context (problem, goals, principles,
assumptions, glossary) from numbered extracted facts. Answers are cached by prompt."""

from collections.abc import Callable
from pathlib import Path

from exodus.application.ports import Language, ProjectDraft, ProjectRequest
from exodus.infrastructure.enrichment.cache import ask_cached
from exodus.infrastructure.enrichment.ollama import ANSWER_LANGUAGE, DEFAULT_MODEL

Progress = Callable[[str], None] | None


class OllamaProjectWriter:
    def __init__(
        self, cache_path: Path, language: Language = Language.PT_BR, model: str = DEFAULT_MODEL
    ) -> None:
        self.cache_path = cache_path
        self.language = language
        self.model = model

    def draft(
        self, request: ProjectRequest, progress: Progress = None, thinking: Progress = None
    ) -> ProjectDraft | None:
        what = f"project context of {request.system}"
        return ask_cached(
            self.cache_path,
            self.model,
            _prompt(request, self.language),
            _draft,
            what,
            progress,
            thinking,
        )


def _prompt(request: ProjectRequest, language: Language) -> str:
    return "\n".join(
        [
            "You document a legacy software system for the team that will migrate it. From the "
            "numbered facts (F, extracted from its source code) and documentation excerpts (D, "
            f"from its written documentation) below only, infer, in {ANSWER_LANGUAGE[language]}"
            ": the business problem the system solves; its business goals; the "
            "architecture principles or patterns its code shows (layers, CQRS, events, "
            "microservices...), each citing the fact or excerpt it is based on (F3, D2...); the "
            "assumptions it relies on; and a glossary of the business/domain terms and "
            "acronyms that appear in the facts or excerpts (entities, messages, processes; "
            "not tools, frameworks or products; keep each term exactly as written). Be "
            "concise; do not invent details the facts do not support. Never mention fact or "
            "excerpt numbers in the texts: cite them only in the principles' source field. "
            "Return JSON exactly: "
            '{"problem": string, "goals": [string], "principles": [{"text": string, '
            '"source": "F<number> or D<number>"}], "assumptions": [string], "glossary": [{"term": '
            "string, "
            '"meaning": string}], "confidence": number}.',
            f"System: {request.system}.",
            "Facts:",
            *request.facts,
            *(["Documentation excerpts:", *request.documents] if request.documents else []),
        ]
    )


def _draft(answer: dict[str, object]) -> ProjectDraft | None:
    goals, principles, assumptions, glossary = (
        _list(answer, key) for key in ("goals", "principles", "assumptions", "glossary")
    )
    if goals is None or principles is None or assumptions is None or glossary is None:
        return None
    try:
        confidence = float(str(answer.get("confidence", 0.6)))
    except ValueError:
        return None
    cited = [
        (str(item["text"]), str(source))
        for item in principles
        if isinstance(item, dict)
        and "text" in item
        and (source := item.get("source") or item.get("fact"))  # uncited: dropped
    ]
    return ProjectDraft(
        problem=str(answer.get("problem", "")),
        goals=tuple(str(goal) for goal in goals),
        principles=tuple(cited),
        assumptions=tuple(str(assumption) for assumption in assumptions),
        glossary=tuple(
            (str(t["term"]), str(t["meaning"]))
            for t in glossary
            if isinstance(t, dict) and "term" in t and "meaning" in t
        ),
        confidence=confidence,
    )


def _list(answer: dict[str, object], key: str) -> list[object] | None:
    """The list under key (missing = empty); None when it is not a list."""
    value = answer.get(key, [])
    return value if isinstance(value, list) else None
