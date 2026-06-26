"""
PromptBuilder — assembles prompts and JSON schemas from YAML templates.

Templates use Python str.format placeholders. Public methods return either
a str (NLG prompt) or a (str, dict) tuple (NLU prompt + output schema).

The `language` parameter (e.g. "Spanish", "English") is injected into every
template automatically, so templates can use {language} wherever needed.
"""

import logging  # TRACE
import time  # TRACE

from .dialog_context import DialogContext
from .dialog_frame import DialogFrame

_log = logging.getLogger("PromptBuilder")  # TRACE


class PromptBuilder:

    def __init__(self, templates: dict[str, str], language: str = "Spanish"):
        self._tpl = templates
        self._language = language

    def _t(self, key: str, **kwargs) -> str:
        """Render template `key`, always making {language} available."""
        return self._tpl[key].format(language=self._language, **kwargs)

    # ==== CONTEXT INJECTION ====

    @staticmethod
    def _inject(prompt: str, ctx: DialogContext | None) -> str:
        if not ctx:
            return prompt
        block = ctx.to_prompt_block()
        # TRACE
        if block:
            _emotion = ctx.current_user_state().emotion
            _log.info(
                f"[TRACE] context_injected resources={len(ctx.resources)} has_domain={bool(ctx.domain)} emotion={_emotion} | t={time.monotonic():.4f}"
            )
        # /TRACE
        return f"{block}\n{prompt}" if block else prompt

    # ==== TASK LEVEL ====

    def classify_task_mode(self, task: str, ctx: DialogContext | None = None) -> tuple[str, dict]:
        schema = {
            "type": "object",
            "properties": {"mode": {"type": "string", "enum": ["slot_filling", "explanation"]}},
            "required": ["mode"],
        }
        prompt = self._inject(self._t("classify_task_mode", task=task), ctx)
        return prompt, schema

    def create_frame(self, task: str, ctx: DialogContext | None = None) -> tuple[str, dict]:
        # No context injection: slot schema must derive from the task alone.
        schema = {
            "type": "object",
            "properties": {
                "slots": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["str", "int", "float", "bool", "list_str"],
                            },
                            "condition_slot": {"type": "string"},
                            "condition_value": {"type": "string"},
                            "canonical_values": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["name", "type"],
                    },
                }
            },
            "required": ["slots"],
        }
        prompt = self._t("create_frame", task=task)
        return prompt, schema

    def audit_frame(
        self, task: str, schema: str, ctx: DialogContext | None = None
    ) -> tuple[str, dict]:
        json_schema = {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slot": {"type": "string"},
                            "action": {"type": "string", "enum": ["add", "remove"]},
                            "values": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["slot", "action", "values"],
                    },
                }
            },
            "required": ["actions"],
        }
        prompt = self._t("audit_frame", task=task, schema=schema)
        return self._inject(prompt, ctx), json_schema

    # ==== SLOT FILLING ====

    def opening(self, task: str, frame: DialogFrame, ctx: DialogContext | None = None) -> str:
        # No context injection: avoids the opening reciting menu options unprompted.
        return self._t("opening", task=task, slots=frame.describe_slots())

    def opening_direct(self, task: str, frame: DialogFrame, ctx: DialogContext | None = None) -> str:
        # Context IS injected: opening_direct is for chained dialogs where the
        # patient/domain context is already established and the LLM needs it
        # (e.g. to use the patient's name without resorting to placeholders).
        return self._inject(self._t("opening_direct", task=task, slots=frame.describe_slots()), ctx)

    def resume_opening(
        self, task: str, frame: DialogFrame, next_slot: str | None, ctx: DialogContext | None = None
    ) -> str:
        filled = frame.filled_slots()
        known = "\n".join(f"  - {k}: {v!r}" for k, v in filled.items()) or "  (none)"
        prompt = self._t(
            "resume_opening", task=task, known_slots=known, next_slot=next_slot or "NONE"
        )
        return self._inject(prompt, ctx)

    def extract_slots(
        self, user_text: str, frame: DialogFrame, ctx: DialogContext | None = None
    ) -> tuple[str, dict]:
        """NLU pass for gathering: detects new values and corrections in a single call."""
        modifiable = frame.modifiable_slots()
        slot_defs = "\n".join(self._slot_def_line(k, frame) for k in modifiable)
        filled = frame.filled_slots()
        filled_ctx = ", ".join(f"{k}={v!r}" for k, v in filled.items()) if filled else "None"
        recent_ctx = self._fmt_history(frame.last_turns(2))
        prompt = self._t(
            "extract_slots",
            user_text=user_text,
            slot_defs=slot_defs,
            filled_ctx=filled_ctx,
            recent_context=recent_ctx,
        )
        return self._inject(prompt, ctx), frame.schema_for_extraction()

    def _slot_def_line(self, slot: str, frame: DialogFrame) -> str:
        slot_type = frame.slot_type(slot)
        line = f"  - {slot} (type: {slot_type})"
        if slot_type == "list_str":
            line += " [LIST — accumulates across turns; user may add, remove with _remove, or replace with _replace]"
        elif not frame.is_empty(slot):
            line += f" [ALREADY FILLED with {frame.current_value(slot)!r} — extract only if the user is explicitly correcting it]"
        else:
            line += " [empty — needs a value]"
        line += self._canonical_hint(slot, frame)
        return line

    @staticmethod
    def _canonical_hint(slot: str, frame: DialogFrame) -> str:
        canon = frame.canonical_values(slot)
        if not canon:
            return ""
        return f" [must be one of: {' | '.join(repr(v) for v in canon)}]"

    def generate_response(
        self,
        task: str,
        frame: DialogFrame,
        user_text: str,
        extracted_slots: list[dict],
        attempts_exceeded: list[str],
        ctx: DialogContext | None = None,
    ) -> str:
        history_text = self._fmt_history(frame.last_turns(10))
        next_slot = frame.next_slot() or "NONE"
        extracted_summary = (
            ", ".join(f"{e['slot']}={e['value']!r}" for e in extracted_slots) or "None"
        )
        prompt = self._t(
            "generate_response",
            task=task,
            slots=frame.describe_slots(),
            history=history_text,
            user_text=user_text,
            extracted_summary=extracted_summary,
            next_slot=next_slot,
            attempts_exceeded=str(attempts_exceeded),
        )
        return self._inject(prompt, ctx)

    def ask_confirmation(
        self, task: str, frame: DialogFrame, ctx: DialogContext | None = None
    ) -> str:
        prompt = self._t("ask_confirmation", task=task, slots=frame.describe_slots())
        return self._inject(prompt, ctx)

    def classify_intent(
        self, user_text: str, frame: DialogFrame, ctx: DialogContext | None = None
    ) -> tuple[str, dict]:
        prompt = self._t(
            "classify_intent", slots_summary=frame.describe_slots(), user_text=user_text
        )
        return self._inject(prompt, ctx), frame.schema_for_intent()

    def response_to_intent(
        self,
        task: str,
        intent: str,
        corrections: dict,
        frame: DialogFrame,
        ctx: DialogContext | None = None,
    ) -> str:
        history_text = self._fmt_history(frame.last_turns(6))
        corr_str = ", ".join(f"{k}={v!r}" for k, v in corrections.items()) or "None"
        prompt = self._t(
            "response_to_intent",
            task=task,
            intent=intent,
            corrections=corr_str,
            slots=frame.describe_slots(),
            history=history_text,
        )
        return self._inject(prompt, ctx)

    def answer_confirmation_question(
        self, user_text: str, task: str, frame: DialogFrame, ctx: DialogContext | None = None
    ) -> str:
        slots_summary = ", ".join(f"{k}={v!r}" for k, v in frame.filled_slots().items())
        prompt = self._t(
            "answer_confirmation_question",
            task=task,
            slots_summary=slots_summary,
            user_text=user_text,
        )
        return self._inject(prompt, ctx)

    # ==== QUIZ ====

    def quiz_opening(self, task: str, total: int) -> str:
        return self._t("quiz_opening", task=task, total=total)

    def evaluate_quiz_answer(self, question: str, expected: str, given: str) -> tuple[str, dict]:
        json_schema = {
            "type": "object",
            "properties": {
                "correct": {"type": "boolean"},
                "feedback": {"type": "string"},
            },
            "required": ["correct", "feedback"],
        }
        prompt = self._t("evaluate_quiz_answer", question=question, expected=expected, given=given)
        return prompt, json_schema

    def quiz_next_question(self, feedback: str, n: int, total: int, question: str) -> str:
        return self._t("quiz_next_question", feedback=feedback, n=n, total=total, question=question)

    def quiz_summary(self, task: str, correct: int, total: int, wrongs: str) -> str:
        return self._t(
            "quiz_summary", task=task, correct=correct, total=total, wrongs=wrongs or "(none)"
        )

    # ==== EXPLANATION ====

    def explanation_opening(self, task: str, ctx: DialogContext | None = None) -> str:
        return self._inject(self._t("explanation_opening", task=task), ctx)

    def explanation_opening_direct(self, task: str, ctx: DialogContext | None = None) -> str:
        return self._inject(self._t("explanation_opening_direct", task=task), ctx)

    def check_understanding(self, task: str, ctx: DialogContext | None = None) -> str:
        return self._inject(self._t("check_understanding", task=task), ctx)

    def classify_understanding(
        self, user_text: str, history: list[dict], ctx: DialogContext | None = None
    ) -> tuple[str, dict]:
        schema = {
            "type": "object",
            "properties": {
                "comprehension": {
                    "type": "string",
                    "enum": ["understood", "has_question", "not_understood"],
                }
            },
            "required": ["comprehension"],
        }
        prompt = self._t(
            "classify_understanding", history=self._fmt_history(history[-6:]), user_text=user_text
        )
        return self._inject(prompt, ctx), schema

    def answer_explanation_question(
        self, user_text: str, task: str, history: list[dict], ctx: DialogContext | None = None
    ) -> str:
        prompt = self._t(
            "answer_explanation_question",
            task=task,
            history=self._fmt_history(history[-6:]),
            user_text=user_text,
        )
        return self._inject(prompt, ctx)

    def rephrase_explanation(
        self, task: str, history: list[dict], attempt_number: int, ctx: DialogContext | None = None
    ) -> str:
        prompt = self._t(
            "rephrase_explanation",
            task=task,
            history=self._fmt_history(history[-8:]),
            attempt_number=attempt_number,
        )
        return self._inject(prompt, ctx)

    def understanding_confirmed(self, task: str, ctx: DialogContext | None = None) -> str:
        return self._inject(self._t("understanding_confirmed", task=task), ctx)

    def explanation_max_attempts(self, task: str, ctx: DialogContext | None = None) -> str:
        return self._inject(self._t("explanation_max_attempts", task=task), ctx)

    # ==== CANCEL FLOW ====

    def detect_cancel_intent(
        self, user_text: str, ctx: DialogContext | None = None, strict: bool = False
    ) -> tuple[str, dict]:
        # No context injection: cancel detection must be fast and unambiguous.
        schema = {
            "type": "object",
            "properties": {"cancel": {"type": "boolean"}},
            "required": ["cancel"],
        }
        prompt = self._t(
            "detect_cancel_intent", user_text=user_text, strict="true" if strict else "false"
        )
        return prompt, schema

    def detect_cancel_confirmation(
        self, user_text: str, ctx: DialogContext | None = None
    ) -> tuple[str, dict]:
        schema = {
            "type": "object",
            "properties": {"confirmed": {"type": "boolean"}},
            "required": ["confirmed"],
        }
        prompt = self._t("detect_cancel_confirmation", user_text=user_text)
        return prompt, schema

    def ask_cancel_confirmation(self, task: str, ctx: DialogContext | None = None) -> str:
        return self._inject(self._t("ask_cancel_confirmation", task=task), ctx)

    def cancel_confirmed_response(
        self, task: str, frame: DialogFrame | None = None, ctx: DialogContext | None = None
    ) -> str:
        return self._inject(self._t("cancel_confirmed_response", task=task), ctx)

    def cancel_denied_response(
        self, task: str, frame: DialogFrame | None = None, ctx: DialogContext | None = None
    ) -> str:
        if frame:
            filled = ", ".join(f"{k}={v!r}" for k, v in frame.filled_slots().items()) or "None"
            next_slot = frame.next_slot() or "NONE"
        else:
            filled = "None"
            next_slot = "NONE"
        prompt = self._t(
            "cancel_denied_response", task=task, filled_slots=filled, next_slot=next_slot
        )
        return self._inject(prompt, ctx)

    # ==== HELPERS ====

    @staticmethod
    def _fmt_history(turns: list[dict]) -> str:
        if not turns:
            return "  (empty)"
        return "\n".join(f"  {t['role'].capitalize()}: {t['content']}" for t in turns)
