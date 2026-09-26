"""Local Ollama adapter with a content-addressed response cache."""

import hashlib
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request

from exodus.application.ports import Language
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence, Inference, Node, NodeKind
from exodus.infrastructure.local_http import DIRECT_OPENER

DEFAULT_MODEL = "qwen3.5:9b"
TIMEOUT_SECONDS = 120
CONTEXT_TOKENS = 8192  # room for the source files of a use case; Ollama's default is smaller
# the language the model answers in, as named in the prompts
ANSWER_LANGUAGE = {Language.PT_BR: "Brazilian Portuguese", Language.EN: "English"}


class OllamaEnricher:
    def __init__(
        self, cache_path: Path, language: Language = Language.PT_BR, model: str = DEFAULT_MODEL
    ) -> None:
        self.cache_path = cache_path
        self.language = language
        self.model = model

    def enrich(
        self,
        graph: ArchitectureGraph,
        progress: Callable[[str], None] | None = None,
        thinking: Callable[[str], None] | None = None,
    ) -> ArchitectureGraph:
        cache = self._load_cache()
        nodes = [
            node
            for node in graph.nodes()
            if node.kind in (NodeKind.SYSTEM, NodeKind.CONTAINER, NodeKind.COMPONENT)
        ]
        for number, node in enumerate(nodes, start=1):
            prompt = _prompt(node, self.language)
            key = hashlib.sha256(prompt.encode()).hexdigest()
            response = cache.get(key)
            if response is not None:
                _report(progress, f"Ollama: cache {number}/{len(nodes)} ({node.name})")
            else:
                _report(progress, f"Ollama: generating {number}/{len(nodes)} ({node.name})")
                response = self._ask(prompt, node.evidence, progress, thinking)
            if response is None:
                _report(progress, "Ollama unavailable or response invalid; keeping extracted graph")
                continue
            cache[key] = response
            graph.add_node(node.model_copy(update={"description": response}))
        if cache:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(
                    {key: value.model_dump(mode="json") for key, value in cache.items()}, indent=2
                ),
                encoding="utf-8",
            )
        return graph

    def _load_cache(self) -> dict[str, Inference]:
        if not self.cache_path.is_file():
            return {}
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return {key: Inference.model_validate(value) for key, value in raw.items()}
        except (json.JSONDecodeError, OSError, ValueError):
            return {}

    def _ask(
        self,
        prompt: str,
        evidence: tuple[Evidence, ...],
        progress: Callable[[str], None] | None,
        thinking: Callable[[str], None] | None,
    ) -> Inference | None:
        try:
            answer = ask(self.model, prompt, progress, thinking)
            text = str(answer["description"]).strip()
            confidence = float(str(answer.get("confidence", 0.6)))
            return Inference(text=text, confidence=confidence, evidence=evidence)
        except (KeyError, TypeError, ValueError, URLError, OSError):
            return None


def ask(
    model: str,
    prompt: str,
    progress: Callable[[str], None] | None,
    thinking: Callable[[str], None] | None,
) -> dict[str, object]:
    """Send a prompt to the local Ollama and return its JSON answer. Raises URLError/OSError
    when Ollama is unreachable and ValueError when the answer is not a JSON object."""
    request = Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(_payload(model, prompt, think=thinking is not None)).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with DIRECT_OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
        answer, reasoning = _stream(response, progress, thinking)
    if reasoning:
        _report(progress, "Ollama: thinking complete; validating structured response")
    return answer


def _payload(model: str, prompt: str, think: bool) -> dict[str, object]:
    """Ollama request body. Thinking is opt-in: it takes 30-100 s per element on 8 GB of VRAM,
    against ~1 s without it."""
    payload: dict[str, object] = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "think": think,
        "options": {"num_ctx": CONTEXT_TOKENS},
    }
    if not think:
        # Only without thinking: Ollama applies the JSON grammar to the thinking too,
        # turning the reasoning into made-up JSON.
        payload["format"] = "json"
    return payload


def _prompt(node: Node, language: Language) -> str:
    extracted = {
        key: value for key, value in node.attributes.items() if not key.startswith("secret:")
    }
    sentence = "Portuguese" if language is Language.PT_BR else "English"
    return (
        f"You document legacy software architecture. Infer one concise {sentence} sentence about "
        "the responsibility of this element using only the extracted facts below. Do not invent "
        'details. Return JSON exactly: {"description": string, "confidence": number}.\n'
        + json.dumps(
            {
                "name": node.name,
                "kind": node.kind,
                "technology": node.technology,
                "attributes": extracted,
                "evidence": [str(e) for e in node.evidence],
            },
            sort_keys=True,
        )
    )


def _report(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _stream(
    response: Iterable[bytes],
    progress: Callable[[str], None] | None,
    thinking: Callable[[str], None] | None,
) -> tuple[dict[str, object], str]:
    """Consume Ollama's JSONL stream, handing each thinking fragment to `thinking` as it
    arrives (or only its running size to `progress`), and parse the JSON answer."""
    text: list[str] = []
    reasoning: list[str] = []
    for raw in response:
        chunk = json.loads(raw)
        text.append(str(chunk.get("response", "")))
        fragment = str(chunk.get("thinking", ""))
        if fragment:
            reasoning.append(fragment)
            if thinking is not None:
                thinking(fragment)
            else:
                _report(progress, f"Ollama raciocinando ({len(''.join(reasoning))} caracteres)")
    return _json_object("".join(text)), "".join(reasoning)


def _json_object(text: str) -> dict[str, object]:
    """The JSON object in a free-text answer (tolerates ```json fences and surrounding prose)."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"no JSON object in the answer: {text[:80]!r}")
    answer = json.loads(text[start : end + 1])
    if not isinstance(answer, dict):
        raise ValueError("the answer is not a JSON object")
    return answer
