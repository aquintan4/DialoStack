"""
LLM adapter: factory functions that return an infer_fn compatible
with LLMDialogClient's signature:
    (session_id: str, prompt: str, max_tokens: int|None, schema: dict|None) -> str|None

This replaces the ROS action client used in production.
"""

import os
from typing import Callable, Optional

InferFn = Callable[[str, str, Optional[int], Optional[dict]], Optional[str]]


def make_gemini_infer_fn(
    model: str = "gemini-2.5-flash",
    api_key: Optional[str] = None,
) -> InferFn:
    from google import genai
    from google.genai import types as gt

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY not set. Export it or add api_key to config.yaml.")
    client = genai.Client(api_key=key)

    def infer(
        session_id: str,
        prompt: str,
        max_tokens: Optional[int],
        schema: Optional[dict],
    ) -> Optional[str]:
        kwargs: dict = {}
        if max_tokens and max_tokens > 0:
            kwargs["max_output_tokens"] = max_tokens
        if schema:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_schema"] = schema
        try:
            kwargs["thinking_config"] = gt.ThinkingConfig(thinking_budget=0)
        except AttributeError:
            pass
        config = gt.GenerateContentConfig(**kwargs)
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[gt.Content(role="user", parts=[gt.Part.from_text(text=prompt)])],
                config=config,
            )
            return str(resp.text).strip() or None
        except Exception as exc:
            print(f"  [Gemini error] {exc}")
            return None

    return infer


def make_ollama_infer_fn(
    model: str = "qwen2.5",
    host: str = "127.0.0.1",
    port: int = 11434,
) -> InferFn:
    import json
    import requests

    url = f"http://{host}:{port}/api/generate"

    def infer(
        session_id: str,
        prompt: str,
        max_tokens: Optional[int],
        schema: Optional[dict],
    ) -> Optional[str]:
        payload: dict = {"model": model, "prompt": prompt, "stream": False}
        if max_tokens and max_tokens > 0:
            payload["options"] = {"num_predict": max_tokens}
        if schema:
            payload["format"] = schema
        try:
            r = requests.post(url, json=payload, timeout=120)
            r.raise_for_status()
            return r.json().get("response", "").strip() or None
        except Exception as exc:
            print(f"  [Ollama error] {exc}")
            return None

    return infer


def make_claude_infer_fn(
    model: str = "claude-opus-5-5",
    api_key: Optional[str] = None,
    effort: str = "low",
) -> InferFn:
    """Uses the production ClaudeProvider, so benchmarks see the same request
    shape (structured-output schema, effort, max_tokens floor) as the robot."""
    import sys

    llm_pkg = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "ros2_llm_manager")
    )
    if llm_pkg not in sys.path:
        sys.path.insert(0, llm_pkg)
    from ros2_llm_manager.providers.claude_provider import ClaudeProvider

    provider = ClaudeProvider(
        api_key=api_key or "", timeout=120.0, default_model=model, effort=effort
    )
    ok, msg = provider.connect()
    if not ok:
        raise ValueError(msg)

    def infer(
        session_id: str,
        prompt: str,
        max_tokens: Optional[int],
        schema: Optional[dict],
    ) -> Optional[str]:
        result = provider.generate(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens or 0,
            format_schema=schema,
        )
        if not result.success:
            print(f"  [Claude error] {result.error}")
            return None
        return result.text or None

    return infer


def make_infer_fn(cfg: dict) -> InferFn:
    provider = cfg.get("llm", {}).get("provider", "gemini")
    llm_cfg = cfg.get("llm", {})
    if provider == "gemini":
        return make_gemini_infer_fn(
            model=llm_cfg.get("model", "gemini-2.5-flash"),
            api_key=llm_cfg.get("api_key") or None,
        )
    if provider == "ollama":
        return make_ollama_infer_fn(
            model=llm_cfg.get("model", "qwen2.5"),
            host=llm_cfg.get("ollama_host", "127.0.0.1"),
            port=int(llm_cfg.get("ollama_port", 11434)),
        )
    if provider == "claude":
        return make_claude_infer_fn(
            model=llm_cfg.get("model", "claude-opus-5-5"),
            api_key=llm_cfg.get("api_key") or None,
            effort=llm_cfg.get("effort", "low"),
        )
    raise ValueError(f"Unknown provider '{provider}'. Use 'gemini', 'ollama' or 'claude'.")
