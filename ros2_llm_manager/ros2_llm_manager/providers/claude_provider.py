"""
ClaudeProvider — inference backend for Anthropic Claude models (Claude API).

Wraps the official anthropic SDK. Requires a Claude API key (ANTHROPIC_API_KEY
or the `api_key` parameter); a Claude.ai subscription does not grant API access.

Current Claude models always think, so latency is kept low through the effort
level ("low" by default) rather than by disabling thinking. Thinking counts
toward max_tokens, so the short caps the dialog manager asks for (80-300
tokens) are raised to a floor; reply length is governed by the prompts.

Refusals are retried server-side on Anthropic's recommended fallback model
(fallbacks="default") on the models that support it.
"""

import copy
import os
from typing import Callable, Optional

from ..base_provider import BaseProvider, GenerateResult

try:
    import anthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

# Thinking tokens count toward max_tokens: below this floor a short cap can be
# used up by thinking and leave no reply text.
_MIN_MAX_TOKENS = 4096

# Server-side refusal fallback ("default" picks the model per refusal category).
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_FALLBACK_MODELS = frozenset(
    {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
)


def strict_schema(schema: dict) -> dict:
    """Copy of a JSON schema accepted by Claude structured outputs.

    Claude requires `additionalProperties: false` on every object; the dialog
    manager's schemas leave it unset. Nested schemas (properties, items, anyOf...)
    are rewritten recursively.
    """

    def fix(node):
        if isinstance(node, list):
            return [fix(n) for n in node]
        if not isinstance(node, dict):
            return node
        out = {k: fix(v) for k, v in node.items()}
        if out.get("type") == "object" or "properties" in out:
            out["additionalProperties"] = False
        return out

    return fix(copy.deepcopy(schema))


def split_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Session messages -> (system prompt, user/assistant turns) for the Messages API."""
    system_parts = []
    turns = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
            continue
        role = "assistant" if msg["role"] == "assistant" else "user"
        turns.append({"role": role, "content": msg["content"]})
    return "\n\n".join(system_parts), turns


class ClaudeProvider(BaseProvider):

    def __init__(self, api_key: str, timeout: float, default_model: str, effort: str = "low"):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._timeout = timeout
        self._effort = effort
        self.default_model = default_model
        self._client = None

    # ==== CONNECTION ====

    def connect(self) -> tuple[bool, str]:
        if not _ANTHROPIC_AVAILABLE:
            return False, "anthropic package not installed."
        try:
            # Without an explicit key the SDK resolves ANTHROPIC_API_KEY (or an
            # `ant auth login` profile) on its own.
            kwargs = {"timeout": self._timeout}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = anthropic.Anthropic(**kwargs)
            # Free call that checks both the credentials and the model id.
            self._client.models.retrieve(self.default_model)
            return True, f"Claude client initialised ({self.default_model})."
        except anthropic.AuthenticationError:
            self._client = None
            return False, "Invalid Claude API key."
        except TypeError:
            # Raised by the SDK when no credential source resolves at all.
            self._client = None
            return False, "No Claude API key found (set ANTHROPIC_API_KEY or claude.api_key)."
        except anthropic.NotFoundError:
            self._client = None
            return False, f"Claude model '{self.default_model}' not found."
        except Exception as exc:
            self._client = None
            return False, f"Claude init error: {exc}"

    def ensure_model_ready(self, model: str) -> tuple[bool, str]:
        # Cloud models have no warm-up concept.
        return True, f"Claude '{model}' ready (cloud)."

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
    ) -> GenerateResult:
        if not self._client:
            return GenerateResult(success=False, error="Client not initialised.")

        system, turns = split_messages(messages)
        params = self._build_params(model, system, turns, max_tokens, format_schema)

        try:
            try:
                return self._run(params, stream_callback)
            except anthropic.BadRequestError:
                # A schema the API cannot compile: retry once without it. The
                # prompts already ask for JSON and the client parses it loosely.
                config = params["output_config"]
                if "format" not in config:
                    raise
                without_format = {k: v for k, v in config.items() if k != "format"}
                return self._run({**params, "output_config": without_format}, stream_callback)
        except anthropic.APITimeoutError as exc:
            return GenerateResult(success=False, error=str(exc), error_type="timeout")
        except anthropic.APIConnectionError as exc:
            return GenerateResult(success=False, error=str(exc), error_type="connection")
        except anthropic.APIStatusError as exc:
            return GenerateResult(
                success=False, error=exc.message, status_code=exc.status_code, error_type="http"
            )
        except Exception as exc:
            return GenerateResult(success=False, error=str(exc), error_type="unknown")

    def _build_params(self, model, system, turns, max_tokens, format_schema) -> dict:
        params: dict = {
            "model": model,
            "max_tokens": max(max_tokens, _MIN_MAX_TOKENS),
            "messages": turns,
            "output_config": {},
        }
        if system:
            params["system"] = system
        if self._effort:
            params["output_config"]["effort"] = self._effort
        if format_schema:
            params["output_config"]["format"] = {
                "type": "json_schema",
                "schema": strict_schema(format_schema),
            }
        if model in _FALLBACK_MODELS:
            params["betas"] = [_FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    def _run(self, params: dict, stream_callback) -> GenerateResult:
        if stream_callback is None:
            return self._to_result(self._client.beta.messages.create(**params))

        streamed = ""
        with self._client.beta.messages.stream(**params) as stream:
            for token in stream.text_stream:
                streamed += token
                if not stream_callback(token):
                    return GenerateResult(success=False, text=streamed, error="cancelled")
            message = stream.get_final_message()
        return self._to_result(message)

    @staticmethod
    def _to_result(message) -> GenerateResult:
        usage = message.usage
        if message.stop_reason == "refusal":
            return GenerateResult(
                success=False,
                error="Claude declined the request.",
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                error_type="api",
            )
        text = "".join(b.text for b in message.content if b.type == "text").strip()
        if not text:
            return GenerateResult(
                success=False,
                error=f"Empty reply (stop_reason={message.stop_reason}).",
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                error_type="api",
            )
        return GenerateResult(
            success=True,
            text=text,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
        )
