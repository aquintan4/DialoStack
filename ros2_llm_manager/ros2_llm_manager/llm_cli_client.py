"""
LlmCliClient — interactive terminal client for the LLM Manager node.

Useful for validating provider connectivity, session isolation, history
management and streaming behaviour without needing a full dialog stack.

Commands:
  /new [provider] [model]   Open a new session (defaults from node params).
  /session <id>             Switch active session.
  /list                     List all open sessions.
  /info                     Show details of the active session.
  /delete [id]              Delete a session (default: active).
  /stream                   Toggle streaming on / off.
  /stateless                Toggle stateful / stateless for the next /new.
  /clear                    Clear the terminal.
  /help                     Show this help.
  /quit                     Close all sessions and exit.
  <any other text>          Send a prompt to the active session.

ROS interfaces consumed:
  Action client   /llm/inference          (LlmInference)
  Service client  /llm/session/create     (CreateSession)
  Service client  /llm/session/delete     (DeleteSession)
  Service client  /llm/session/list       (ListSessions)
"""

import os
import sys
import threading
import uuid

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from ros2_llm_interfaces.action import LlmInference
from ros2_llm_interfaces.srv import CreateSession, DeleteSession, ListSessions

# Hard timeout for a single inference round-trip.
_INFERENCE_TIMEOUT_SECS = 120.0
# Hard timeout for service calls (create / delete / list).
_SERVICE_TIMEOUT_SECS = 10.0


class LlmCliClient(Node):

    def __init__(self):
        super().__init__("llm_cli_client")

        self._declare_parameters()
        self._read_parameters()

        self._cb = ReentrantCallbackGroup()

        self._action_client = ActionClient(
            self, LlmInference, "/llm/inference", callback_group=self._cb
        )
        self._create_client = self.create_client(
            CreateSession, "/llm/session/create", callback_group=self._cb
        )
        self._delete_client = self.create_client(
            DeleteSession, "/llm/session/delete", callback_group=self._cb
        )
        self._list_client = self.create_client(
            ListSessions, "/llm/session/list", callback_group=self._cb
        )

        # Session state.
        self._active_id: str | None = None
        self._sessions: dict[str, dict] = {}  # id → {provider, model, stateful}
        self._session_lock = threading.Lock()

        # Inference state.
        self._goal_event = threading.Event()
        self._streaming = True
        self._next_stateful = True

        self._running = threading.Event()
        self._running.set()

    # ==== PARAMETER HANDLING ====

    def _declare_parameters(self) -> None:
        self.declare_parameter("default_provider", "")
        self.declare_parameter("default_model", "")

    def _read_parameters(self) -> None:
        p = self.get_parameter
        self._default_provider = p("default_provider").value
        self._default_model = p("default_model").value

    # ==== TERMINAL LOOP ====

    def run(self) -> None:
        """Blocking terminal loop. Runs in a dedicated thread."""
        _print_header()
        _print_help()

        while rclpy.ok() and self._running.is_set():
            try:
                prompt = input(self._prompt_str()).strip()
            except (EOFError, KeyboardInterrupt):
                self._cmd_quit()
                break

            if not prompt:
                continue

            if prompt.startswith("/"):
                self._dispatch_command(prompt)
            else:
                self._send_prompt(prompt)

    def _prompt_str(self) -> str:
        sid = self._active_id or "none"
        mode = "stream" if self._streaming else "block"
        sf = "stateful" if self._next_stateful else "stateless"
        return f"[{sid[:8]}|{mode}|{sf}] > "

    def _dispatch_command(self, raw: str) -> None:
        parts = raw.split()
        cmd = parts[0].lower()

        dispatch = {
            "/new": self._cmd_new,
            "/session": self._cmd_session,
            "/list": self._cmd_list,
            "/info": self._cmd_info,
            "/delete": self._cmd_delete,
            "/stream": self._cmd_toggle_stream,
            "/stateless": self._cmd_toggle_stateless,
            "/clear": self._cmd_clear,
            "/help": lambda _: _print_help(),
            "/quit": self._cmd_quit,
        }

        handler = dispatch.get(cmd)
        if handler is None:
            _print_system(f"Unknown command '{cmd}'. Type /help for the list.")
            return
        handler(parts)

    # ==== COMMANDS ====

    def _cmd_new(self, parts: list[str]) -> None:
        provider = parts[1] if len(parts) > 1 else self._default_provider
        model = parts[2] if len(parts) > 2 else self._default_model

        sid = str(uuid.uuid4())[:8]
        req = CreateSession.Request(
            session_id=sid,
            provider=provider,
            model=model,
            system_prompt="",
            stateful=self._next_stateful,
        )

        res = self._call_service(self._create_client, req)
        if res is None:
            _print_system("Session service not available.")
            return
        if not res.success:
            _print_system(f"Failed to create session: {res.message}")
            return

        actual_id = res.session_id
        with self._session_lock:
            self._sessions[actual_id] = {
                "provider": provider or "(default)",
                "model": model or "(default)",
                "stateful": self._next_stateful,
            }
            self._active_id = actual_id

        sf = "stateful" if self._next_stateful else "stateless"
        _print_system(
            f"Session created: {actual_id}  "
            f"provider={provider or '(default)'}  "
            f"model={model or '(default)'}  "
            f"mode={sf}"
        )

    def _cmd_session(self, parts: list[str]) -> None:
        if len(parts) < 2:
            _print_system("Usage: /session <id>")
            return

        target = parts[1]
        with self._session_lock:
            # Accept prefix match for convenience.
            match = next((k for k in self._sessions if k.startswith(target)), None)
            if match is None:
                _print_system(f"No session matching '{target}'. Run /list to see active sessions.")
                return
            self._active_id = match

        _print_system(f"Active session: {self._active_id}")

    def _cmd_list(self, _parts: list[str]) -> None:
        res = self._call_service(self._list_client, ListSessions.Request())
        if res is None:
            _print_system("List service not available.")
            return

        if not res.session_ids:
            _print_system("No active sessions.")
            return

        _print_system("Active sessions:")
        for sid, provider, model, stateful, turns in zip(
            res.session_ids,
            res.providers,
            res.models,
            res.stateful,
            res.history_turns,
        ):
            marker = " <-- active" if sid == self._active_id else ""
            sf = "stateful" if stateful else "stateless"
            print(f"    {sid}  provider={provider}  model={model}  {sf}  turns={turns}{marker}")

    def _cmd_info(self, _parts: list[str]) -> None:
        with self._session_lock:
            sid = self._active_id
            info = self._sessions.get(sid)

        if sid is None or info is None:
            _print_system("No active session. Use /new to create one.")
            return

        # Fetch live turn count from the node.
        res = self._call_service(self._list_client, ListSessions.Request())
        turns = 0
        if res:
            for i, s in enumerate(res.session_ids):
                if s == sid:
                    turns = res.history_turns[i]
                    break

        sf = "stateful" if info["stateful"] else "stateless"
        _print_system(
            f"Session : {sid}\n"
            f"    provider : {info['provider']}\n"
            f"    model    : {info['model']}\n"
            f"    mode     : {sf}\n"
            f"    turns    : {turns}"
        )

    def _cmd_delete(self, parts: list[str]) -> None:
        with self._session_lock:
            if len(parts) > 1:
                target = next((k for k in self._sessions if k.startswith(parts[1])), None)
                if target is None:
                    _print_system(f"No session matching '{parts[1]}'.")
                    return
            else:
                target = self._active_id

        if target is None:
            _print_system("No active session to delete.")
            return

        req = DeleteSession.Request(session_id=target)
        res = self._call_service(self._delete_client, req)
        if res is None:
            _print_system("Delete service not available.")
            return

        if res.success:
            with self._session_lock:
                self._sessions.pop(target, None)
                if self._active_id == target:
                    # Switch to another open session if one exists, else None.
                    self._active_id = next(iter(self._sessions), None)
            fallback = f"  Active session is now: {self._active_id}" if self._active_id else ""
            _print_system(f"Session {target} deleted.{fallback}")
        else:
            _print_system(f"Could not delete session: {res.message}")

    def _cmd_toggle_stream(self, _parts: list[str]) -> None:
        self._streaming = not self._streaming
        state = "on" if self._streaming else "off"
        _print_system(f"Streaming {state}.")

    def _cmd_toggle_stateless(self, _parts: list[str]) -> None:
        self._next_stateful = not self._next_stateful
        state = "stateful" if self._next_stateful else "stateless"
        _print_system(f"Next session will be {state}.")

    def _cmd_clear(self, _parts: list[str]) -> None:
        os.system("clear")

    def _cmd_quit(self, _parts: list[str] = None) -> None:
        _print_system("Closing all sessions and exiting…")
        with self._session_lock:
            ids = list(self._sessions.keys())
        for sid in ids:
            self._call_service(self._delete_client, DeleteSession.Request(session_id=sid))
        self._running.clear()
        if rclpy.ok():
            rclpy.shutdown()

    # ==== INFERENCE ====

    def _send_prompt(self, prompt: str) -> None:
        with self._session_lock:
            sid = self._active_id

        if sid is None:
            _print_system("No active session. Use /new to create one first.")
            return

        if not self._action_client.wait_for_server(timeout_sec=5.0):
            _print_system("LLM action server not available.")
            return

        goal = LlmInference.Goal()
        goal.session_id = sid
        goal.prompt = prompt
        goal.max_tokens = 0
        goal.format_schema = ""

        self._goal_event.clear()

        send_future = self._action_client.send_goal_async(
            goal,
            feedback_callback=self._on_feedback if self._streaming else None,
        )
        send_future.add_done_callback(self._on_goal_response)

        print("Bot: ", end="", flush=True)
        if not self._goal_event.wait(timeout=_INFERENCE_TIMEOUT_SECS):
            _print_system("Inference timed out.")

    def _on_feedback(self, feedback_msg) -> None:
        print(feedback_msg.feedback.partial_text, end="", flush=True)

    def _on_goal_response(self, future) -> None:
        goal_handle = future.result()
        if not goal_handle or not goal_handle.accepted:
            print()
            _print_system("Goal rejected by the server.")
            self._goal_event.set()
            return
        goal_handle.get_result_async().add_done_callback(self._on_result)

    def _on_result(self, future) -> None:
        try:
            wrapped = future.result()
            result = wrapped.result
            if not self._streaming:
                # In blocking mode the full answer arrives here; print it now.
                print(result.answer)
            else:
                print()  # newline after streamed tokens

            if not result.success:
                _print_system(f"Inference error: {result.answer}")
            else:
                _print_system(
                    f"tokens={result.prompt_tokens}+{result.completion_tokens}  "
                    f"time={result.total_time:.2f}s"
                )
        except Exception as exc:
            _print_system(f"Result callback error: {exc}")
        finally:
            self._goal_event.set()

    # ==== SERVICE HELPER ====

    def _call_service(self, client, req):
        done = threading.Event()
        result = [None]

        def cb(future):
            try:
                result[0] = future.result()
            except Exception as exc:
                self.get_logger().warning(f"Service call failed: {exc}")
            finally:
                done.set()

        client.call_async(req).add_done_callback(cb)
        done.wait(timeout=_SERVICE_TIMEOUT_SECS)
        return result[0]


# ==== PRESENTATION HELPERS ====


def _print_system(msg: str) -> None:
    print(f"[system] {msg}")


def _print_header() -> None:
    print()
    print("LLM Manager — interactive test client")
    print("Type /help for the list of commands.")
    print()


def _print_help() -> None:
    print()
    print("Commands:")
    print("  /new [provider] [model]   Open a new session.")
    print("  /session <id>             Switch active session (prefix match).")
    print("  /list                     List all open sessions.")
    print("  /info                     Show active session details.")
    print("  /delete [id]              Delete a session (default: active).")
    print("  /stream                   Toggle streaming on / off.")
    print("  /stateless                Toggle stateful / stateless for next /new.")
    print("  /clear                    Clear the terminal.")
    print("  /help                     Show this help.")
    print("  /quit                     Close all sessions and exit.")
    print("  <any other text>          Send prompt to the active session.")
    print()


# ==== ENTRY POINT ====


def main(args=None):
    rclpy.init(args=args)
    node = LlmCliClient()

    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)

    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        spin_thread.join(timeout=2.0)


if __name__ == "__main__":
    main()
