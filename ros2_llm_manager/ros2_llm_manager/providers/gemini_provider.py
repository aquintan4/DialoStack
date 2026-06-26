"""
GeminiProvider — inference backend for Google Gemini cloud models.

Wraps the google-genai SDK. Thinking is disabled unconditionally
(thinking_budget=0) to keep latency predictable for dialog applications.
"""

import os
from typing import Callable, Optional

from ..base_provider import BaseProvider, GenerateResult

try:
    from google import genai
    from google.genai import types

    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False


class GeminiProvider(BaseProvider):

    def __init__(self, api_key: str, timeout: float, default_model: str):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._timeout = timeout
        self.default_model = default_model
        self._client = None

    # ==== CONNECTION ====

    def connect(self) -> tuple[bool, str]:
        if not _GEMINI_AVAILABLE:
            return False, "google-genai package not installed."
        if not self._api_key:
            return False, "GEMINI_API_KEY not set."
        try:
            self._client = genai.Client(api_key=self._api_key)
            return True, "Gemini client initialised."
        except Exception as exc:
            return False, f"Gemini init error: {exc}"

    def ensure_model_ready(self, model: str) -> tuple[bool, str]:
        # Cloud models have no warm-up concept.
        return True, f"Gemini '{model}' ready (cloud)."

    def close(self) -> None:
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

        system_instr = None
        contents: list = []

        for msg in messages:
            if msg["role"] == "system":
                system_instr = msg["content"]
                continue
            role = "user" if msg["role"] == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg["content"])],
                )
            )

        config_kwargs: dict = {}
        if system_instr:
            config_kwargs["system_instruction"] = system_instr
        if max_tokens > 0:
            config_kwargs["max_output_tokens"] = max_tokens
        if format_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = format_schema

        # Disable thinking to keep latency predictable. ThinkingConfig was
        # added in a later SDK release; guard only against AttributeError so
        # real errors (e.g. wrong argument types) still surface.
        try:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except AttributeError:
            pass

        config = types.GenerateContentConfig(**config_kwargs)

        try:
            if stream_callback is not None:
                return self._stream(model, contents, config, stream_callback)
            return self._blocking(model, contents, config)
        except Exception as exc:
            # google-genai APIError subclasses carry an HTTP `.code` (e.g. 404
            # model not found, 429 quota, 503 unavailable); fall back to 0.
            code = getattr(exc, "code", 0)
            try:
                code = int(code)
            except (TypeError, ValueError):
                code = 0
            return GenerateResult(
                success=False, error=str(exc), status_code=code, error_type="api"
            )

    def _blocking(self, model, contents, config) -> GenerateResult:
        response = self._client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        usage = response.usage_metadata
        return GenerateResult(
            success=True,
            text=str(response.text).strip(),
            prompt_tokens=getattr(usage, "prompt_token_count", 0),
            completion_tokens=getattr(usage, "candidates_token_count", 0),
        )

    def _stream(
        self, model, contents, config, stream_callback: Callable[[str], bool]
    ) -> GenerateResult:
        full_text = ""
        prompt_tokens = 0
        completion_tokens = 0

        for chunk in self._client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        ):
            token = self._text_from_chunk(chunk)
            if token:
                full_text += token
                if not stream_callback(token):
                    return GenerateResult(success=False, text=full_text, error="cancelled")

            usage = getattr(chunk, "usage_metadata", None)
            if usage:
                prompt_tokens = getattr(usage, "prompt_token_count", 0) or prompt_tokens
                completion_tokens = getattr(usage, "candidates_token_count", 0) or completion_tokens

        return GenerateResult(
            success=True,
            text=full_text.strip(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    @staticmethod
    def _text_from_chunk(chunk) -> str:
        """Extract text from a stream chunk, skipping internal thought parts."""
        try:
            parts = chunk.candidates[0].content.parts
            return "".join(part.text or "" for part in parts if not getattr(part, "thought", False))
        except (AttributeError, IndexError, TypeError):
            return chunk.text or ""
