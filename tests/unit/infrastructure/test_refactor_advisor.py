from pathlib import Path

import pytest

from exodus.application.ports import (
    PieceRequest,
    StructuralAnswer,
    StructuralRequest,
)
from exodus.domain.refactor import CatalogOption, PieceType
from exodus.infrastructure.enrichment import ollama
from exodus.infrastructure.enrichment.refactor import OllamaRefactorAdvisor

OPTIONS = PieceType(
    id="worker",
    category="compute",
    label="Worker",
    options=(
        CatalogOption(id="lambda-sqs", service="AWS Lambda", when="bursty", cost="per call",
                      security="IAM", performance="cold start"),
    ),
)  # fmt: skip
PIECE = PieceRequest(
    name="audit",
    piece=OPTIONS,
    facts=("entry points: queue consumer",),
    replatform="ECS Fargate",
    priorities=("cost", "security", "performance"),
)


def answering(prompts: list[str], answer: dict[str, object]) -> object:
    def ask(model: str, prompt: str, progress: object, thinking: object) -> dict[str, object]:
        prompts.append(prompt)
        return answer

    return ask


def test_structural_answer_keeps_only_well_formed_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts: list[str] = []
    answer = {
        "merges": [{"service": "web", "into": "api", "justification": "j"}, {"service": "x"}],
        "shared_databases": [{"database": "db", "option": "keep-shared"}],
    }
    monkeypatch.setattr(ollama, "ask", answering(prompts, answer))
    request = StructuralRequest(
        system="shop",
        merges=(("web", "api"),),
        shared=(("db", ("api", "web")),),
        shared_options=OPTIONS,
        facts=("web: api-service",),
        priorities=("cost",),
    )

    assert OllamaRefactorAdvisor(tmp_path / "c.json").structure(request) == StructuralAnswer(
        merges=(("web", "api", "j"),), shared=(("db", "keep-shared", ""),)
    )
    assert "- web into api" in prompts[0]
    assert "- db, used by api, web" in prompts[0]


def test_malformed_answers_give_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    advisor = OllamaRefactorAdvisor(tmp_path / "c.json")
    monkeypatch.setattr(ollama, "ask", answering([], {"justification": "no option"}))
    assert advisor.choose(PIECE) is None
    monkeypatch.setattr(ollama, "ask", answering([], {"option": "x", "confidence": "high"}))
    assert advisor.choose(PIECE) is None
    monkeypatch.setattr(ollama, "ask", answering([], {"merges": "all"}))
    request = StructuralRequest("s", (), (), OPTIONS, (), ())
    assert advisor.structure(request) is None
