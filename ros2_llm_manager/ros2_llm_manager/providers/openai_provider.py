"""
OpenAIProvider — inference backend for the OpenAI API (Chat Completions).

Wraps the official openai SDK. Requires an OpenAI API key (OPENAI_API_KEY or
the `api_key` parameter). Chat Completions is used rather than the Responses
API so the same provider also drives OpenAI-compatible servers (vLLM, LM
Studio, OpenRouter...) through `base_url`.

Current OpenAI models reason before answering; `reasoning_effort` ("none" by
default) keeps spoken replies fast. Reasoning tokens count toward the output
cap, so the dialog manager's short caps are raised to a floor when reasoning
is on.

OpenAI caches repeated prompt prefixes automatically, so the provider needs no
cache markers: the dialog prompts already put their fixed instructions first.
"""

import copy
import os
from typing import Callable, Optional

from ..base_provider import BaseProvider, GenerateResult

try:
    import openai

    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

# Reasoning tokens count toward max_completion_tokens: below this floor a short
# cap can be used up by reasoning and leave no reply text.
_MIN_REASONING_MAX_TOKENS = 4096


def strict_schema(schema: dict) -> tuple[dict, bool]:
    """Copy of a JSON schema for Structured Outputs, and whether strict mode
    can be used.

    Strict mode needs `additionalProperties: false` on every object and every
    property listed in `required`. The dialog manager's schemas have optional
    properties, so those are sent non-strict: the schema then guides the reply
    and the client still parses it loosely.
    """
    strict = True

    def fix(node):
        nonlocal strict
        if isinstance(node, list):
            return [fix(n) for n in node]
        if not isinstance(node, dict):
            return node
        out = {k: fix(v) for k, v in node.items()}
        if out.get("type") == "object" or "properties" in out:
            out["additionalProperties"] = False
            if set(out.get("properties", {})) - set(out.get("required", [])):
                strict = False
        return out

    fixed = fix(copy.deepcopy(schema))
    return fixed, strict


class OpenAIProvider(BaseProvider):

    def __init__(
        self,
        api_key: str,
        timeout: float,
        default_model: str,
        reasoning_effort: str = "none",
        base_url: str = "",
    ):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._timeout = timeout
        self._reasoning_effort = reasoning_effort
        self._base_url = base_url
        self.default_model = default_model
        self._client = None

    # ==== CONNECTION ====

    def connect(self) -> tuple[bool, str]:
        if not _OPENAI_AVAILABLE:
            return False, "openai package not installed."
        if not self._api_key and not self._base_url:
            return False, "No OpenAI API key found (set OPENAI_API_KEY or openai.api_key)."
        try:
            # Local OpenAI-compatible servers usually ignore the key but the SDK
            # requires one.
            self._client = openai.OpenAI(
                api_key=self._api_key or "unused",
                base_url=self._base_url or None,
                timeout=self._timeout,
            )
            # Free call that checks both the credentials and the model id.
            self._client.models.retrieve(self.default_model)
            target = f" at {self._base_url}" if self._base_url else ""
            return True, f"OpenAI client initialised ({self.default_model}{target})."
        except openai.AuthenticationError:
            self._client = None
            return False, "Invalid OpenAI API key."
        except openai.NotFoundError:
            self._client = None
            return False, f"OpenAI model '{self.default_model}' not found."
        except Exception as exc:
            self._client = None
            return False, f"OpenAI init error: {exc}"

    def ensure_model_ready(self, model: str) -> tuple[bool, str]:
        # Cloud models have no warm-up concept.
        return True, f"OpenAI '{model}' ready (cloud)."

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = None

    # ==== INFERENCE ====

    def generate(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 0,
        format_schema: Optional[dict] = None,
        stream_callback: Optional[Callable[[str], bool]] = None,
        cache_prefix_len: int = 0,
    ) -> GenerateResult:
        if not self._client:
            return GenerateResult(success=False, error="Client not initialised.")

        params = self._build_params(model, messages, max_tokens, format_schema)
        try:
            return self._run(params, stream_callback)
        except openai.APITimeoutError as exc:
            return GenerateResult(success=False, error=str(exc), error_type="timeout")
        except openai.APIConnectionError as exc:
            return GenerateResult(success=False, error=str(exc), error_type="connection")
        except openai.APIStatusError as exc:
            return GenerateResult(
                success=False, error=exc.message, status_code=exc.status_code, error_type="http"
            )
        except Exception as exc:
            return GenerateResult(success=False, error=str(exc), error_type="unknown")

    def _build_params(self, model, messages, max_tokens, format_schema) -> dict:
        reasoning = self._reasoning_effort not in ("", "none")
        params: dict = {
            "model": model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self._reasoning_effort:
            params["reasoning_effort"] = self._reasoning_effort
        if max_tokens > 0:
            params["max_completion_tokens"] = (
                max(max_tokens, _MIN_REASONING_MAX_TOKENS) if reasoning else max_tokens
            )
        if format_schema:
            schema, strict = strict_schema(format_schema)
            params["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": schema, "strict": strict},
            }
        return params

    def _run(self, params: dict, stream_callback) -> GenerateResult:
        text = ""
        refusal = ""
        finish_reason = None
        usage = None
        with self._client.chat.completions.create(**params) as stream:
            for chunk in stream:
                if chunk.usage is not None:
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                finish_reason = choice.finish_reason or finish_reason
                if choice.delta.refusal:
                    refusal += choice.delta.refusal
                token = choice.delta.content
                if not token:
                    continue
                text += token
                if stream_callback is not None and not stream_callback(token):
                    return GenerateResult(success=False, text=text, error="cancelled")

        tokens = self._usage(usage)
        if refusal:
            return GenerateResult(
                success=False,
                error=f"OpenAI declined the request: {refusal}",
                error_type="api",
                **tokens,
            )
        text = text.strip()
        if not text:
            return GenerateResult(
                success=False,
                error=f"Empty reply (finish_reason={finish_reason}).",
                error_type="api",
                **tokens,
            )
        return GenerateResult(success=True, text=text, **tokens)

    @staticmethod
    def _usage(usage) -> dict:
        if usage is None:
            return {}
        details = usage.prompt_tokens_details
        return {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "cached_tokens": (details.cached_tokens or 0) if details else 0,
        }
