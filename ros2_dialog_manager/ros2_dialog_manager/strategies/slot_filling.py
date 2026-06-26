"""
SlotFillingStrategy — collects structured data via a DialogFrame.

Phase flow:
    gathering -> confirming -> done (success)
              (user corrects during confirming) -> gathering

Resume capability: if the goal includes initial_frame_json, the frame is
seeded with those values and the opening is a resumption acknowledgement.
"""

import json
import logging
import time  # TRACE

from ..dialog_frame import DialogFrame
from .base import BaseDialogStrategy, FSMConfig, OpKind, Operation, register_strategy


@register_strategy("slot_filling")
class SlotFillingStrategy(BaseDialogStrategy):

    def __init__(self, llm, config: FSMConfig, ctx, request=None):
        super().__init__(llm, config, ctx, request)
        self._initial_json = (
            (getattr(request, "initial_frame_json", "") or "").strip() if request else ""
        )
        self._skip_intro: bool = bool(getattr(request, "skip_intro", False)) if request else False
        self._frame: DialogFrame | None = None
        self._phase = "gathering"
        self._confirmed = False
        self._consecutive_unclear = 0
        self._ack_idx = 0
        self._log = logging.getLogger("SlotFillingStrategy")

    # ==== LIFECYCLE ====

    def on_init(self, task: str) -> str:
        frame_schema_json = (getattr(self._request, "frame_schema_json", "") or "").strip()

        if frame_schema_json:
            # User supplied a pre-defined schema — build the frame directly and
            # skip LLM generation and audit entirely.
            self._frame = DialogFrame.from_slots_json(
                frame_schema_json,
                history_max_turns=self._llm.history_max_turns,
            )
            # TRACE
            self._log.info(
                f"[TRACE] frame_loaded_from_schema slots={len(self._frame.all_keys())} "
                f"| t={time.monotonic():.4f}"
            )
            # /TRACE
        else:
            self._frame = self._llm.create_frame(task, self._ctx)
            if not self._frame or not self._frame.all_keys():
                raise ValueError("Failed to create DialogFrame from LLM")
            # TRACE
            self._log.info(
                f"[TRACE] frame_created slots={len(self._frame.all_keys())} | t={time.monotonic():.4f}"
            )
            # /TRACE

            try:
                self._llm.audit_frame(self._frame, task, self._ctx)
            except Exception as exc:
                self._log.warning(f"Schema audit failed ({exc}); proceeding with original schema.")
            # TRACE
            self._log.info(f"[TRACE] frame_audited | t={time.monotonic():.4f}")
            # /TRACE

        seeded = self._seed_from_initial_json()

        if self._frame.is_complete():
            self._phase = "confirming"
            return self._llm.get_confirmation_question(task, self._frame, self._ctx)

        self._phase = "gathering"
        if seeded > 0:
            return self._llm.get_resume_opening(
                task, self._frame, self._frame.next_slot(), self._ctx
            )
        if self._skip_intro:
            return self._llm.get_opening_direct(task, self._frame, self._ctx)
        return self._llm.get_opening(task, self._frame, self._ctx)

    def _seed_from_initial_json(self) -> int:
        """Seed the frame with values from initial_frame_json. Returns slots seeded."""
        if not self._initial_json:
            return 0
        try:
            seed = json.loads(self._initial_json)
        except Exception as exc:
            self._log.warning(f"initial_frame_json is not valid JSON ({exc}); ignored.")
            return 0
        if not isinstance(seed, dict):
            self._log.warning("initial_frame_json must be a JSON object; ignored.")
            return 0

        known_slots = set(self._frame.all_keys())
        applicable, unknown = {}, []
        for key, value in seed.items():
            if key in known_slots:
                applicable[key] = value
            else:
                unknown.append(key)

        if unknown:
            self._log.info(
                f"initial_frame_json: {len(unknown)} unknown slot(s) ignored ({', '.join(unknown)})."
            )
        if not applicable:
            return 0

        self._frame.try_update(applicable)
        seeded = sum(1 for k in applicable if not self._frame.is_empty(k))
        if seeded:
            self._log.info(f"Resumed with {seeded}/{len(applicable)} slot(s) pre-filled.")
        return seeded

    def on_user_turn(self, task: str, user_text: str) -> tuple[str, bool]:
        next_slot = self._frame.next_slot() if self._frame else None
        is_choice = bool(next_slot and self._frame.canonical_values(next_slot))

        cancel_result = self._cancel_pre_check(task, user_text, strict=is_choice)
        if cancel_result is not None:
            return cancel_result

        self._frame.add_turn("user", user_text)

        if self._phase == "gathering":
            return self._handle_gathering(task, user_text)
        return self._handle_confirming(task, user_text)

    # ==== PHASE HANDLERS ====

    def _pop_ack(self) -> str:
        phrases = self._config.ack_phrases
        if not phrases:
            return ""
        phrase = phrases[self._ack_idx % len(phrases)]
        self._ack_idx += 1
        return phrase

    def _handle_gathering(self, task: str, user_text: str) -> tuple[str, bool]:
        slot_asked = self._frame.next_slot()
        extractions = self._llm.extract_slots(user_text, self._frame, self._ctx)

        operations = self._extractions_to_operations(extractions, default_list_op=OpKind.ADD)
        applied = self._apply_operations(operations)

        extracted_keys = {op.slot for op in operations}
        if slot_asked is not None and slot_asked not in extracted_keys:
            self._frame.increment_attempts(slot_asked)

        # Acknowledgment is injected by Python (not the LLM) to guarantee variety
        # and prevent the LLM from saying "Anotado." when nothing was extracted.
        ack = self._pop_ack() if applied > 0 else ""

        if self._frame.is_complete():
            self._phase = "confirming"
            # TRACE
            self._log.info(
                f"[TRACE] phase_transition gathering→confirming | t={time.monotonic():.4f}"
            )
            # /TRACE
            question = self._llm.get_confirmation_question(task, self._frame, self._ctx)
            reply = f"{ack} {question}".strip() if ack else question
            self._frame.add_turn("assistant", reply)
            return reply, False

        next_q = self._llm.generate_response(
            task=task,
            user_text=user_text,
            frame=self._frame,
            extracted_slots=extractions,
            attempts_exceeded=self._slots_over_attempts(),
            ctx=self._ctx,
        )
        reply = f"{ack} {next_q}".strip() if ack else next_q
        self._frame.add_turn("assistant", reply)
        return reply, False

    def _handle_confirming(self, task: str, user_text: str) -> tuple[str, bool]:
        intent, corrections = self._llm.classify_intent(user_text, self._frame, self._ctx)
        corrections = corrections or {}

        if intent == "confirms":
            self._confirmed = True
            # TRACE
            self._log.info(f"[TRACE] dialog_confirmed | t={time.monotonic():.4f}")
            # /TRACE
            reply = self._llm.response_to_intent(
                task=task,
                intent="confirms",
                corrections={},
                frame=self._frame,
                ctx=self._ctx,
            )
            return reply, True

        if intent == "question":
            self._consecutive_unclear = 0
            return (
                self._llm.answer_confirmation_question(
                    user_text,
                    task,
                    self._frame,
                    self._ctx,
                ),
                False,
            )

        if intent == "corrects":
            operations = self._extractions_to_operations(
                self._normalize_corrections_to_extractions(corrections),
                default_list_op=OpKind.ADD,
            )
            applied = self._apply_operations(operations)

            if not self._frame.is_complete():
                # Real correction opened a missing slot — go back to gathering.
                self._consecutive_unclear = 0
                self._phase = "gathering"
                # TRACE
                self._log.info(
                    f"[TRACE] phase_transition confirming→gathering | t={time.monotonic():.4f}"
                )
                # /TRACE
                applied_extractions = [{"slot": op.slot, "value": op.value} for op in operations]
                next_q = self._llm.generate_response(
                    task=task,
                    user_text=user_text,
                    frame=self._frame,
                    extracted_slots=applied_extractions,
                    attempts_exceeded=self._slots_over_attempts(),
                    ctx=self._ctx,
                )
                self._frame.add_turn("assistant", next_q)
                return next_q, False

            if applied > 0:
                # Real corrections applied and frame is still complete — re-confirm.
                self._consecutive_unclear = 0
                reply = self._llm.response_to_intent(
                    task=task,
                    intent="corrects",
                    corrections=corrections,
                    frame=self._frame,
                    ctx=self._ctx,
                )
                self._frame.add_turn("assistant", reply)
                return reply, False

            # applied == 0: LLM said "corrects" but nothing actually changed.
            # The user is almost certainly affirming, not correcting.  Treat this
            # the same as an unclear response so the unclear counter escalates.

        # unclear (or corrects with no actual change)
        self._consecutive_unclear += 1
        if self._consecutive_unclear >= self._config.max_unclear:
            self._log.warning(f"Reached max_unclear={self._config.max_unclear}; closing.")
            return (
                self._llm.response_to_intent(
                    task=task,
                    intent="unclear",
                    corrections={},
                    frame=self._frame,
                    ctx=self._ctx,
                ),
                True,
            )
        # Re-anchor the user to the yes/no confirmation question instead of
        # generating an open-ended question that derails the flow.
        question = self._llm.get_confirmation_question(task, self._frame, self._ctx)
        self._frame.add_turn("assistant", question)
        return question, False

    # ==== OPERATIONS ====

    def _extractions_to_operations(
        self, extractions: list[dict], default_list_op: OpKind
    ) -> list[Operation]:
        """Convert validated extractions (with _add/_remove/_replace sentinels) to Operation objects."""
        ops: list[Operation] = []
        for extraction in extractions:
            slot = extraction.get("slot")
            value = extraction.get("value")
            if not slot or value is None:
                continue
            if self._frame.slot_type(slot) != "list_str":
                ops.append(Operation(slot, OpKind.SET, value))
                continue
            if extraction.get("_remove"):
                ops.append(Operation(slot, OpKind.REMOVE, value))
            elif extraction.get("_replace"):
                ops.append(Operation(slot, OpKind.REPLACE, value))
            elif extraction.get("_add"):
                ops.append(Operation(slot, OpKind.ADD, value))
            else:
                ops.append(Operation(slot, default_list_op, value))
        return ops

    def _apply_operations(self, operations: list[Operation]) -> int:
        """
        Apply operations in three stages:
          1. Auto-promote conditional parents when a child op targets a slot whose
             parent condition is not yet met — prevents the frame silently dropping
             child corrections because the parent isn't in scope.
          2. Batch all scalar SETs into a single try_update for atomic child reset.
          3. Apply list operations in order (REMOVE before ADD matters).
        """
        if not operations or not self._frame:
            return 0

        promoted: dict = {}
        for op in operations:
            conds = self._frame.conditions_for(op.slot)
            if not conds:
                continue
            parent_slot, required_value = conds[0]
            if self._frame.current_value(parent_slot) == required_value:
                continue
            if any(o.slot == parent_slot for o in operations):
                continue
            promoted[parent_slot] = required_value

        applied = 0

        scalar_updates: dict = dict(promoted)
        for op in operations:
            if op.kind == OpKind.SET:
                scalar_updates[op.slot] = op.value
        if scalar_updates:
            changed = self._frame.try_update(scalar_updates)
            applied += len(changed)
            if promoted:
                self._log.info(f"Auto-promoted parent(s) {list(promoted.keys())}.")

        for op in operations:
            if op.kind == OpKind.SET:
                continue
            items = op.value if isinstance(op.value, list) else [op.value]
            if op.kind == OpKind.ADD:
                if self._frame.add_to_list(op.slot, items):
                    applied += 1
            elif op.kind == OpKind.REMOVE:
                if self._frame.remove_from_list(op.slot, items):
                    applied += 1
            elif op.kind == OpKind.REPLACE:
                if self._frame.replace_list(op.slot, items):
                    applied += 1
        return applied

    def _slots_over_attempts(self) -> list[str]:
        if self._frame is None:
            return []
        threshold = self._config.max_attempts
        return [s for s in self._frame.available_slots() if self._frame.attempts(s) >= threshold]

    def _normalize_corrections_to_extractions(self, corrections: dict) -> list[dict]:
        """Bridge classify_intent output format to the extraction format for _apply_operations."""
        extractions: list[dict] = []
        for slot, val in corrections.items():
            ex: dict = {"slot": slot, "value": val}
            if isinstance(val, dict):
                if val.get("_remove"):
                    ex["value"] = val.get("items", [])
                    ex["_remove"] = True
                elif val.get("_replace"):
                    ex["value"] = val.get("items", [])
                    ex["_replace"] = True
                elif val.get("_add"):
                    ex["value"] = val.get("items", [])
                    ex["_add"] = True
            extractions.append(ex)
        return extractions

    # ==== ACCESSORS ====

    def succeeded(self) -> bool:
        return self._confirmed and not self._user_cancelled

    def current_data(self) -> dict:
        return self._frame.to_dict() if self._frame else {}

    def current_phase(self) -> str:
        return self._phase

    def turn_count(self) -> int:
        return self._frame.turn_count() if self._frame else 0

    def _frame_or_none(self) -> DialogFrame | None:
        return self._frame
