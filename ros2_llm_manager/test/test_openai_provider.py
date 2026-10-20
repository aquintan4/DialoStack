"""Unit tests for OpenAIProvider: schema adaptation, request parameters and
stream handling, against a fake client (no network)."""

from types import SimpleNamespace

import httpx2
import openai

from ros2_llm_manager.providers.openai_provider import OpenAIProvider, strict_schema

# ==== HELPERS ====


def chunk(content=None, refusal=None, finish_reason=None):
    delta = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)], usage=None
    )


def usage_chunk(prompt=100, completion=5, cached=80):
    usage = SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
    )
    return SimpleNamespace(choices=[], usage=usage)


class FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._chunks)


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **params):
        self.calls.append(params)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return FakeStream(reply)


def provider_with(*replies, effort="none"):
    p = OpenAIProvider(
        api_key="test", timeout=5.0, default_model="gpt-6-luna", reasoning_effort=effort
    )
    fake = FakeCompletions(replies)
    p._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return p, fake


def reply(text="Hello"):
    return [chunk(text), chunk(finish_reason="stop"), usage_chunk()]


USER = [{"role": "user", "content": "x"}]

# ==== SCHEMA ====


def test_strict_when_every_property_is_required():
    schema, strict = strict_schema(
        {"type": "object", "properties": {"cancel": {"type": "boolean"}}, "required": ["cancel"]}
    )
    assert strict and schema["additionalProperties"] is False


def test_optional_properties_fall_back_to_non_strict():
    schema, strict = strict_schema(
        {
            "type": "object",
            "properties": {"name": {"type": "string"}, "hint": {"type": "string"}},
            "required": ["name"],
        }
    )
    assert not strict and schema["additionalProperties"] is False


# ==== REQUEST PARAMETERS ====


def test_params_without_reasoning_keep_max_tokens():
    p, fake = provider_with(reply())
    p.generate("gpt-6-luna", USER, max_tokens=120)
    params = fake.calls[0]
    assert params["max_completion_tokens"] == 120
    assert params["reasoning_effort"] == "none"
    assert params["stream_options"] == {"include_usage": True}


def test_params_with_reasoning_raise_small_max_tokens():
    p, fake = provider_with(reply(), effort="low")
    p.generate("gpt-6-luna", USER, max_tokens=120)
    assert fake.calls[0]["max_completion_tokens"] >= 4096


def test_empty_effort_is_omitted():
    p, fake = provider_with(reply(), effort="")
    p.generate("gpt-6-luna", USER)
    assert "reasoning_effort" not in fake.calls[0]
    assert "max_completion_tokens" not in fake.calls[0]


def test_params_send_json_schema():
    p, fake = provider_with(reply('{"cancel": true}'))
    p.generate(
        "gpt-6-luna",
        USER,
        format_schema={
            "type": "object",
            "properties": {"cancel": {"type": "boolean"}},
            "required": ["cancel"],
        },
    )
    fmt = fake.calls[0]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True


# ==== RESULTS ====


def test_generate_returns_text_and_usage():
    p, _ = provider_with(reply("Hello there"))
    r = p.generate("gpt-6-luna", USER)
    assert r.success and r.text == "Hello there"
    assert (r.prompt_tokens, r.completion_tokens, r.cached_tokens) == (100, 5, 80)


def test_streaming_forwards_tokens_and_cancels():
    p, _ = provider_with([chunk("a"), chunk("b"), chunk("c")])
    r = p.generate("gpt-6-luna", USER, stream_callback=lambda t: t != "b")
    assert not r.success and r.error == "cancelled" and r.text == "ab"


def test_refusal_is_an_error():
    p, _ = provider_with([chunk(refusal="I can't help with that."), usage_chunk()])
    r = p.generate("gpt-6-luna", USER)
    assert not r.success and "declined" in r.error


def test_empty_reply_is_an_error():
    p, _ = provider_with([chunk(finish_reason="length"), usage_chunk()])
    r = p.generate("gpt-6-luna", USER)
    assert not r.success and "length" in r.error


def test_http_error_is_classified():
    request = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
    error = openai.BadRequestError(
        "bad", response=httpx2.Response(400, request=request), body=None
    )
    p, _ = provider_with(error)
    r = p.generate("gpt-6-luna", USER)
    assert (r.success, r.error_type, r.status_code) == (False, "http", 400)


def test_connect_without_key_fails_clearly(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = OpenAIProvider(api_key="", timeout=5.0, default_model="gpt-6-luna")
    ok, msg = p.connect()
    assert not ok and "OPENAI_API_KEY" in msg
