"""
OllamaProvider — inference backend for locally-served Ollama models.

Maintains a persistent HTTP connection pool (httpx.Client) and uses
keep_alive=-1 on every request to keep the model resident in VRAM, avoiding
repeated cold-start penalties during a dialog session.
"""

import json
import time
from typing import Callable, Optional

import httpx

from ..base_provider import BaseProvider, GenerateResult


class OllamaProvider(BaseProvider):

    def __init__(self, host: str, port: int, timeout: float, default_model: str):
        self._base_url = f"http://{host}:{port}"
        self._timeout = timeout
        self.default_model = default_model
        self._http: Optional[httpx.Client] = None

    # ==== CONNECTION ====

    def connect(self) -> tuple[bool, str]:
        try:
            self._http = httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                    keepalive_expiry=30.0,
                ),
            )
            r = self._http.get("/api/tags", timeout=3.0)
            if r.status_code == 200:
                return True, f"Reachable at {self._base_url}"
            return False, f"Returned HTTP {r.status_code}"
        except httpx.ConnectError:
            return False, f"Cannot connect to {self._base_url}"
        except Exception as exc:
            return False, f"Unexpected error: {exc}"

    def ensure_model_ready(self, model: str) -> tuple[bool, str]:
        """
        Send an empty prompt to force the model into VRAM.
        Retries up to 3 times with exponential backoff.
        """
        last_error = "unknown error"
        for attempt in range(3):
            try:
                r = self._http.post(
                    "/api/generate",
                    json={"model": model, "prompt": "", "keep_alive": -1},
                    timeout=180.0,
                )
                if r.status_code == 200:
                    return True, f"Model '{model}' loaded into memory."
                return False, f"Load failed: HTTP {r.status_code}"
            except Exception as exc:
                last_error = str(exc)
                if attempt < 2:
                    time.sleep(2**attempt)

        return False, f"Failed after 3 attempts: {last_error}"

    def close(self) -> None:
        if self._http:
            self._http.close()
            self._http = None

    # ==== INFERENCE ====

    def generate(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 0,
        format_schema: Optional[dict] = None,
        stream_callback: Optional[Callable[[str], bool]] = None,
    ) -> GenerateResult:
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": stream_callback is not None,
            "keep_alive": -1,
        }
        if max_tokens > 0:
            payload["options"] = {"num_predict": max_tokens}
        if format_schema:
            payload["format"] = format_schema

        try:
            if stream_callback is not None:
                return self._stream(payload, stream_callback)
            return self._blocking(payload)
        except httpx.TimeoutException:
            return GenerateResult(
                success=False, error=f"Timeout after {self._timeout}s", error_type="timeout"
            )
        except httpx.ConnectError:
            return GenerateResult(
                success=False, error="Lost connection to Ollama", error_type="connection"
            )
        except Exception as exc:
            return GenerateResult(
                success=False, error=f"Unexpected error: {exc}", error_type="unknown"
            )

    def _blocking(self, payload: dict) -> GenerateResult:
        r = self._http.post("/api/chat", json=payload)
        if r.status_code != 200:
            return GenerateResult(
                success=False, error=f"HTTP {r.status_code}",
                status_code=r.status_code, error_type="http",
            )

        data = r.json()
        return GenerateResult(
            success=True,
            text=data["message"]["content"],
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    def _stream(self, payload: dict, stream_callback: Callable[[str], bool]) -> GenerateResult:
        full_text = ""
        prompt_tokens = 0
        completion_tokens = 0

        # httpx closes the response body when the context manager exits, even
        # if we return early due to cancellation — no resource leak.
        with self._http.stream("POST", "/api/chat", json=payload) as r:
            if r.status_code != 200:
                return GenerateResult(
                    success=False, error=f"HTTP {r.status_code}",
                    status_code=r.status_code, error_type="http",
                )

            for raw_line in r.iter_lines():
                if not raw_line:
                    continue

                try:
                    chunk = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                token = chunk.get("message", {}).get("content", "")
                if token:
                    full_text += token
                    if not stream_callback(token):
                        return GenerateResult(success=False, text=full_text, error="cancelled")

                if chunk.get("done"):
                    prompt_tokens = chunk.get("prompt_eval_count", 0)
                    completion_tokens = chunk.get("eval_count", 0)

        return GenerateResult(
            success=True,
            text=full_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
