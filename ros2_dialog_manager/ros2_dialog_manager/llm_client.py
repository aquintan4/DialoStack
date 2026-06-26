"""
LLMDialogClient — thin wrapper around the LLM inference action.

Owns two independent sessions (NLU for understanding, NLG for generation).
All structured-output calls retry on parse failure up to MAX_RETRIES.
NLG calls fall back to a safe Spanish phrase if the LLM is unavailable.
"""

import inspect  # TRACE
import json
import logging
import re
import time  # TRACE
from typing import Callable

from .dialog_context import DialogContext
from .dialog_frame import DialogFrame, _VALID_TYPES
from .prompt_builder import PromptBuilder
from .utils import local_cancel_check, parse_loose_json, to_snake_case

InferFn = Callable[[str, str, int | None, dict | None], str | None]

_MIN_NLG_CHARS = 3

# Last-resort fallback strings used only when the LLM is completely unavailable.
# Operators can extend this dict for additional languages.
_LANG_FALLBACKS: dict[str, dict[str, str]] = {
    "Spanish": {
        "opening": "Hola, ¿en qué puedo ayudarte?",
        "resume": "Continuamos donde lo dejamos.",
        "unclear": "¿Podrías repetirlo?",
        "confirm_q": "¿Es correcta esta información?",
        "good_question": "Buena pregunta.",
        "intent_response": "De acuerdo.",
        "explain_open": "Déjame explicarte esto.",
        "understand_check": "¿Lo has entendido?",
        "understand_ok": "¡Perfecto! Adelante.",
        "understand_fail": "No te preocupes, puedes preguntarme de nuevo cuando quieras.",
        "quiz_opening": "¡Empezamos el cuestionario!",
        "quiz_summary": "Cuestionario completado.",
        "cancel_ask": "¿Seguro que quieres cancelar?",
        "cancel_ok": "De acuerdo, cancelado.",
        "cancel_no": "Perfecto, continuamos.",
        "quiz_correct": "¡Correcto!",
        "quiz_wrong": "No, la respuesta era {expected}.",
        "timeout": "¿Sigues ahí?",
    },
    "English": {
        "opening": "Hello, how can I help you?",
        "resume": "Let's continue where we left off.",
        "unclear": "Could you repeat that?",
        "confirm_q": "Is this information correct?",
        "good_question": "Good question.",
        "intent_response": "Understood.",
        "explain_open": "Let me explain this.",
        "understand_check": "Did you understand?",
        "understand_ok": "Great, let's proceed.",
        "understand_fail": "No worries, feel free to ask me again.",
        "quiz_opening": "Let's start the quiz!",
        "quiz_summary": "Quiz completed.",
        "cancel_ask": "Are you sure you want to cancel?",
        "cancel_ok": "Alright, cancelled.",
        "cancel_no": "OK, let's continue.",
        "quiz_correct": "Correct!",
        "quiz_wrong": "No, the answer was {expected}.",
        "timeout": "Are you still there?",
    },
}

# Acknowledgment phrases injected by slot-filling after extracting a slot. Kept
# apart from _LANG_FALLBACKS because it is a LIST per language (the rest are
# single strings). Same language keys, so both switch with the `language` param.
_LANG_ACK_PHRASES: dict[str, tuple[str, ...]] = {
    "Spanish": ("Anotado.", "Hecho.", "Perfecto.", "Entendido.", "De acuerdo."),
    "English": ("Noted.", "Done.", "Got it.", "Understood.", "Alright."),
}


def default_ack_phrases(language: str) -> tuple[str, ...]:
    """Language-aware acknowledgment phrases, used when no explicit override."""
    return _LANG_ACK_PHRASES.get(language, _LANG_ACK_PHRASES["English"])


def default_timeout_prompt(language: str) -> str:
    """Language-aware "are you still there?" line, used when no explicit override."""
    return _LANG_FALLBACKS.get(language, _LANG_FALLBACKS["English"])["timeout"]


def default_phrases(language: str) -> dict[str, str]:
    """The full canned-phrase set for a language (the Strategies editor's defaults)."""
    return dict(_LANG_FALLBACKS.get(language, _LANG_FALLBACKS["English"]))


def phrase_languages() -> list[str]:
    """Languages that ship with a built-in phrase set."""
    return list(_LANG_FALLBACKS.keys())


class _ListOp:
    """Sentinel carrying a list operation produced by NLU coercion."""

    __slots__ = ("kind", "items")

    def __init__(self, kind: str, items: list[str]):
        self.kind = kind  # "add" | "remove" | "replace"
        self.items = items

    def __repr__(self) -> str:
        return f"_ListOp({self.kind}, {self.items!r})"


class LLMDialogClient:
    MAX_RETRIES = 2

    def __init__(
        self,
        nlu_session_id: str,
        nlg_session_id: str,
        infer_fn: InferFn,
        prompt_builder: PromptBuilder,
        language: str = "Spanish",
        history_max_turns: int = 200,
        phrase_overrides: dict[str, str] | None = None,
    ):
        self._nlu_sid = nlu_session_id
        self._nlg_sid = nlg_session_id
        self._infer = infer_fn
        self._pb = prompt_builder
        self._log = logging.getLogger("LLMDialogClient")
        # Language defaults, with operator overrides (from the Strategies editor)
        # layered on top so only the edited phrases change.
        base = _LANG_FALLBACKS.get(language, _LANG_FALLBACKS["English"])
        self._fb = {**base, **(phrase_overrides or {})}
        self._history_max_turns = history_max_turns

    @property
    def history_max_turns(self) -> int:
        return self._history_max_turns

    def _fb_fmt(self, key: str, **kwargs) -> str:
        """Return a fallback string, formatting any {placeholders} it contains."""
        return self._fb[key].format(**kwargs) if kwargs else self._fb[key]

    # ==== TASK LEVEL ====

    def classify_task_mode(self, task: str, ctx: DialogContext | None = None) -> str:
        prompt, schema = self._pb.classify_task_mode(task, ctx)
        raw = self._call_nlu(prompt, schema, max_tokens=50)
        if not raw:
            return "slot_filling"
        try:
            mode = parse_loose_json(raw).get("mode", "slot_filling")
            return mode if mode in ("slot_filling", "explanation") else "slot_filling"
        except Exception:
            return "slot_filling"

    def create_frame(self, task: str, ctx: DialogContext | None = None) -> DialogFrame | None:
        prompt, schema = self._pb.create_frame(task, ctx)
        for attempt in range(self.MAX_RETRIES):
            raw = self._call_nlu(prompt, schema, max_tokens=500)
            if not raw:
                continue
            try:
                data = parse_loose_json(raw)
                slots = data.get("slots", [])
                if not slots:
                    continue

                frame_schema: dict = {}
                types: dict = {}
                conditions: dict = {}
                canon_vals: dict = {}

                for s in slots:
                    if not isinstance(s, dict) or "name" not in s:
                        continue
                    name = to_snake_case(s["name"])
                    frame_schema[name] = None
                    t = s.get("type", "str")
                    types[name] = t if t in _VALID_TYPES else "str"
                    if "condition_slot" in s and "condition_value" in s:
                        conditions[name] = [
                            (to_snake_case(s["condition_slot"]), str(s["condition_value"]))
                        ]
                    if isinstance(s.get("canonical_values"), list):
                        canon_vals[name] = [str(v).lower().strip() for v in s["canonical_values"]]

                if not frame_schema:
                    continue

                return DialogFrame(
                    frame_schema,
                    types,
                    conditions=conditions or None,
                    canonical_values=canon_vals or None,
                    history_max_turns=self._history_max_turns,
                )
            except Exception as exc:
                self._log.warning(f"Frame parse error (attempt {attempt + 1}): {exc}")
        return None

    def audit_frame(self, frame: DialogFrame, task: str, ctx: DialogContext | None = None) -> int:
        """Second pass over the frame's canonical_values against resource context.
        Mutates frame in place. Best-effort — any failure is logged and ignored."""
        if ctx is None or not getattr(ctx, "resources", None):
            return 0

        schema_lines: list[str] = []
        for k in frame.all_keys():
            canon = frame.canonical_values(k)
            slot_type = frame.slot_type(k)
            if canon:
                schema_lines.append(f"  - {k} (type: {slot_type}): canonical_values = {canon}")
            elif slot_type in ("str", "list_str"):
                schema_lines.append(f"  - {k} (type: {slot_type}): canonical_values = []")
        if not schema_lines:
            return 0

        schema = "\n".join(schema_lines)
        prompt, json_schema = self._pb.audit_frame(task, schema, ctx)
        raw = self._call_nlu(prompt, json_schema, max_tokens=300)
        if not raw:
            return 0

        try:
            data = parse_loose_json(raw)
        except Exception as exc:
            self._log.warning(f"Schema-audit parse error: {exc}")
            return 0

        amend = getattr(frame, "amend_canonical_values", None)
        if amend is None:
            self._log.warning("DialogFrame missing amend_canonical_values; schema audit skipped.")
            return 0

        applied = 0
        for action in data.get("actions", []):
            slot = action.get("slot")
            kind = action.get("action")
            values = action.get("values", [])
            if not slot or not values or slot not in frame.all_keys():
                continue
            try:
                if kind == "add" and amend(slot, add=values):
                    applied += 1
                elif kind == "remove" and amend(slot, remove=values):
                    applied += 1
            except Exception as exc:
                self._log.warning(f"Schema audit action ignored ({exc}).")

        if applied:
            self._log.info(f"Schema audit applied {applied} canonical-value action(s).")
        return applied

    # ==== SLOT FILLING ====

    def get_opening(self, task: str, frame: DialogFrame, ctx: DialogContext | None = None) -> str:
        prompt = self._pb.opening(task, frame, ctx)
        res = self._call_nlg(prompt, max_tokens=100)
        return self._clean(res) or self._fb["opening"]

    def get_opening_direct(self, task: str, frame: DialogFrame, ctx: DialogContext | None = None) -> str:
        prompt = self._pb.opening_direct(task, frame, ctx)
        res = self._call_nlg(prompt, max_tokens=100)
        return self._clean(res) or self._fb["opening"]

    def get_resume_opening(
        self, task: str, frame: DialogFrame, next_slot: str | None, ctx: DialogContext | None = None
    ) -> str:
        prompt = self._pb.resume_opening(task, frame, next_slot, ctx)
        res = self._call_nlg(prompt, max_tokens=100)
        return self._clean(res) or self._fb["resume"]

    def extract_slots(
        self, user_text: str, frame: DialogFrame, ctx: DialogContext | None = None
    ) -> list[dict]:
        """Single-pass NLU during gathering. Detects new values and corrections."""
        prompt, schema = self._pb.extract_slots(user_text, frame, ctx)
        for attempt in range(self.MAX_RETRIES):
            raw = self._call_nlu(prompt, schema, max_tokens=300)
            if not raw:
                continue
            try:
                data = parse_loose_json(raw)
                return self._validate_extractions(data.get("extractions", []), frame)
            except Exception as exc:
                self._log.warning(f"Extraction parse error (attempt {attempt + 1}): {exc}")
        return []

    def generate_response(
        self,
        task: str,
        frame: DialogFrame,
        user_text: str,
        extracted_slots: list[dict],
        attempts_exceeded: list[str],
        ctx: DialogContext | None = None,
    ) -> str:
        prompt = self._pb.generate_response(
            task, frame, user_text, extracted_slots, attempts_exceeded, ctx
        )
        res = self._call_nlg(prompt, max_tokens=120)
        return self._clean(res) or self._fb["unclear"]

    def get_confirmation_question(
        self, task: str, frame: DialogFrame, ctx: DialogContext | None = None
    ) -> str:
        prompt = self._pb.ask_confirmation(task, frame, ctx)
        res = self._call_nlg(prompt, max_tokens=150)
        return self._clean(res) or self._fb["confirm_q"]

    def classify_intent(
        self, user_text: str, frame: DialogFrame, ctx: DialogContext | None = None
    ) -> tuple[str, dict]:
        """Confirming-phase intent classifier. Returns (intent, corrections)."""
        prompt, schema = self._pb.classify_intent(user_text, frame, ctx)
        for attempt in range(self.MAX_RETRIES):
            raw = self._call_nlu(prompt, schema, max_tokens=200)
            if not raw:
                continue
            try:
                data = parse_loose_json(raw)
                intent = data.get("intent", "unclear")
                if intent not in ("confirms", "corrects", "question", "unclear"):
                    intent = "unclear"

                corrs: dict = {}
                for slot, val in (data.get("corrections") or {}).items():
                    if val is None or slot not in frame.all_keys():
                        continue
                    coerced = self._coerce_value(val, frame.slot_type(slot))
                    if coerced is None:
                        continue
                    if isinstance(coerced, _ListOp):
                        items = self._enforce_canonical_list(slot, coerced.items, frame)
                        if not items and coerced.kind != "remove":
                            continue
                        corrs[slot] = {f"_{coerced.kind}": True, "items": items}
                    elif isinstance(coerced, list):
                        items = self._enforce_canonical_list(slot, coerced, frame)
                        if not items:
                            continue
                        corrs[slot] = items
                    else:
                        if not self._enforce_canonical_scalar(slot, coerced, frame):
                            continue
                        corrs[slot] = coerced

                return intent, corrs
            except Exception as exc:
                self._log.warning(f"Intent parse error (attempt {attempt + 1}): {exc}")
        return "unclear", {}

    def answer_confirmation_question(
        self, user_text: str, task: str, frame: DialogFrame, ctx: DialogContext | None = None
    ) -> str:
        prompt = self._pb.answer_confirmation_question(user_text, task, frame, ctx)
        res = self._call_nlg(prompt, max_tokens=80)
        return self._clean(res) or self._fb["good_question"]

    def response_to_intent(
        self,
        task: str,
        intent: str,
        corrections: dict,
        frame: DialogFrame,
        ctx: DialogContext | None = None,
    ) -> str:
        prompt = self._pb.response_to_intent(task, intent, corrections, frame, ctx)
        res = self._call_nlg(prompt, max_tokens=100)
        return self._clean(res) or self._fb["intent_response"]

    # ==== EXPLANATION ====

    def generate_explanation(self, task: str, ctx: DialogContext | None = None) -> str:
        prompt = self._pb.explanation_opening(task, ctx)
        res = self._call_nlg(prompt, max_tokens=300)
        return self._clean(res) or self._fb["explain_open"]

    def generate_explanation_direct(self, task: str, ctx: DialogContext | None = None) -> str:
        prompt = self._pb.explanation_opening_direct(task, ctx)
        res = self._call_nlg(prompt, max_tokens=300)
        return self._clean(res) or self._fb["explain_open"]

    def ask_understanding_check(self, task: str, ctx: DialogContext | None = None) -> str:
        prompt = self._pb.check_understanding(task, ctx)
        res = self._call_nlg(prompt, max_tokens=60)
        return self._clean(res) or self._fb["understand_check"]

    def classify_understanding(
        self, user_text: str, history: list[dict], ctx: DialogContext | None = None
    ) -> str:
        prompt, schema = self._pb.classify_understanding(user_text, history, ctx)
        for _ in range(self.MAX_RETRIES):
            raw = self._call_nlu(prompt, schema, max_tokens=60)
            if not raw:
                continue
            try:
                comp = parse_loose_json(raw).get("comprehension", "not_understood")
                return (
                    comp
                    if comp in ("understood", "has_question", "not_understood")
                    else "not_understood"
                )
            except Exception:
                continue
        return "not_understood"

    def answer_explanation_question(
        self, user_text: str, task: str, history: list[dict], ctx: DialogContext | None = None
    ) -> str:
        prompt = self._pb.answer_explanation_question(user_text, task, history, ctx)
        res = self._call_nlg(prompt, max_tokens=150)
        return self._clean(res) or self._fb["good_question"]

    def rephrase_explanation(
        self, task: str, history: list[dict], attempt_number: int, ctx: DialogContext | None = None
    ) -> str:
        prompt = self._pb.rephrase_explanation(task, history, attempt_number, ctx)
        res = self._call_nlg(prompt, max_tokens=300)
        return self._clean(res) or self._fb["explain_open"]

    def understanding_confirmed_response(self, task: str, ctx: DialogContext | None = None) -> str:
        prompt = self._pb.understanding_confirmed(task, ctx)
        res = self._call_nlg(prompt, max_tokens=80)
        return self._clean(res) or self._fb["understand_ok"]

    def explanation_max_attempts_response(self, task: str, ctx: DialogContext | None = None) -> str:
        prompt = self._pb.explanation_max_attempts(task, ctx)
        res = self._call_nlg(prompt, max_tokens=100)
        return self._clean(res) or self._fb["understand_fail"]

    # ==== QUIZ ====

    def quiz_opening(self, task: str, total: int) -> str:
        prompt = self._pb.quiz_opening(task, total)
        res = self._call_nlg(prompt, max_tokens=80)
        return self._clean(res) or self._fb["quiz_opening"]

    def evaluate_quiz_answer(self, question: str, expected: str, given: str) -> dict:
        """Returns {"correct": bool, "feedback": str}. Falls back to string match on LLM failure."""
        prompt, json_schema = self._pb.evaluate_quiz_answer(question, expected, given)
        raw = self._call_nlu(prompt, json_schema, max_tokens=120)
        if raw:
            try:
                data = parse_loose_json(raw)
                if isinstance(data, dict) and "correct" in data:
                    correct = bool(data["correct"])
                    feedback = str(data.get("feedback", "")).strip()
                    if not feedback:
                        feedback = (
                            self._fb["quiz_correct"]
                            if correct
                            else self._fb_fmt("quiz_wrong", expected=expected)
                        )
                    return {"correct": correct, "feedback": feedback}
            except Exception as exc:
                self._log.warning(f"Quiz evaluation parse error: {exc}")

        correct = expected.lower().strip() in given.lower().strip()
        fb = self._fb["quiz_correct"] if correct else self._fb_fmt("quiz_wrong", expected=expected)
        return {"correct": correct, "feedback": fb}

    def quiz_next_question(self, feedback: str, n: int, total: int, question: str) -> str:
        prompt = self._pb.quiz_next_question(feedback, n, total, question)
        res = self._call_nlg(prompt, max_tokens=100)
        return self._clean(res) or f"{feedback} {question}"

    def quiz_summary(self, task: str, correct: int, total: int, wrongs: list[str]) -> str:
        wrongs_str = "; ".join(wrongs) if wrongs else ""
        prompt = self._pb.quiz_summary(task, correct, total, wrongs_str)
        res = self._call_nlg(prompt, max_tokens=80)
        return self._clean(res) or self._fb["quiz_summary"]

    # ==== CANCEL FLOW ====

    def detect_cancel_intent(
        self, user_text: str, ctx: DialogContext | None = None, strict: bool = False
    ) -> bool:
        """Two-stage: local regex fast-path, then LLM fallback when ambiguous."""
        local = local_cancel_check(user_text, strict=strict)
        if local is not None:
            return local
        prompt, schema = self._pb.detect_cancel_intent(user_text, ctx, strict=strict)
        raw = self._call_nlu(prompt, schema, max_tokens=30)
        if not raw:
            return False
        try:
            return parse_loose_json(raw).get("cancel", False) is True
        except Exception:
            return False

    def detect_cancel_confirmation(self, user_text: str, ctx: DialogContext | None = None) -> bool:
        prompt, schema = self._pb.detect_cancel_confirmation(user_text, ctx)
        raw = self._call_nlu(prompt, schema, max_tokens=30)
        if not raw:
            return False
        try:
            return parse_loose_json(raw).get("confirmed", False) is True
        except Exception:
            return False

    def ask_cancel_confirmation(self, task: str, ctx: DialogContext | None = None) -> str:
        prompt = self._pb.ask_cancel_confirmation(task, ctx)
        res = self._call_nlg(prompt, max_tokens=60)
        return self._clean(res) or self._fb["cancel_ask"]

    def cancel_confirmed_response(
        self, task: str, frame: DialogFrame | None = None, ctx: DialogContext | None = None
    ) -> str:
        prompt = self._pb.cancel_confirmed_response(task, frame, ctx)
        res = self._call_nlg(prompt, max_tokens=60)
        return self._clean(res) or self._fb["cancel_ok"]

    def cancel_denied_response(
        self, task: str, frame: DialogFrame | None = None, ctx: DialogContext | None = None
    ) -> str:
        prompt = self._pb.cancel_denied_response(task, frame, ctx)
        res = self._call_nlg(prompt, max_tokens=80)
        return self._clean(res) or self._fb["cancel_no"]

    # ==== TRANSPORT ====

    def _call_nlu(self, prompt: str, schema: dict | None, max_tokens: int) -> str | None:
        # TRACE
        _op = inspect.currentframe().f_back.f_code.co_name
        _t = time.monotonic()
        self._log.info(f"[TRACE] nlu_start op={_op} max_tokens={max_tokens} | t={_t:.4f}")
        # /TRACE
        try:
            result = self._infer(self._nlu_sid, prompt, max_tokens, schema)
            # TRACE
            self._log.info(
                f"[TRACE] nlu_end op={_op} elapsed={time.monotonic()-_t:.3f}s | t={time.monotonic():.4f}"
            )
            # /TRACE
            return result
        except Exception as exc:
            self._log.error(f"NLU inference failed: {exc}")
            # TRACE
            self._log.info(f"[TRACE] nlu_error op={_op} | t={time.monotonic():.4f}")
            # /TRACE
            return None

    def _call_nlg(self, prompt: str, max_tokens: int) -> str | None:
        # TRACE
        _op = inspect.currentframe().f_back.f_code.co_name
        _t = time.monotonic()
        self._log.info(f"[TRACE] nlg_start op={_op} max_tokens={max_tokens} | t={_t:.4f}")
        # /TRACE
        for attempt in range(self.MAX_RETRIES):
            try:
                result = self._infer(self._nlg_sid, prompt, max_tokens, None)
                if result and len(result.strip()) >= _MIN_NLG_CHARS:
                    # TRACE
                    self._log.info(
                        f"[TRACE] nlg_end op={_op} elapsed={time.monotonic()-_t:.3f}s | t={time.monotonic():.4f}"
                    )
                    # /TRACE
                    return result
                if result is not None:
                    self._log.warning(
                        f"NLG response too short, retrying ({attempt + 1}/{self.MAX_RETRIES}): {result!r}"
                    )
            except Exception as exc:
                self._log.error(f"NLG inference failed ({attempt + 1}): {exc}")
        # TRACE
        self._log.info(
            f"[TRACE] nlg_failed op={_op} elapsed={time.monotonic()-_t:.3f}s | t={time.monotonic():.4f}"
        )
        # /TRACE
        return None

    # ==== COERCION ====

    _CONTENT_KEYS = ("value", "data", "content", "text", "result", "val")
    _METADATA_KEYS = frozenset({"type", "kind", "format", "source_span", "slot", "description"})

    @classmethod
    def _coerce_value(cls, val, slot_type: str):
        """Coerce raw NLU output to a typed value. For list_str, handles plain lists,
        comma-separated strings, and explicit list-operation payloads."""
        if slot_type != "list_str":
            return cls._coerce_primitive(val, slot_type)

        raw_obj = val
        if isinstance(val, str):
            stripped = val.strip()
            if stripped.startswith("{"):
                try:
                    raw_obj = parse_loose_json(stripped)
                except Exception:
                    pass
            elif stripped.startswith("["):
                try:
                    raw_obj = json.loads(stripped)
                except Exception:
                    pass

        if isinstance(raw_obj, dict):
            for kind in ("add", "remove", "replace"):
                if raw_obj.get(f"_{kind}") is True:
                    items = [
                        str(i).strip()
                        for i in raw_obj.get("items", [])
                        if i is not None and str(i).strip()
                    ]
                    return _ListOp(kind, items)

        if isinstance(raw_obj, list):
            items = [str(i).strip() for i in raw_obj if i is not None and str(i).strip()]
            return items if items else None

        if isinstance(val, str):
            parts = [p.strip() for p in re.split(r"[,;]+", val) if p.strip()]
            return parts if parts else None

        return None

    @classmethod
    def _coerce_primitive(cls, val, slot_type: str):
        if isinstance(val, (str, int, float, bool)):
            return val
        if isinstance(val, list):
            return cls._coerce_primitive(val[0], slot_type) if len(val) == 1 else None
        if not isinstance(val, dict):
            return None
        for key in cls._CONTENT_KEYS:
            if key in val:
                return cls._coerce_primitive(val[key], slot_type)
        candidates = {k: v for k, v in val.items() if k not in cls._METADATA_KEYS}
        if len(candidates) == 1:
            return cls._coerce_primitive(next(iter(candidates.values())), slot_type)
        return None

    def _validate_extractions(self, extractions: list, frame: DialogFrame) -> list[dict]:
        """Coerce, validate and enforce canonical values on each extraction."""
        valid: list[dict] = []
        for e in extractions:
            slot = e.get("slot", "")
            val = e.get("value")
            if slot not in frame.all_keys() or val is None:
                continue

            coerced = self._coerce_value(val, frame.slot_type(slot))
            if coerced is None:
                continue

            src = str(e.get("source_span", "")).strip()

            if isinstance(coerced, _ListOp):
                items = self._enforce_canonical_list(slot, coerced.items, frame)
                if not items and coerced.kind != "remove":
                    continue
                valid.append(
                    {"slot": slot, "value": items, "source_span": src, f"_{coerced.kind}": True}
                )
                continue

            if isinstance(coerced, list):
                items = self._enforce_canonical_list(slot, coerced, frame)
                if not items:
                    continue
                valid.append({"slot": slot, "value": items, "source_span": src})
                continue

            if not self._enforce_canonical_scalar(slot, coerced, frame):
                continue

            valid.append({"slot": slot, "value": coerced, "source_span": src})

        self._log.info(f"Validated extractions: {valid}")
        return valid

    @staticmethod
    def _enforce_canonical_list(slot: str, items: list, frame: DialogFrame) -> list[str]:
        canon = frame.canonical_values(slot)
        if not canon:
            return items
        canon_set = {c.lower() for c in canon}
        return [i for i in items if str(i).lower() in canon_set]

    @staticmethod
    def _enforce_canonical_scalar(slot: str, value: object, frame: DialogFrame) -> bool:
        canon = frame.canonical_values(slot)
        if not canon:
            return True
        return str(value).lower().strip() in {c.lower() for c in canon}

    @staticmethod
    def _clean(text) -> str | None:
        if not text:
            return None
        return str(text).strip().strip('"').strip("'") or None
