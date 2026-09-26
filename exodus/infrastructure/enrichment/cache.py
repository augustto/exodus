"""Ask the local model through a content-addressed cache of its JSON answers.

An answer is cached by the hash of its prompt, and only once it parses: a malformed answer is
asked again next time, a cached one never is.
"""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from urllib.error import URLError

from exodus.infrastructure.enrichment import ollama

Progress = Callable[[str], None] | None


def ask_cached[T](
    cache_path: Path,
    model: str,
    prompt: str,
    parse: Callable[[dict[str, object]], T | None],
    what: str,
    progress: Progress = None,
    thinking: Progress = None,
) -> T | None:
    """The parsed answer to prompt, from the cache or from the model; None if there is none."""
    key = hashlib.sha256(prompt.encode()).hexdigest()
    cache = _load(cache_path)
    answer = cache.get(key)
    if answer is None:
        _report(progress, f"Ollama: {what}")
        try:
            answer = ollama.ask(model, prompt, progress, thinking)
        except (URLError, OSError, ValueError):
            _report(progress, f"Ollama unavailable or response invalid: {what}")
            return None
    else:
        _report(progress, f"Ollama: cached {what}")
    parsed = parse(answer)
    if parsed is not None and key not in cache:
        cache[key] = answer
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return parsed


def _load(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _report(progress: Progress, message: str) -> None:
    if progress is not None:
        progress(message)
