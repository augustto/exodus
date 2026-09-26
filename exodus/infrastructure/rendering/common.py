"""Formatting helpers shared by the renderers."""

import re
from collections.abc import Sequence

from exodus.application.ports import Language
from exodus.domain.model import Evidence

EVIDENCE_LIMIT = 5


def evidence_summary(evidence: Sequence[Evidence], limit: int = EVIDENCE_LIMIT) -> str:
    shown = ", ".join(str(e) for e in evidence[:limit])
    hidden = len(evidence) - limit
    return f"{shown} (+{hidden} more)" if hidden > 0 else shown


def pick(language: Language, pt_br: str, en: str) -> str:
    """The fixed text of a document in its language."""
    return pt_br if language is Language.PT_BR else en


# fixed phrases the domain writes in English (reasons, evidence summaries), in Portuguese
_PHRASES = [
    (re.compile(r"\bruntime upgrade from\b"), "upgrade do runtime"),
    (re.compile(r"^upgrade (?!do runtime)"), "upgrade de "),
    (re.compile(r"\bcall each other:"), "chamam um ao outro:"),
    (re.compile(r"\bcalls\b"), "chama"),
    (re.compile(r"^share\b"), "compartilha"),
    (re.compile(r"\(wave (\d+)\)"), r"(onda \1)"),
    (re.compile(r"\bin earlier waves\b"), "em ondas anteriores"),
    (re.compile(r"\(\+(\d+) more\)"), r"(+\1 outros)"),
]


def localize(text: str, language: Language) -> str:
    """A phrase written by the domain (in English) in the document's language."""
    if language is Language.EN:
        return text
    for pattern, replacement in _PHRASES:
        text = pattern.sub(replacement, text)
    return text
