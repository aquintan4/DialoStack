"""
DialogFSM — thin conversation driver.

Owns turn sequencing, timeouts and cancellation. Task-specific logic lives
in BaseDialogStrategy subclasses; the FSM never knows about slots, intents,
or explanations.
"""

import json
import logging
import time  # TRACE
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Callable

from .audio_io import AudioIO
from .strategies import BaseDialogStrategy, FSMConfig


class DialogState(Enum):
    INIT = auto()
    RUNNING = auto()
    SUCCESS = auto()
    ABORTED = auto()


@dataclass
class DialogResult:
    success: bool
    final_json: str = "{}"
    failure_reason: str = ""
    total_turns: int = 0


class DialogFSM:

    def __init__(
        self,
        task: str,
        strategy: BaseDialogStrategy,
        audio: AudioIO,
        config: FSMConfig,
        on_feedback: Callable[[str, str, str, int], None],
        is_cancelled: Callable[[], bool],
        timeout_prompt: str,
        log_path: str | None = None,
        log_max_mb: float = 10.0,
    ):
        self.task = task
        self.strategy = strategy
        self.audio = audio
        self.config = config
        self._feedback = on_feedback
        self._cancelled = is_cancelled
        self._timeout_prompt = timeout_prompt
        self._log = logging.getLogger("DialogFSM")
        self.state = DialogState.INIT
        self._turns = 0
        self._consecutive_timeouts = 0
        self._log_path = Path(log_path).expanduser() if log_path else None
        self._log_max_bytes = int(log_max_mb * 1024 * 1024) if log_max_mb > 0 else 0
        self._transcript_header()

    def run(self) -> DialogResult:
        """Execute the dialog loop. Always returns a DialogResult."""
        # TRACE
        self._log.info(f"[TRACE] fsm_start | t={time.monotonic():.4f}")
        # /TRACE
        try:
            opening = self.strategy.on_init(self.task)
        except Exception as exc:
            import traceback

            self._log.error(
                f"Strategy init failed: {type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            )
            result = DialogResult(success=False, failure_reason=f"Init error: {exc}")
            self._transcript_footer(result)
            return result

        # TRACE
        self._log.info(f"[TRACE] strategy_init_done | t={time.monotonic():.4f}")
        # /TRACE
        self.audio.clear_buffer()
        self._say(opening)
        self.state = DialogState.RUNNING

        while self.state == DialogState.RUNNING:
            if self._cancelled():
                self._abort("Cancelled by client")
                break

            if self.config.max_turns > 0 and self._turns >= self.config.max_turns:
                self._abort(f"Max turns ({self.config.max_turns}) reached")
                break

            # TRACE
            self._log.info(f"[TRACE] turn_start n={self._turns + 1} | t={time.monotonic():.4f}")
            # /TRACE
            user_text = self._listen()
            if user_text is None:
                continue

            self._turns += 1

            try:
                reply, done = self.strategy.on_user_turn(self.task, user_text)
            except Exception as exc:
                import traceback

                self._log.error(
                    f"Strategy turn error: {type(exc).__name__}: {exc}\n{traceback.format_exc()}"
                )
                self._abort(f"Strategy error: {exc}")
                break

            # TRACE
            self._log.info(
                f"[TRACE] turn_processed n={self._turns} done={done} | t={time.monotonic():.4f}"
            )
            # /TRACE
            self._say(reply)

            if done:
                self.state = (
                    DialogState.SUCCESS if self.strategy.succeeded() else DialogState.ABORTED
                )
                if self.state == DialogState.ABORTED:
                    self._log.warning("Strategy ended without success.")

        result = DialogResult(
            success=self.state == DialogState.SUCCESS,
            final_json=json.dumps(self.strategy.current_data(), ensure_ascii=False),
            failure_reason="" if self.state == DialogState.SUCCESS else self.state.name,
            total_turns=self._turns,
        )

        try:
            self.strategy.on_finish(result.success)
        except Exception as exc:
            self._log.warning(f"strategy.on_finish failed silently: {exc}")

        # TRACE
        self._log.info(
            f"[TRACE] fsm_end success={result.success} turns={result.total_turns} | t={time.monotonic():.4f}"
        )
        # /TRACE
        self._transcript_footer(result)
        return result

    # ==== HELPERS ====

    def _say(self, text: str) -> None:
        """Publish feedback, log, then speak. Feedback first so action clients
        see each utterance before TTS blocks."""
        self._feedback(
            self.strategy.current_phase(),
            json.dumps(self.strategy.current_data(), ensure_ascii=False),
            text,
            self._turns,
        )
        self._transcript_line("assistant", text)
        # TRACE
        _ts = time.monotonic()
        self._log.info(f"[TRACE] say_start chars={len(text)} | t={_ts:.4f}")
        # /TRACE
        self.audio.speak(text)
        # TRACE
        self._log.info(
            f"[TRACE] say_end elapsed={time.monotonic()-_ts:.3f}s | t={time.monotonic():.4f}"
        )
        # /TRACE

    def _listen(self) -> str | None:
        # TRACE
        _tl = time.monotonic()
        self._log.info(f"[TRACE] listen_start | t={_tl:.4f}")
        # /TRACE
        text = self.audio.listen()
        if text is None:
            # TRACE
            self._log.info(
                f"[TRACE] listen_timeout elapsed={time.monotonic()-_tl:.3f}s | t={time.monotonic():.4f}"
            )
            # /TRACE
            self._consecutive_timeouts += 1
            if self._consecutive_timeouts >= self.config.max_timeouts:
                self._abort("User timeout")
            else:
                self._say(self._timeout_prompt)
            return None
        # TRACE
        self._log.info(
            f"[TRACE] user_input_received elapsed={time.monotonic()-_tl:.3f}s | t={time.monotonic():.4f}"
        )
        # /TRACE
        self._consecutive_timeouts = 0
        self._transcript_line("user", text)
        return text

    def _abort(self, reason: str) -> None:
        self._log.warning(f"Aborting dialog: {reason}")
        self.state = DialogState.ABORTED

    # ==== TRANSCRIPT (best-effort, never raises) ====

    def _transcript_header(self) -> None:
        if not self._log_path:
            return
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            if (
                self._log_max_bytes > 0
                and self._log_path.exists()
                and self._log_path.stat().st_size >= self._log_max_bytes
            ):
                self._log_path.replace(self._log_path.with_suffix(".log.1"))
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(
                    f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} — New dialog ===\n"
                    f"Task: {self.task}\n\n"
                )
        except Exception as exc:
            self._log.warning(f"Could not open transcript {self._log_path}: {exc}")
            self._log_path = None

    def _transcript_line(self, role: str, text: str) -> None:
        if not self._log_path:
            return
        try:
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(f"[{datetime.now():%H:%M:%S}] {role:9s} {text}\n")
        except Exception:
            pass

    def _transcript_footer(self, result: DialogResult) -> None:
        if not self._log_path:
            return
        try:
            outcome = "success" if result.success else f"aborted ({result.failure_reason})"
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(
                    f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} — Ended: {outcome} "
                    f"({result.total_turns} turns) ===\n"
                    f"Final frame: {result.final_json}\n"
                )
        except Exception:
            pass
