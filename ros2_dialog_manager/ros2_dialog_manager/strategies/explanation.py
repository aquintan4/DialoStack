"""
ExplanationStrategy — explains a topic and verifies the user's understanding.

Flow:
    explain -> check_understanding -> understood     -> done (success)
                                   -> has_question   -> answer, loop
                                   -> not_understood -> rephrase (bounded)
"""

import logging
import time  # TRACE

from .base import BaseDialogStrategy, FSMConfig, register_strategy


@register_strategy("explanation")
class ExplanationStrategy(BaseDialogStrategy):

    def __init__(self, llm, config: FSMConfig, ctx, request=None):
        super().__init__(llm, config, ctx, request)
        self._attempts = 0
        self._completed = False
        self._history: list[dict] = []
        self._log = logging.getLogger("ExplanationStrategy")
        self._skip_intro: bool = bool(getattr(request, "skip_intro", False)) if request else False

    def on_init(self, task: str) -> str:
        if self._skip_intro:
            explanation = self._llm.generate_explanation_direct(task, self._ctx)
        else:
            explanation = self._llm.generate_explanation(task, self._ctx)
        check = self._llm.ask_understanding_check(task, self._ctx)
        opening = f"{explanation} {check}"
        self._history.append({"role": "assistant", "content": opening})
        # TRACE
        self._log.info(f"[TRACE] explanation_init_done | t={time.monotonic():.4f}")
        # /TRACE
        return opening

    def on_user_turn(self, task: str, user_text: str) -> tuple[str, bool]:
        cancel_result = self._cancel_pre_check(task, user_text, strict=False)
        if cancel_result is not None:
            return cancel_result

        self._history.append({"role": "user", "content": user_text})
        comprehension = self._llm.classify_understanding(user_text, self._history, self._ctx)

        if comprehension == "understood":
            self._completed = True
            # TRACE
            self._log.info(f"[TRACE] understanding_confirmed | t={time.monotonic():.4f}")
            # /TRACE
            reply = self._llm.understanding_confirmed_response(task, self._ctx)
            self._history.append({"role": "assistant", "content": reply})
            return reply, True

        if comprehension == "has_question":
            reply = self._llm.answer_explanation_question(user_text, task, self._history, self._ctx)
            self._history.append({"role": "assistant", "content": reply})
            return reply, False

        # not_understood
        self._attempts += 1
        if self._attempts >= self._config.max_attempts:
            self._log.warning("Max rephrase attempts reached; closing explanation.")
            return self._llm.explanation_max_attempts_response(task, self._ctx), True

        # TRACE
        self._log.info(f"[TRACE] rephrase attempt={self._attempts} | t={time.monotonic():.4f}")
        # /TRACE
        rephrased = self._llm.rephrase_explanation(
            task, self._history, attempt_number=self._attempts + 1, ctx=self._ctx
        )
        check = self._llm.ask_understanding_check(task, self._ctx)
        reply = f"{rephrased} {check}"
        self._history.append({"role": "assistant", "content": reply})
        return reply, False

    def succeeded(self) -> bool:
        return self._completed and not self._user_cancelled

    def current_data(self) -> dict:
        return {"attempts": self._attempts, "completed": self._completed}

    def current_phase(self) -> str:
        return "done" if self._completed else "explaining"

    def turn_count(self) -> int:
        return sum(1 for t in self._history if t["role"] == "user")
