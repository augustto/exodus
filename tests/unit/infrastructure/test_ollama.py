import json

import pytest

from exodus.infrastructure.enrichment.ollama import _payload, _stream


def test_stream_reports_thinking_only_to_progress_callback() -> None:
    updates: list[str] = []
    chunks = [
        json.dumps({"thinking": "Inspecting the endpoint "}).encode() + b"\n",
        json.dumps({"thinking": "and its dependencies."}).encode() + b"\n",
        json.dumps({"response": '{"description":"Handles orders.","confidence":0.8}'}).encode()
        + b"\n",
    ]

    answer, thinking = _stream(chunks, updates.append, None)

    assert answer == {"description": "Handles orders.", "confidence": 0.8}
    assert thinking == "Inspecting the endpoint and its dependencies."
    assert updates == [
        "Ollama raciocinando (24 caracteres)",
        "Ollama raciocinando (45 caracteres)",
    ]


def test_stream_hands_each_thinking_fragment_to_the_thinking_sink() -> None:
    updates: list[str] = []
    fragments: list[str] = []
    chunks = [
        json.dumps({"thinking": "Okay, let's see. "}).encode() + b"\n",
        json.dumps({"thinking": "It hosts the API."}).encode() + b"\n",
        json.dumps({"response": '{"description":"Handles orders."}'}).encode() + b"\n",
    ]

    _stream(chunks, updates.append, fragments.append)

    assert fragments == ["Okay, let's see. ", "It hosts the API."]
    assert updates == []


def test_stream_extracts_the_json_object_from_a_free_text_answer() -> None:
    chunks = [
        json.dumps({"response": '```json\n{"description": "Handles orders.",'}).encode() + b"\n",
        json.dumps({"response": ' "confidence": 0.9}\n```'}).encode() + b"\n",
    ]

    answer, _ = _stream(chunks, None, None)

    assert answer == {"description": "Handles orders.", "confidence": 0.9}


def test_stream_rejects_an_answer_without_json() -> None:
    chunks = [json.dumps({"response": "Sorry, I cannot."}).encode() + b"\n"]

    with pytest.raises(ValueError):
        _stream(chunks, None, None)


def test_payload_asks_for_json_without_thinking_by_default() -> None:
    payload = _payload("qwen3.5:9b", "prompt", think=False)

    assert payload["think"] is False
    assert payload["format"] == "json"


def test_payload_with_thinking_leaves_the_answer_format_free() -> None:
    payload = _payload("qwen3.5:9b", "prompt", think=True)

    assert payload["think"] is True
    assert "format" not in payload
