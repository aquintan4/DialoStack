"""Unit tests for ClaudeProvider: schema adaptation, message mapping, request
parameters and result handling, against a fake client (no network)."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from ros2_llm_manager.providers.claude_provider import (
    ClaudeProvider,
    mark_cache_prefix,
    split_messages,
    strict_schema,
)

# ==== HELPERS ====


def message(text="hi", stop_reason="end_turn", cache_read=None):
    content = [SimpleNamespace(type="thinking", thinking="")]
    if text:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=None,
        ),
    )


class FakeStream:
    def __init__(self, tokens, final):
        self.text_stream = iter(tokens)
        self._final = final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._final


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def _next(self, params):
        self.calls.append(params)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    def create(self, **params):
        return self._next(params)

    def stream(self, **params):
        return self._next(params)


def provider_with(*replies, model="claude-opus-5-5"):
    p = ClaudeProvider(api_key="test", timeout=5.0, default_model=model)
    fake = FakeMessages(replies)
    p._client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    return p, fake


def bad_request():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(400, request=request)
    return anthropic.BadRequestError("invalid schema", response=response, body=None)


EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "extractions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slot": {"type": "string", "enum": ["name"]},
                    "value": {
                        "anyOf": [
                            {"type": "string"},
                            {"type": "object", "properties": {"_add": {"type": "boolean"}}},
                        ]
                    },
                },
            },
        }
    },
    "required": ["extractions"],
}

# ==== SCHEMA AND MESSAGES ====


def test_strict_schema_closes_every_object():
    s = strict_schema(EXTRACTION_SCHEMA)
    item = s["properties"]["extractions"]["items"]
    assert s["additionalProperties"] is False
    assert item["additionalProperties"] is False
    assert item["properties"]["value"]["anyOf"][1]["additionalProperties"] is False
    assert "additionalProperties" not in item["properties"]["value"]["anyOf"][0]


def test_strict_schema_does_not_mutate_input():
    strict_schema(EXTRACTION_SCHEMA)
    assert "additionalProperties" not in EXTRACTION_SCHEMA


def test_split_messages_moves_system_out():
    system, turns = split_messages(
        [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
    )
    assert system == "be brief"
    assert turns == [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]


def test_cache_prefix_splits_last_user_turn():
    turns = [{"role": "user", "content": "RULES\n\nUSER: hi"}]
    mark_cache_prefix(turns, len("RULES\n\n"))
    first, rest = turns[0]["content"]
    assert first == {"type": "text", "text": "RULES\n\n", "cache_control": {"type": "ephemeral"}}
    assert rest == {"type": "text", "text": "USER: hi"}


@pytest.mark.parametrize("prefix_len", [0, 99])
def test_cache_prefix_out_of_range_is_ignored(prefix_len):
    turns = [{"role": "user", "content": "short"}]
    mark_cache_prefix(turns, prefix_len)
    assert turns[0]["content"] == "short"


# ==== REQUEST PARAMETERS ====


def test_params_raise_small_max_tokens_and_set_effort():
    p, fake = provider_with(message())
    p.generate("claude-opus-5-5", [{"role": "user", "content": "x"}], max_tokens=120)
    params = fake.calls[0]
    assert params["max_tokens"] >= 4096
    assert params["output_config"]["effort"] == "low"


def test_params_enable_fallback_on_supported_models_only():
    p, fake = provider_with(message(), message())
    p.generate("claude-opus-5-5", [{"role": "user", "content": "x"}])
    p.generate("claude-haiku-5-5", [{"role": "user", "content": "x"}])
    assert fake.calls[0]["fallbacks"] == "default"
    assert "fallbacks" not in fake.calls[1]


def test_params_send_strict_json_schema():
    p, fake = provider_with(message('{"extractions": []}'))
    p.generate(
        "claude-opus-5-5", [{"role": "user", "content": "x"}], format_schema=EXTRACTION_SCHEMA
    )
    fmt = fake.calls[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["additionalProperties"] is False


# ==== RESULTS ====


def test_generate_returns_text_and_usage():
    p, _ = provider_with(message("Hello there"))
    r = p.generate("claude-opus-5-5", [{"role": "user", "content": "x"}])
    assert r.success and r.text == "Hello there"
    assert (r.prompt_tokens, r.completion_tokens) == (10, 5)


def test_cached_tokens_are_reported():
    p, fake = provider_with(message("ok", cache_read=900))
    r = p.generate(
        "claude-haiku-5-5", [{"role": "user", "content": "RULES\n\nhi"}], cache_prefix_len=7
    )
    assert (r.prompt_tokens, r.cached_tokens) == (910, 900)
    assert fake.calls[0]["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}


def test_refusal_is_an_error():
    p, _ = provider_with(message("", stop_reason="refusal"))
    r = p.generate("claude-opus-5-5", [{"role": "user", "content": "x"}])
    assert not r.success and "declined" in r.error


def test_empty_reply_is_an_error():
    p, _ = provider_with(message("", stop_reason="max_tokens"))
    r = p.generate("claude-opus-5-5", [{"role": "user", "content": "x"}])
    assert not r.success and "max_tokens" in r.error


def test_schema_rejected_retries_without_format():
    p, fake = provider_with(bad_request(), message('{"ok": true}'))
    r = p.generate(
        "claude-opus-5-5", [{"role": "user", "content": "x"}], format_schema={"type": "object"}
    )
    assert r.success
    assert "format" in fake.calls[0]["output_config"]
    assert "format" not in fake.calls[1]["output_config"]


def test_bad_request_without_schema_is_not_retried():
    p, fake = provider_with(bad_request())
    r = p.generate("claude-opus-5-5", [{"role": "user", "content": "x"}])
    assert not r.success and len(fake.calls) == 1


def test_streaming_forwards_tokens():
    p, _ = provider_with(FakeStream(["Hel", "lo"], message("Hello")))
    seen = []
    r = p.generate(
        "claude-opus-5-5",
        [{"role": "user", "content": "x"}],
        stream_callback=lambda t: seen.append(t) or True,
    )
    assert seen == ["Hel", "lo"] and r.text == "Hello"


def test_streaming_cancel():
    p, _ = provider_with(FakeStream(["a", "b", "c"], message("abc")))
    r = p.generate(
        "claude-opus-5-5", [{"role": "user", "content": "x"}], stream_callback=lambda t: False
    )
    assert not r.success and r.error == "cancelled" and r.text == "a"


def test_generate_without_client_fails_cleanly():
    p = ClaudeProvider(api_key="", timeout=5.0, default_model="claude-opus-5-5")
    assert not p.generate("claude-opus-5-5", [{"role": "user", "content": "x"}]).success


@pytest.mark.parametrize("effort", ["", None])
def test_empty_effort_is_omitted(effort):
    p = ClaudeProvider(api_key="k", timeout=5.0, default_model="m", effort=effort)
    params = p._build_params("claude-haiku-4-5", "", [], 0, None)
    assert "effort" not in params["output_config"]
