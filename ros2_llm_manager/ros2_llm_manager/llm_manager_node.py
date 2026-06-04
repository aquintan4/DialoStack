"""
LLMManagerNode — ROS2 node for multi-provider LLM inference.

Exposes:
  Action server  /llm/inference          (LlmInference)   — main inference endpoint.
  Service        /llm/session/create     (CreateSession)  — session lifecycle.
  Service        /llm/session/delete     (DeleteSession)
  Service        /llm/session/list       (ListSessions)

Provider selection and model defaults are driven by ROS parameters (see
the launch/YAML config). At least one provider must connect successfully
at startup, otherwise the node will log an error and reject all goals.
"""

import json
import time

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from ros2_llm_interfaces.action import LlmInference
from ros2_llm_interfaces.srv import CreateSession, DeleteSession, ListSessions

from .session_manager import SessionManager
from .providers.ollama_provider import OllamaProvider
from .providers.gemini_provider import GeminiProvider


class LLMManagerNode(Node):

    def __init__(self):
        super().__init__("llm_manager_node")

        self._declare_parameters()
        self._read_parameters()

        self._providers: dict = {}
        self._init_providers()

        if not self._providers:
            self.get_logger().error(
                "No providers enabled or available — node cannot serve requests."
            )
        elif self._default_provider and self._default_provider not in self._providers:
            # Warn early: sessions without an explicit provider will fail.
            self.get_logger().warning(
                f"default_provider '{self._default_provider}' is configured but "
                f"failed to connect. Active providers: {list(self._providers.keys())}"
            )

        self._sessions = SessionManager()

        cb = ReentrantCallbackGroup()

        ActionServer(
            self,
            LlmInference,
            "/llm/inference",
            execute_callback=self._on_inference,
            goal_callback=lambda _: GoalResponse.ACCEPT,
            cancel_callback=lambda _: CancelResponse.ACCEPT,
            callback_group=cb,
        )
        self.create_service(
            CreateSession, "/llm/session/create", self._on_create_session, callback_group=cb
        )
        self.create_service(
            DeleteSession, "/llm/session/delete", self._on_delete_session, callback_group=cb
        )
        self.create_service(
            ListSessions, "/llm/session/list", self._on_list_sessions, callback_group=cb
        )

        self._log(f"LLM Manager ready. Active providers: {list(self._providers.keys())}")

    # ==== PARAMETER HANDLING ====

    def _declare_parameters(self) -> None:
        self.declare_parameter("default_provider", "")
        self.declare_parameter("default_model", "")
        self.declare_parameter("max_concurrent", 4)
        self.declare_parameter("silent_mode", False)

        self.declare_parameter("ollama.enable", False)
        self.declare_parameter("ollama.host", "127.0.0.1")
        self.declare_parameter("ollama.port", 11434)
        self.declare_parameter("ollama.model", "llama3.2:3b")
        self.declare_parameter("ollama.timeout", 120.0)

        self.declare_parameter("gemini.enable", False)
        self.declare_parameter("gemini.api_key", "")
        self.declare_parameter("gemini.model", "gemini-2.0-flash")
        self.declare_parameter("gemini.timeout", 60.0)

    def _read_parameters(self) -> None:
        p = self.get_parameter
        self._default_provider = p("default_provider").value
        self._default_model = p("default_model").value
        self._silent = p("silent_mode").value

    # ==== PROVIDER INIT ====

    def _init_providers(self) -> None:
        p = self.get_parameter

        if p("ollama.enable").value:
            ollama = OllamaProvider(
                host=p("ollama.host").value,
                port=p("ollama.port").value,
                timeout=p("ollama.timeout").value,
                default_model=p("ollama.model").value,
            )
            ok, msg = ollama.connect()
            self._log(f"[ollama] {msg}") if ok else self.get_logger().warning(f"[ollama] {msg}")

            if ok:
                ok2, msg2 = ollama.ensure_model_ready(p("ollama.model").value)
                (
                    self._log(f"[ollama] {msg2}")
                    if ok2
                    else self.get_logger().warning(f"[ollama] {msg2}")
                )
                self._providers["ollama"] = ollama

        if p("gemini.enable").value:
            gemini = GeminiProvider(
                api_key=p("gemini.api_key").value,
                timeout=p("gemini.timeout").value,
                default_model=p("gemini.model").value,
            )
            ok, msg = gemini.connect()
            self._log(f"[gemini] {msg}") if ok else self.get_logger().warning(f"[gemini] {msg}")

            if ok:
                self._providers["gemini"] = gemini

    # ==== INFERENCE ACTION ====

    def _on_inference(self, goal_handle) -> LlmInference.Result:
        req = goal_handle.request
        t0 = time.monotonic()

        session = self._sessions.get(req.session_id)
        if session is None:
            goal_handle.abort()
            return LlmInference.Result(success=False, status="error", answer="Session not found.")

        provider = self._providers.get(session.provider)
        if provider is None:
            goal_handle.abort()
            return LlmInference.Result(
                success=False, status="error", answer="Provider not available."
            )

        format_schema = None
        if req.format_schema.strip():
            try:
                format_schema = json.loads(req.format_schema)
            except json.JSONDecodeError as exc:
                self.get_logger().warning(f"Invalid JSON schema, ignoring: {exc}")

        messages = session.build_messages(req.prompt)

        def stream_cb(token: str) -> bool:
            if goal_handle.is_cancel_requested:
                return False
            goal_handle.publish_feedback(LlmInference.Feedback(partial_text=token))
            return True

        result = provider.generate(
            model=session.model,
            messages=messages,
            max_tokens=req.max_tokens,
            format_schema=format_schema,
            stream_callback=stream_cb,
        )

        elapsed = time.monotonic() - t0

        if goal_handle.is_cancel_requested or result.error == "cancelled":
            goal_handle.canceled()
            return LlmInference.Result(success=False, status="cancelled", total_time=elapsed)

        if not result.success:
            self.get_logger().error(f"[{session.provider}] Inference error: {result.error}")
            goal_handle.abort()
            return LlmInference.Result(
                success=False, status="error", answer=result.error, total_time=elapsed
            )

        session.commit_turn(req.prompt, result.text)

        self._log(
            f"[{session.provider}/{session.model}] "
            f"session={req.session_id} "
            f"tokens={result.prompt_tokens}+{result.completion_tokens} "
            f"time={elapsed:.2f}s"
        )

        goal_handle.succeed()
        return LlmInference.Result(
            success=True,
            answer=result.text,
            total_time=elapsed,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            status="completed",
        )

    # ==== SESSION SERVICES ====

    def _on_create_session(self, request, response):
        provider_name = request.provider.strip() or self._default_provider

        if not provider_name or provider_name not in self._providers:
            response.success = False
            response.message = (
                f"Provider '{provider_name}' unavailable. Active: {list(self._providers.keys())}"
            )
            return response

        provider = self._providers[provider_name]
        model = request.model.strip() or provider.default_model

        ok, sid_or_error, _ = self._sessions.create(
            session_id=request.session_id,
            provider=provider_name,
            model=model,
            system_prompt=request.system_prompt,
            stateful=request.stateful,
        )

        response.success = ok
        response.session_id = sid_or_error if ok else ""
        response.message = "Session created." if ok else sid_or_error

        self._log(response.message) if ok else self.get_logger().warning(response.message)
        return response

    def _on_delete_session(self, request, response):
        ok, count = self._sessions.delete(request.session_id)
        response.success = ok
        response.deleted_count = count
        response.message = f"{count} session(s) deleted." if ok else "Session not found."
        self._log(response.message)
        return response

    def _on_list_sessions(self, _request, response):
        sessions = self._sessions.list_all()
        response.session_ids = [s["session_id"] for s in sessions]
        response.providers = [s["provider"] for s in sessions]
        response.models = [s["model"] for s in sessions]
        response.stateful = [s["stateful"] for s in sessions]
        response.history_turns = [s["history_turns"] for s in sessions]
        return response

    # ==== HELPERS ====

    def _log(self, msg: str) -> None:
        if not self._silent:
            self.get_logger().info(msg)

    def destroy_node(self) -> None:
        for name, provider in self._providers.items():
            provider.close()
            self._log(f"[{name}] connection closed.")
        super().destroy_node()


# ==== ENTRY POINT ====


def main(args=None):
    rclpy.init(args=args)
    node = LLMManagerNode()

    max_concurrent = node.get_parameter("max_concurrent").value
    executor = MultiThreadedExecutor(num_threads=max_concurrent + 2)
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
