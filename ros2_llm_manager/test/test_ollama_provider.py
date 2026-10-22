"""Unit tests for OllamaProvider request payloads, against a fake HTTP client."""

from types import SimpleNamespace

import pytest

from ros2_llm_manager.providers.ollama_provider import OllamaProvider


class FakeHttp:
    def __init__(self):
        self.payloads = []

    def post(self, path, json):
        self.payloads.append(json)
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"message": {"content": "ok"}, "prompt_eval_count": 3, "eval_count": 1},
        )


@pytest.mark.parametrize("think", [False, True])
def test_think_flag_is_sent(think):
    p = OllamaProvider("127.0.0.1", 11434, 5.0, "qwen3.5:9b", think=think)
    p._http = FakeHttp()
    r = p.generate("qwen3.5:9b", [{"role": "user", "content": "x"}], max_tokens=50)
    assert r.success and r.text == "ok"
    payload = p._http.payloads[0]
    assert payload["think"] is think
    assert payload["options"] == {"num_predict": 50}


def test_thinking_is_off_by_default():
    p = OllamaProvider("127.0.0.1", 11434, 5.0, "qwen3.5:9b")
    p._http = FakeHttp()
    p.generate("qwen3.5:9b", [{"role": "user", "content": "x"}])
    assert p._http.payloads[0]["think"] is False


def test_schema_calls_run_at_temperature_zero():
    p = OllamaProvider("127.0.0.1", 11434, 5.0, "llama3.2:3b")
    p._http = FakeHttp()
    schema = {"type": "object", "properties": {"intent": {"type": "string"}}}
    p.generate("llama3.2:3b", [{"role": "user", "content": "x"}], max_tokens=50, format_schema=schema)
    payload = p._http.payloads[0]
    assert payload["format"] == schema
    assert payload["options"] == {"num_predict": 50, "temperature": 0}


def test_spoken_replies_keep_the_model_temperature():
    p = OllamaProvider("127.0.0.1", 11434, 5.0, "llama3.2:3b")
    p._http = FakeHttp()
    p.generate("llama3.2:3b", [{"role": "user", "content": "x"}])
    assert "options" not in p._http.payloads[0]
