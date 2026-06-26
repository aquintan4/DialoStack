"""
DialogManagerNode — central ROS2 node orchestrating spoken dialogs.

Designed for a single dialog at a time: a second goal is rejected while one
is already running (single microphone, single TTS channel).

Topics consumed:
  /transcription   (String) — ASR output from speech_to_text_node.
  /user_emotion    (String) — JSON {"emotion","confidence","source"}, optional.
  /user_speaking   (Bool)   — VAD signal; True interrupts ongoing TTS (barge-in).

Action server:
  /dialog/execute_task (ros2_dialog_interfaces/action/DialogTask)

Topics published:
  /robot_utterance (String) — each robot line, as it is sent to TTS.
  /barge_in        (BargeIn) — authoritative notice that the user cut an
                              ongoing utterance short (true barge-in). The
                              Monitor GUI consumes this instead of inferring
                              barge-in from the timing of unrelated topics.

Downstream clients:
  /llm/inference         (LlmInference)
  /llm/session/create    (CreateSession service)
  /llm/session/delete    (DeleteSession service)
  /speak                 (SpeakText action)
"""

import json
import logging
import threading
import time  # TRACE
from typing import Callable

import rclpy
from rclpy.action import ActionServer, ActionClient, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from std_msgs.msg import Bool, String

from ros2_llm_interfaces.action import LlmInference
from ros2_llm_interfaces.srv import CreateSession, DeleteSession
from ros2_dialog_interfaces.action import DialogTask, SpeakText
from ros2_dialog_interfaces.msg import BargeIn

from .audio_io import RosAudioIO
from .dialog_context import DialogContext, Resource, UserState
from .dialog_fsm import DialogFSM
from .strategies import BaseDialogStrategy, FSMConfig, available_modes, build_strategy
from .llm_client import LLMDialogClient, default_ack_phrases, default_timeout_prompt
from .prompt_builder import PromptBuilder
from .utils import clean_user_input

# ==== DIALOG MANAGER NODE ====


class DialogManagerNode(Node):

    def __init__(self):
        super().__init__(
            "dialog_manager_node",
            automatically_declare_parameters_from_overrides=True,
        )

        self._declare_parameters()
        self._read_parameters()
        self._configure_logging()
        self._templates = self._load_prompt_templates()

        self._active_goal_handle = None
        self._active_lock = threading.Lock()
        self._active_audio: RosAudioIO | None = None
        self._active_context: DialogContext | None = None

        self._user_state = UserState()
        self._user_state_lock = threading.Lock()

        self._cb = ReentrantCallbackGroup()
        self._llm_create = self.create_client(
            CreateSession, "/llm/session/create", callback_group=self._cb
        )
        self._llm_delete = self.create_client(
            DeleteSession, "/llm/session/delete", callback_group=self._cb
        )
        self._llm_action = ActionClient(
            self, LlmInference, "/llm/inference", callback_group=self._cb
        )
        self._tts_client = ActionClient(self, SpeakText, "/speak", callback_group=self._cb)

        self.create_subscription(
            String, self._transcription_topic, self._on_transcription, 10, callback_group=self._cb
        )
        self.create_subscription(
            String, self._user_emotion_topic, self._on_emotion, 10, callback_group=self._cb
        )
        if self._user_speaking_topic:
            self.create_subscription(
                Bool, self._user_speaking_topic, self._on_user_speaking, 10, callback_group=self._cb
            )

        ActionServer(
            self,
            DialogTask,
            "/dialog/execute_task",
            execute_callback=self._on_execute,
            goal_callback=self._on_goal_request,
            cancel_callback=lambda _: CancelResponse.ACCEPT,
            callback_group=self._cb,
        )

        self._robot_utterance_pub = self.create_publisher(
            String, "/robot_utterance", 10
        )
        # Reliable QoS (default depth 10): the barge-in notice is the GUI's only
        # source of truth, so it must not be dropped the way a best-effort signal
        # could be.
        self._barge_in_pub = self.create_publisher(BargeIn, "/barge_in", 10)

        self._log("Dialog Manager ready (single-dialog mode).")

    # ==== PARAMETER HANDLING ====

    def _declare_parameters(self) -> None:
        defaults: dict[str, object] = {
            "transcription_topic": "/transcription",
            "user_emotion_topic": "/user_emotion",
            "user_speaking_topic": "/user_speaking",
            "wait_timeout": 20.0,
            "llm_timeout": 120.0,
            "tts_timeout": 60.0,
            "max_timeouts": 2,
            "max_unclear": 3,
            "max_attempts": 3,
            "llm_provider": "",
            "llm_model": "",
            "silent_mode": False,
            "timeout_prompt": "",
            "conversation_log_path": "/tmp/dialog_conversations.log",
            "conversation_log_max_mb": 10.0,
            "language": "Spanish",
            "history_max_turns": 200,
            "ack_phrases": [""],  # Empty list disables acknowledgment; set in app_params.yaml
        }
        for name, default in defaults.items():
            if not self.has_parameter(name):
                self.declare_parameter(name, default)

    def _read_parameters(self) -> None:
        p = self.get_parameter
        self._transcription_topic = p("transcription_topic").value
        self._user_emotion_topic = p("user_emotion_topic").value
        self._user_speaking_topic = p("user_speaking_topic").value
        self._wait_timeout = p("wait_timeout").value
        self._llm_timeout = p("llm_timeout").value
        self._tts_timeout = p("tts_timeout").value
        self._max_timeouts = p("max_timeouts").value
        self._max_unclear = p("max_unclear").value
        self._max_attempts = p("max_attempts").value
        self._llm_provider = p("llm_provider").value
        self._llm_model = p("llm_model").value
        self._silent = p("silent_mode").value
        self._conversation_log_path = p("conversation_log_path").value
        self._conversation_log_max_mb = p("conversation_log_max_mb").value
        self._language = p("language").value
        self._history_max_turns = p("history_max_turns").value

        # Canned-phrase overrides from the Strategies editor (params under
        # "phrases.*"). 'ack' (list) and 'timeout' (str) feed the FSM; the rest
        # are NLG fallbacks layered over the language defaults in LLMDialogClient.
        phrases = self._load_phrase_overrides()
        ack_ovr = phrases.pop("ack", None)
        timeout_ovr = phrases.pop("timeout", None)
        self._phrase_overrides = phrases

        # Precedence for ack / timeout: phrases.* override > legacy dedicated
        # param > language-aware default. Empty everywhere => follows `language`.
        legacy_ack = tuple(s for s in (p("ack_phrases").value or []) if s.strip())
        ack_ovr = tuple(s for s in (ack_ovr or []) if s and s.strip())
        self._ack_phrases = ack_ovr or legacy_ack or default_ack_phrases(self._language)

        legacy_timeout = (p("timeout_prompt").value or "").strip()
        self._timeout_prompt = (
            (timeout_ovr or "").strip() or legacy_timeout or default_timeout_prompt(self._language)
        )

    def _load_phrase_overrides(self) -> dict:
        """Read non-empty 'phrases.*' params (auto-declared from the params file)."""
        out: dict = {}
        for name, param in self.get_parameters_by_prefix("phrases").items():
            val = param.value
            if val is None:
                continue
            if isinstance(val, str):
                if val.strip():
                    out[name] = val
            else:  # 'ack' arrives as a string list
                out[name] = val
        return out

    def _configure_logging(self) -> None:
        level = logging.WARNING if self._silent else logging.INFO
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
        for name in (
            "DialogFSM",
            "SlotFillingStrategy",
            "ExplanationStrategy",
            "QuizStrategy",
            "LLMDialogClient",
        ):
            log = logging.getLogger(name)
            log.setLevel(level)
            if not log.handlers:
                log.addHandler(handler)
            log.propagate = False

    def _load_prompt_templates(self) -> dict[str, str]:
        import string

        params = self.get_parameters_by_prefix("prompts")
        templates = {k: v.value for k, v in params.items() if v.value}
        if not templates:
            self.get_logger().fatal(
                "No prompt templates loaded. Check that prompts.yaml is passed via --params-file."
            )
            raise RuntimeError("prompts.yaml missing or empty under 'prompts.*'")

        broken: list[str] = []
        for name, tpl in templates.items():
            try:
                for _, field_name, _, _ in string.Formatter().parse(tpl):
                    if field_name is None or field_name == "":
                        continue
                    if not field_name.isidentifier():
                        broken.append(f"{name}: malformed placeholder '{{{field_name}}}'")
            except ValueError as exc:
                broken.append(f"{name}: format-string error: {exc}")

        if broken:
            for line in broken:
                self.get_logger().fatal(f"Bad prompt template — {line}")
            raise RuntimeError(
                "Invalid format strings in prompts.yaml. Literal '{' and '}' must be doubled."
            )
        return templates

    # ==== SINGLE-DIALOG GATE ====

    def _on_goal_request(self, _goal_request) -> GoalResponse:
        with self._active_lock:
            if self._active_goal_handle is not None:
                self.get_logger().warning("Rejecting new dialog: another one is already running.")
                return GoalResponse.REJECT
            return GoalResponse.ACCEPT

    # ==== ACTION EXECUTION ====

    def _on_execute(self, goal_handle) -> DialogTask.Result:
        req = goal_handle.request
        self._log(f"New dialog task: '{req.task_description[:60]}'")
        # TRACE
        _t0 = time.monotonic()
        self.get_logger().info(f"[TRACE] goal_received | t={_t0:.4f}")
        # /TRACE

        with self._active_lock:
            self._active_goal_handle = goal_handle

        nlu_sid = None
        nlg_sid = None
        result = None
        try:
            nlu_sid = self._create_llm_session("dlg_nlu", stateful=False)
            nlg_sid = self._create_llm_session("dlg_nlg", stateful=False)
            # TRACE
            self.get_logger().info(
                f"[TRACE] sessions_ready nlu={nlu_sid} nlg={nlg_sid} | t={time.monotonic():.4f}"
            )
            # /TRACE
            if not nlu_sid or not nlg_sid:
                goal_handle.abort()
                return DialogTask.Result(
                    success=False, failure_reason="LLM Manager connection failed"
                )

            ctx, audio = self._setup_dialog_resources(req)
            llm_client, config = self._build_llm_client_and_config(req, nlu_sid, nlg_sid)

            try:
                strategy = self._resolve_strategy(req, llm_client, config, ctx)
            except ValueError as exc:
                self.get_logger().error(str(exc))
                goal_handle.abort()
                return DialogTask.Result(success=False, failure_reason=str(exc))

            fsm = DialogFSM(
                task=req.task_description,
                strategy=strategy,
                audio=audio,
                config=config,
                on_feedback=lambda phase, frame_json, utterance, turns: self._publish_feedback(
                    goal_handle, phase, frame_json, utterance, turns
                ),
                is_cancelled=lambda: goal_handle.is_cancel_requested,
                timeout_prompt=self._timeout_prompt,
                log_path=self._conversation_log_path,
                log_max_mb=self._conversation_log_max_mb,
            )

            try:
                result = fsm.run()
            except Exception as exc:
                self.get_logger().error(f"FSM error: {exc}")
        finally:
            self._delete_llm_session(nlu_sid)
            self._delete_llm_session(nlg_sid)
            self._clear_active()

        # TRACE
        _success = result.success if result else False
        _turns = result.total_turns if result else 0
        self.get_logger().info(
            f"[TRACE] task_done success={_success} turns={_turns} elapsed={time.monotonic()-_t0:.3f}s | t={time.monotonic():.4f}"
        )
        # /TRACE
        return self._finalize_result(goal_handle, result)

    def _setup_dialog_resources(self, req) -> tuple[DialogContext, RosAudioIO]:
        ctx = self._build_context(req)
        audio = RosAudioIO(self, self._wait_timeout)
        with self._active_lock:
            self._active_audio = audio
            self._active_context = ctx
        return ctx, audio

    def _build_llm_client_and_config(
        self, req, nlu_sid: str, nlg_sid: str
    ) -> tuple[LLMDialogClient, FSMConfig]:
        pb = PromptBuilder(self._templates, language=self._language)
        llm_client = LLMDialogClient(
            nlu_sid,
            nlg_sid,
            self._infer_sync,
            pb,
            language=self._language,
            history_max_turns=self._history_max_turns,
            phrase_overrides=self._phrase_overrides,
        )
        config = FSMConfig(
            max_turns=req.max_turns,
            max_timeouts=self._max_timeouts,
            max_unclear=self._max_unclear,
            max_attempts=self._max_attempts,
            ack_phrases=self._ack_phrases,
        )
        return llm_client, config

    # Registry resolves the strategy class; no if/elif here so adding a new
    # mode is a one-file addition in strategies/.
    def _resolve_strategy(
        self, req, llm_client: LLMDialogClient, config: FSMConfig, ctx: DialogContext
    ) -> BaseDialogStrategy:
        dialog_mode = getattr(req, "dialog_mode", "").strip()
        if not dialog_mode:
            dialog_mode = llm_client.classify_task_mode(req.task_description, ctx)
        self._log(f"Dialog mode: {dialog_mode}")
        # TRACE
        self.get_logger().info(
            f"[TRACE] strategy_resolved mode={dialog_mode} | t={time.monotonic():.4f}"
        )
        # /TRACE
        return build_strategy(mode=dialog_mode, llm=llm_client, config=config, ctx=ctx, request=req)

    def _finalize_result(self, goal_handle, result) -> DialogTask.Result:
        if not result:
            goal_handle.abort()
            return DialogTask.Result(success=False, failure_reason="Internal FSM Error")
        if goal_handle.is_cancel_requested:
            goal_handle.canceled()
            return DialogTask.Result(
                success=False, failure_reason="Cancelled", total_turns=result.total_turns
            )
        if result.success:
            goal_handle.succeed()
            return DialogTask.Result(
                success=True, final_frame_json=result.final_json, total_turns=result.total_turns
            )
        goal_handle.abort()
        return DialogTask.Result(
            success=False, failure_reason=result.failure_reason, total_turns=result.total_turns
        )

    @staticmethod
    def _publish_feedback(
        goal_handle, phase: str, frame_json: str, utterance: str, turns: int
    ) -> None:
        fb = DialogTask.Feedback()
        fb.state = phase
        fb.current_frame_json = frame_json
        fb.last_utterance = utterance
        fb.turns = turns
        goal_handle.publish_feedback(fb)

    def _clear_active(self) -> None:
        with self._active_lock:
            self._active_goal_handle = None
            self._active_audio = None
            self._active_context = None

    # ==== CONTEXT BUILDING ====

    def _build_context(self, req) -> DialogContext:
        # TRACE
        self.get_logger().info(f"[TRACE] context_build_start | t={time.monotonic():.4f}")
        # /TRACE
        resources: list[Resource] = []
        resources_json = getattr(req, "resources_json", "[]")
        if resources_json:
            try:
                for r in json.loads(resources_json):
                    if isinstance(r, dict) and "name" in r and "content" in r:
                        resources.append(
                            Resource(
                                name=r["name"],
                                description=r.get("description", ""),
                                content=r["content"],
                            )
                        )
            except Exception as exc:
                self.get_logger().warning(f"Could not parse resources_json: {exc}")

        ctx = DialogContext(resources=resources, domain=getattr(req, "domain", ""))

        with self._user_state_lock:
            _emotion = self._user_state.emotion  # TRACE
            ctx.update_user_state(
                UserState(
                    emotion=self._user_state.emotion,
                    confidence=self._user_state.confidence,
                    source=self._user_state.source,
                    timestamp=self._user_state.timestamp,
                )
            )
        # TRACE
        self.get_logger().info(
            f"[TRACE] context_built resources={len(resources)} has_domain={bool(ctx.domain)} emotion={_emotion} | t={time.monotonic():.4f}"
        )
        # /TRACE
        return ctx

    # ==== SUBSCRIPTIONS ====

    def _on_transcription(self, msg: String) -> None:
        clean = clean_user_input(msg.data)
        if not clean:
            return
        with self._active_lock:
            audio = self._active_audio
        if audio is not None:
            audio.on_transcription(clean)

    def _on_emotion(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            state = UserState(
                emotion=data.get("emotion", "neutral"),
                confidence=float(data.get("confidence", 0.0)),
                source=data.get("source", "unknown"),
            )
        except Exception as exc:
            self.get_logger().warning(f"Could not parse /user_emotion message: {exc}")
            return

        # TRACE
        self.get_logger().info(
            f"[TRACE] emotion_update emotion={state.emotion} conf={state.confidence:.2f} src={state.source} | t={time.monotonic():.4f}"
        )
        # /TRACE
        with self._user_state_lock:
            self._user_state = state

        with self._active_lock:
            ctx = self._active_context
        if ctx is not None:
            ctx.update_user_state(state)

    def _on_user_speaking(self, msg: Bool) -> None:
        with self._active_lock:
            audio = self._active_audio
        if audio is not None:
            audio.on_user_speaking(msg.data)

    # ==== LLM SESSION HELPERS ====

    def _create_llm_session(self, session_id: str, stateful: bool) -> str | None:
        if not self._llm_create.wait_for_service(timeout_sec=5.0):
            return None
        req = CreateSession.Request(
            session_id=session_id,
            provider=self._llm_provider,
            model=self._llm_model,
            stateful=stateful,
        )
        res = self._call_service_sync(self._llm_create, req)
        return res.session_id if res and res.success else None

    def _delete_llm_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        if not self._llm_delete.wait_for_service(timeout_sec=3.0):
            return
        self._call_service_sync(self._llm_delete, DeleteSession.Request(session_id=session_id))

    # ==== INFERENCE WRAPPER ====

    def _infer_sync(
        self, session_id: str, prompt: str, max_tokens: int, schema: dict | None
    ) -> str | None:
        if not prompt or not prompt.strip():
            self.get_logger().error("Empty prompt; aborting inference.")
            return None
        if not self._llm_action.wait_for_server(timeout_sec=5.0):
            self.get_logger().error("LLM action server not available.")
            return None

        goal = LlmInference.Goal(
            session_id=session_id,
            prompt=prompt,
            max_tokens=max_tokens or 0,
            format_schema=json.dumps(schema) if schema else "",
        )
        # TRACE
        _ti = time.monotonic()
        self.get_logger().info(
            f"[TRACE] llm_infer_start sid={session_id} max_tokens={max_tokens} | t={_ti:.4f}"
        )
        # /TRACE
        result = self._action_call_sync(
            client=self._llm_action,
            goal=goal,
            timeout_secs=self._llm_timeout,
            external_cancel=lambda: (
                self._active_goal_handle is not None
                and self._active_goal_handle.is_cancel_requested
            ),
        )
        # TRACE
        self.get_logger().info(
            f"[TRACE] llm_infer_end sid={session_id} elapsed={time.monotonic()-_ti:.3f}s | t={time.monotonic():.4f}"
        )
        # /TRACE
        if result is None:
            return None
        if not result.result.success:
            self.get_logger().error(f"LLM inference error: {result.result.answer}")
            return None
        return result.result.answer

    # ==== TTS WRAPPER ====

    def _speak_sync(self, text: str, interrupt_event: threading.Event) -> None:
        if not text or not self._tts_client.wait_for_server(timeout_sec=5.0):
            return
        self._robot_utterance_pub.publish(String(data=text))
        # TRACE
        _ts = time.monotonic()
        self.get_logger().info(f"[TRACE] tts_start chars={len(text)} | t={_ts:.4f}")
        # /TRACE
        # Record whether the playback ended because the user barged in (the
        # interrupt event fired) rather than finishing or timing out. This is the
        # authoritative barge-in detection: only here does the robot know for
        # certain that the user cut it off mid-utterance.
        barged_in = False

        def cancel_if_interrupted() -> bool:
            nonlocal barged_in
            if interrupt_event.is_set():
                barged_in = True
                return True
            return False

        self._action_call_sync(
            client=self._tts_client,
            goal=SpeakText.Goal(text=text, speed=1.0),
            timeout_secs=self._tts_timeout,
            external_cancel=cancel_if_interrupted,
        )
        if barged_in:
            spoken_ms = int((time.monotonic() - _ts) * 1000)
            self._barge_in_pub.publish(BargeIn(utterance=text, spoken_ms=spoken_ms))
        # TRACE
        self.get_logger().info(
            f"[TRACE] tts_end barged_in={barged_in} elapsed={time.monotonic()-_ts:.3f}s | t={time.monotonic():.4f}"
        )
        # /TRACE

    # ==== GENERIC ACTION CALL ====

    def _action_call_sync(
        self,
        client: ActionClient,
        goal,
        timeout_secs: float,
        external_cancel: Callable[[], bool] | None = None,
    ):
        """Send goal and block until done, timeout, or external cancel.
        Cancels the remote goal on timeout or external cancel to avoid server-side leaks."""
        done = threading.Event()
        goal_handle_box: list = [None]
        result_box: list = [None]

        def on_accepted(future):
            gh = future.result()
            if not gh or not gh.accepted:
                done.set()
                return
            goal_handle_box[0] = gh
            gh.get_result_async().add_done_callback(
                lambda r: (result_box.__setitem__(0, r.result()), done.set())
            )

        client.send_goal_async(goal).add_done_callback(on_accepted)

        elapsed = 0.0
        poll = 0.05
        while not done.wait(timeout=poll):
            elapsed += poll
            if elapsed >= timeout_secs:
                gh = goal_handle_box[0]
                if gh is not None:
                    gh.cancel_goal_async()
                self.get_logger().warning(f"Action call timed out after {timeout_secs:.0f}s.")
                return None
            if external_cancel and external_cancel():
                gh = goal_handle_box[0]
                if gh is not None:
                    gh.cancel_goal_async()
                done.wait(timeout=1.0)
                return None

        return result_box[0]

    # ==== SERVICE HELPER ====

    def _call_service_sync(self, client, req, timeout: float = 10.0):
        done = threading.Event()
        result = [None]

        def cb(future):
            try:
                result[0] = future.result()
            finally:
                done.set()

        client.call_async(req).add_done_callback(cb)
        done.wait(timeout=timeout)
        return result[0]

    # ==== LOGGING ====

    def _log(self, msg: str) -> None:
        if not self._silent:
            self.get_logger().info(msg)


def main(args=None):
    rclpy.init(args=args)
    node = DialogManagerNode()

    executor = MultiThreadedExecutor(num_threads=6)
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
