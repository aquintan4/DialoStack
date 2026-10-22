"""
ProcedureStrategy — guides the user through an ordered list of steps.

The caller supplies the steps via resources_json. The content of the first
resource that parses as a JSON list of steps is used as the procedure. Each
step is either a plain string or an object:
    {"step": "...", "check": "..."}
    (also accepts "instruction" for "step"; "check" is optional and states
    what the user should observe or report once the step is done)

Each user turn is classified against the current step:
    done       -> mark completed, present the next step (or close)
    question   -> answer it, stay on the step
    problem    -> help / rephrase the step; after max_attempts it is marked
                  "stuck" and the procedure moves on
    repeat     -> present the current step again
    back       -> return to the previous step
    skip       -> mark skipped, present the next step
    unclear    -> remind the user to report when the step is done

current_data() returns:
    {"total_steps": N, "current_step": k, "completed": M, "skipped": S,
     "results": [{"step": "...", "status": "done|skipped|stuck"}, ...]}
"""

import logging
import time  # TRACE

from ..utils import parse_loose_json
from .base import BaseDialogStrategy, FSMConfig, register_strategy


@register_strategy("procedure")
class ProcedureStrategy(BaseDialogStrategy):

    def __init__(self, llm, config: FSMConfig, ctx, request=None):
        super().__init__(llm, config, ctx, request)
        self._steps: list[dict] = self._parse_steps(ctx)
        self._idx = 0
        self._status: list[str | None] = [None] * len(self._steps)
        self._attempts = 0  # help attempts on the current step
        self._turns = 0
        self._completed = False
        self._history: list[dict] = []
        self._log = logging.getLogger("ProcedureStrategy")
        self._skip_intro: bool = bool(getattr(request, "skip_intro", False)) if request else False

    @staticmethod
    def _parse_steps(ctx) -> list[dict]:
        for resource in ctx.resources:
            content = (getattr(resource, "content", "") or "").strip()
            if not content:
                continue
            try:
                data = parse_loose_json(content)
            except Exception:
                continue
            if not isinstance(data, list):
                continue
            items: list[dict] = []
            for entry in data:
                if isinstance(entry, str):
                    text, check = entry, ""
                elif isinstance(entry, dict):
                    text = entry.get("step") or entry.get("instruction") or ""
                    check = entry.get("check") or ""
                else:
                    continue
                if isinstance(text, str) and text.strip():
                    items.append({"step": text.strip(), "check": str(check).strip()})
            if items:
                return items
        return []

    # ==== LIFECYCLE ====

    def on_init(self, task: str) -> str:
        if not self._steps:
            raise ValueError(
                "ProcedureStrategy requires a resource with a JSON list of steps "
                "(strings or {'step','check'} objects) in its content field."
            )
        step = self._present("first")
        if self._skip_intro:
            opening = step
        else:
            intro = self._llm.procedure_opening(task, len(self._steps), self._ctx)
            opening = f"{intro} {step}"
        self._history.append({"role": "assistant", "content": opening})
        return opening

    def on_user_turn(self, task: str, user_text: str) -> tuple[str, bool]:
        cancel_result = self._cancel_pre_check(task, user_text, strict=False)
        if cancel_result is not None:
            return cancel_result

        self._turns += 1
        self._history.append({"role": "user", "content": user_text})
        current = self._steps[self._idx]
        intent = self._llm.classify_step_turn(
            user_text, current["step"], current["check"], self._history, self._ctx
        )
        # TRACE
        self._log.info(
            f"[TRACE] procedure_turn step={self._idx + 1} intent={intent} | t={time.monotonic():.4f}"
        )
        # /TRACE

        if intent == "done":
            reply, done = self._advance(task, "done")
        elif intent == "skip":
            reply, done = self._advance(task, "skipped")
        elif intent == "question":
            reply = self._llm.procedure_answer_question(
                user_text, task, current["step"], self._history, self._ctx
            )
            done = False
        elif intent == "problem":
            reply, done = self._help(task)
        elif intent == "repeat":
            reply, done = self._present("repeat"), False
        elif intent == "back":
            if self._idx > 0:
                self._idx -= 1
                self._status[self._idx] = None
                self._attempts = 0
            reply, done = self._present("back"), False
        else:  # unclear
            reply, done = self._llm.procedure_remind(current["step"], self._ctx), False

        self._history.append({"role": "assistant", "content": reply})
        return reply, done

    # ==== STEP HANDLING ====

    def _present(self, situation: str) -> str:
        """Speak the current step. situation: first | next | repeat | back."""
        current = self._steps[self._idx]
        return self._llm.procedure_step(
            current["step"], self._idx + 1, len(self._steps), situation, self._ctx
        )

    def _advance(self, task: str, status: str) -> tuple[str, bool]:
        self._status[self._idx] = status
        self._attempts = 0
        if self._idx + 1 >= len(self._steps):
            self._completed = True
            return (
                self._llm.procedure_summary(
                    task,
                    completed=self._count("done"),
                    total=len(self._steps),
                    not_done=[s["step"] for s, st in zip(self._steps, self._status) if st != "done"],
                    ctx=self._ctx,
                ),
                True,
            )
        self._idx += 1
        return self._present("next"), False

    def _help(self, task: str) -> tuple[str, bool]:
        self._attempts += 1
        if self._attempts >= self._config.max_attempts:
            self._log.warning(f"Max help attempts reached on step {self._idx + 1}; moving on.")
            return self._advance(task, "stuck")
        current = self._steps[self._idx]
        reply = self._llm.procedure_help_step(
            task, current["step"], self._history, self._attempts + 1, self._ctx
        )
        return reply, False

    def _count(self, status: str) -> int:
        return sum(1 for st in self._status if st == status)

    # ==== STATE ====

    def succeeded(self) -> bool:
        return self._completed and not self._user_cancelled

    def current_data(self) -> dict:
        return {
            "total_steps": len(self._steps),
            "current_step": self._idx + 1,
            "completed": self._count("done"),
            "skipped": self._count("skipped"),
            "results": [
                {"step": s["step"], "status": st}
                for s, st in zip(self._steps, self._status)
                if st is not None
            ],
        }

    def current_phase(self) -> str:
        if self._completed:
            return "done"
        return f"step_{self._idx + 1}_of_{len(self._steps)}"

    def turn_count(self) -> int:
        return self._turns
