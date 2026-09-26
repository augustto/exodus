"""Local Ollama adapter that proposes the refactor by choosing among catalog options.

Prompts carry only extracted facts (never source code), the catalog options with their cost,
security and performance notes, and the priorities in order. Answers are cached by prompt.
"""

from collections.abc import Callable
from pathlib import Path

from exodus.application.ports import (
    Language,
    PieceAnswer,
    PieceRequest,
    StructuralAnswer,
    StructuralRequest,
)
from exodus.domain.refactor import PieceType
from exodus.infrastructure.enrichment.cache import ask_cached
from exodus.infrastructure.enrichment.ollama import ANSWER_LANGUAGE, DEFAULT_MODEL

Progress = Callable[[str], None] | None

_ROLE = (
    "You are a cloud architect planning the modernization (refactor) of a legacy system on AWS. "
    "Decide by these priorities, in this order: {priorities}. Use only the extracted facts "
    "below; do not assume requirements they do not show. Write every justification in "
    "{language}, in one or two sentences naming the priority that decided."
)


def _role(priorities: tuple[str, ...], language: Language) -> str:
    return _ROLE.format(priorities=", ".join(priorities), language=ANSWER_LANGUAGE[language])


class OllamaRefactorAdvisor:
    def __init__(
        self, cache_path: Path, language: Language = Language.PT_BR, model: str = DEFAULT_MODEL
    ) -> None:
        self.cache_path = cache_path
        self.language = language
        self.model = model

    def structure(
        self, request: StructuralRequest, progress: Progress = None, thinking: Progress = None
    ) -> StructuralAnswer | None:
        what = f"refactor structure of {request.system}"
        prompt = _structural_prompt(request, self.language)
        return ask_cached(
            self.cache_path, self.model, prompt, _structural, what, progress, thinking
        )

    def choose(
        self, request: PieceRequest, progress: Progress = None, thinking: Progress = None
    ) -> PieceAnswer | None:
        what = f"refactor target of {request.name}"
        return ask_cached(
            self.cache_path,
            self.model,
            _piece_prompt(request, self.language),
            _piece,
            what,
            progress,
            thinking,
        )


def _options(piece: PieceType) -> list[str]:
    return [
        f"- {o.id}: {o.service}. When: {o.when}. Cost: {o.cost}. Security: {o.security}. "
        f"Performance: {o.performance}."
        for o in piece.options
    ]


def _piece_prompt(request: PieceRequest, language: Language) -> str:
    return "\n".join(
        [
            _role(request.priorities, language),
            "Choose exactly one option id from the list for this element. Return JSON exactly: "
            '{"option": string, "justification": string, "confidence": number}.',
            f"Element: {request.name} ({request.piece.label}).",
            f"Fast-path (replatform) target, for reference: {request.replatform or 'none'}.",
            "Extracted facts:",
            *[f"- {fact}" for fact in request.facts or ("none",)],
            "Options:",
            *_options(request.piece),
        ]
    )


def _structural_prompt(request: StructuralRequest, language: Language) -> str:
    merges = [f"- {service} into {into}" for service, into in request.merges] or ["- none"]
    shared = [
        f"- {database}, used by {', '.join(users)}" for database, users in request.shared
    ] or ["- none"]
    return "\n".join(
        [
            _role(request.priorities, language),
            f"System: {request.system}. Decide only two things. (1) Which candidate services "
            "should merge into another: merging cuts cost, so merge small services that already "
            "move together; keep apart services that must scale or deploy independently. (2) "
            "For each shared database, one option id from the list. Empty lists are valid. "
            'Return JSON exactly: {"merges": [{"service": string, "into": string, '
            '"justification": string}], "shared_databases": [{"database": string, '
            '"option": string, "justification": string}]}.',
            "Services (type; extracted facts):",
            *[f"- {fact}" for fact in request.facts],
            "Merge candidates:",
            *merges,
            "Shared databases:",
            *shared,
            "Options for a shared database:",
            *_options(request.shared_options),
        ]
    )


def _piece(answer: dict[str, object]) -> PieceAnswer | None:
    try:
        return PieceAnswer(
            option_id=str(answer["option"]).strip(),
            justification=str(answer.get("justification", "")),
            confidence=float(str(answer.get("confidence", 0.6))),
        )
    except (KeyError, ValueError):
        return None


def _structural(answer: dict[str, object]) -> StructuralAnswer | None:
    merges, shared = answer.get("merges", []), answer.get("shared_databases", [])
    if not isinstance(merges, list) or not isinstance(shared, list):
        return None
    return StructuralAnswer(
        merges=tuple(
            (str(m["service"]), str(m["into"]), str(m.get("justification", "")))
            for m in merges
            if isinstance(m, dict) and "service" in m and "into" in m
        ),
        shared=tuple(
            (str(s["database"]), str(s["option"]), str(s.get("justification", "")))
            for s in shared
            if isinstance(s, dict) and "database" in s and "option" in s
        ),
    )
