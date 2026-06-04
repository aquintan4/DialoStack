"""
DialogFrame — mutable, thread-safe schema for slot-filling dialogs.

Slots are typed (str, int, float, bool, list_str) and may carry optional metadata:
  - canonical_values: closed set of allowed values (e.g. "small|medium|large").
  - conditions: a slot becomes active only when a parent slot equals a value.

list_str slots accumulate items by default and support explicit operations
(replace_list, remove_from_list, add_to_list) for natural corrections.

Note: list_str slots cannot be parents of conditional slots.
"""

import re
import threading
from typing import Any

from .utils import parse_loose_json, to_snake_case

_EMPTY_VALUES = frozenset({None, "none", "null", "", "unknown", "n/a"})
_VALID_TYPES = frozenset({"str", "int", "float", "bool", "list_str"})

# Default history buffer size; used as the constructor default and exported
# so tests can parameterise without hardcoding the magic number.
_MAX_HISTORY = 200


class DialogFrame:

    def __init__(
        self,
        schema: dict,
        types: dict,
        conditions: dict[str, list[tuple[str, str]]] | None = None,
        canonical_values: dict[str, list[str]] | None = None,
        history_max_turns: int = _MAX_HISTORY,
    ):
        self._lock = threading.RLock()
        self._keys = list(schema.keys())
        self._data = {k: None for k in schema}
        self._types = {k: (types.get(k, "str") if types else "str") for k in schema}
        self._conditions = conditions or {}
        self._canonical_values = canonical_values or {}
        self._attempts: dict[str, int] = {k: 0 for k in schema}
        self._history: list[dict] = []
        self._max_history = history_max_turns

    # ==== FACTORY ====

    @classmethod
    def from_typed_json(cls, raw: Any) -> "DialogFrame":
        """Build a frame from a JSON object whose values describe types."""
        data = parse_loose_json(raw)
        if not isinstance(data, dict):
            raise ValueError("Schema must be a JSON object")
        schema: dict = {}
        types: dict = {}
        for k, v in data.items():
            schema[k] = None
            if isinstance(v, dict) and "type" in v:
                t = v["type"]
                types[k] = t if t in _VALID_TYPES else "str"
            else:
                types[k] = cls._infer_type(v)
        return cls(schema, types)

    @classmethod
    def from_slots_json(
        cls,
        raw: Any,
        history_max_turns: int = _MAX_HISTORY,
    ) -> "DialogFrame":
        """
        Build a validated DialogFrame from a user-supplied slot schema.

        Accepts the same JSON format produced by LLMDialogClient.create_frame():
            {
              "slots": [
                {"name": "size",   "type": "str",
                 "canonical_values": ["small", "large"]},
                {"name": "detail", "type": "str",
                 "condition_slot": "size", "condition_value": "large"}
              ]
            }

        Slot names are normalised to snake_case (same as the LLM path).
        Raises ValueError with a descriptive message on any structural error so
        callers receive a clear explanation before the dialog starts.
        """
        try:
            data = parse_loose_json(raw)
        except (ValueError, Exception) as exc:
            raise ValueError(f"frame_schema_json is not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(
                "frame_schema_json must be a JSON object with a 'slots' key, "
                f"got {type(data).__name__}"
            )

        slots_raw = data.get("slots")
        if not isinstance(slots_raw, list):
            raise ValueError("frame_schema_json must contain a 'slots' key whose value is a list")
        if not slots_raw:
            raise ValueError("frame_schema_json 'slots' array must not be empty")

        schema: dict = {}
        types: dict = {}
        conditions: dict = {}
        canon_vals: dict = {}
        seen: set = set()

        for i, s in enumerate(slots_raw):
            if not isinstance(s, dict):
                raise ValueError(
                    f"Slot at index {i} must be a JSON object, " f"got {type(s).__name__}"
                )

            raw_name = s.get("name", "")
            if not raw_name or not isinstance(raw_name, str) or not raw_name.strip():
                raise ValueError(f"Slot at index {i}: 'name' must be a non-empty string")

            name = to_snake_case(raw_name.strip())
            if not name:
                raise ValueError(
                    f"Slot at index {i}: name '{raw_name}' produces an empty "
                    "identifier after normalisation"
                )
            if name in seen:
                raise ValueError(
                    f"Duplicate slot name after normalisation: '{name}' " f"(from '{raw_name}')"
                )
            seen.add(name)

            raw_type = s.get("type", "str")
            if raw_type not in _VALID_TYPES:
                raise ValueError(
                    f"Slot '{name}': invalid type '{raw_type}'. "
                    f"Valid types: {sorted(_VALID_TYPES)}"
                )

            schema[name] = None
            types[name] = raw_type

            # canonical_values
            raw_canon = s.get("canonical_values")
            if raw_canon is not None:
                if not isinstance(raw_canon, list):
                    raise ValueError(f"Slot '{name}': 'canonical_values' must be a list of strings")
                cleaned = [
                    str(v).lower().strip() for v in raw_canon if v is not None and str(v).strip()
                ]
                canon_vals[name] = cleaned

            # conditions — both keys must appear together or not at all
            has_cslot = "condition_slot" in s
            has_cval = "condition_value" in s
            if has_cslot != has_cval:
                raise ValueError(
                    f"Slot '{name}': 'condition_slot' and 'condition_value' must "
                    "both be present or both absent"
                )
            if has_cslot:
                cslot_raw = s["condition_slot"]
                cval_raw = s["condition_value"]
                if not cslot_raw or not str(cslot_raw).strip():
                    raise ValueError(f"Slot '{name}': 'condition_slot' must be a non-empty string")
                if cval_raw is None or not str(cval_raw).strip():
                    raise ValueError(f"Slot '{name}': 'condition_value' must be a non-empty string")
                cslot = to_snake_case(str(cslot_raw).strip())
                conditions[name] = [(cslot, str(cval_raw).strip())]

        # Second pass: validate cross-slot references now that all names are known.
        for child, conds in conditions.items():
            cslot, cval = conds[0]
            if cslot not in schema:
                raise ValueError(
                    f"Slot '{child}': condition_slot '{cslot}' does not reference "
                    "any slot defined in this schema"
                )
            if types.get(cslot) == "list_str":
                raise ValueError(f"Slot '{child}': cannot condition on list_str slot '{cslot}'")
            parent_canon = canon_vals.get(cslot)
            if parent_canon and cval.lower().strip() not in {v.lower() for v in parent_canon}:
                raise ValueError(
                    f"Slot '{child}': condition_value '{cval}' is not among "
                    f"'{cslot}' canonical_values {parent_canon}"
                )

        return cls(
            schema,
            types,
            conditions=conditions or None,
            canonical_values=canon_vals or None,
            history_max_turns=history_max_turns,
        )

    # ==== SCOPE ====

    def _in_scope(self, slot: str) -> bool:
        for cond_slot, cond_value in self._conditions.get(slot, []):
            actual = self._data.get(cond_slot)
            if actual is None or isinstance(actual, list):
                return False
            if str(actual).lower().strip() != str(cond_value).lower().strip():
                return False
        return True

    def trigger_values(self, slot: str) -> list[str]:
        """Values that, when set on this slot, activate one or more conditional children."""
        return list(
            dict.fromkeys(
                cv for _, conds in self._conditions.items() for cs, cv in conds if cs == slot
            )
        )

    # ==== LIST OPERATIONS ====

    def replace_list(self, slot: str, items: list) -> bool:
        """Overwrite a list_str slot wholesale. Returns True on success."""
        with self._lock:
            if not self._is_list_slot(slot):
                return False
            self._data[slot] = self._clean_items(items)
            return True

    def remove_from_list(self, slot: str, items_to_remove: list) -> bool:
        """Subtract items from a list_str slot (case-insensitive)."""
        with self._lock:
            if not self._is_list_slot(slot):
                return False
            current = self._current_list(slot)
            to_drop = {self._key(i) for i in items_to_remove if i is not None}
            self._data[slot] = [v for v in current if self._key(v) not in to_drop]
            return True

    def add_to_list(self, slot: str, items: list) -> bool:
        """Append new items to a list_str slot, skipping duplicates.
        Returns True only when at least one item was actually added."""
        with self._lock:
            if not self._is_list_slot(slot):
                return False
            current = self._current_list(slot)
            seen = {self._key(v) for v in current}
            additions = [i for i in self._clean_items(items) if self._key(i) not in seen]
            if additions:
                self._data[slot] = current + additions
                return True
            return False

    def _is_list_slot(self, slot: str) -> bool:
        return slot in self._data and self._types.get(slot) == "list_str"

    def _current_list(self, slot: str) -> list:
        v = self._data[slot]
        return v if isinstance(v, list) else []

    # ==== SCALAR UPDATES ====

    def try_update(self, data: dict) -> list[str]:
        """
        Apply a batch of value updates atomically. Returns the slots whose
        value actually changed. Conditional children are reset when their
        parent's value changes and the condition no longer holds.
        """
        if not isinstance(data, dict):
            return []

        updated: list[str] = []
        with self._lock:
            for k, v in data.items():
                if k not in self._data:
                    continue
                normalized = self._normalize(v, self._types[k])
                if normalized is None:
                    continue

                if self._types[k] == "list_str" and isinstance(normalized, list):
                    existing = self._current_list(k)
                    seen = {self._key(v) for v in existing}
                    new = [i for i in normalized if self._key(i) not in seen]
                    if new:
                        self._data[k] = existing + new
                        updated.append(k)
                    continue

                if self._data[k] != normalized:
                    old = self._data[k]
                    self._data[k] = normalized
                    updated.append(k)
                    self._reset_conditional_children(k, old, normalized)

        return updated

    def _reset_conditional_children(self, changed_slot: str, old_val: Any, new_val: Any) -> None:
        """Invalidate children whose condition no longer holds after a parent change."""
        for child, conds in self._conditions.items():
            for cond_slot, cond_value in conds:
                if cond_slot != changed_slot:
                    continue
                old_matched = self._scalar_equal(old_val, cond_value)
                new_matches = self._scalar_equal(new_val, cond_value)
                if old_matched and not new_matches:
                    self._data[child] = None
                    self._attempts[child] = 0

    @staticmethod
    def _scalar_equal(value: Any, target: str) -> bool:
        if value is None or isinstance(value, list):
            return False
        return str(value).lower().strip() == str(target).lower().strip()

    # ==== ATTEMPT TRACKING ====

    def increment_attempts(self, slot: str) -> int:
        with self._lock:
            self._attempts[slot] = self._attempts.get(slot, 0) + 1
            return self._attempts[slot]

    def attempts(self, slot: str) -> int:
        with self._lock:
            return self._attempts.get(slot, 0)

    def reset_attempts(self, slot: str) -> None:
        with self._lock:
            self._attempts[slot] = 0

    # ==== QUERIES ====

    def _is_empty(self, slot: str) -> bool:
        v = self._data[slot]
        if isinstance(v, list):
            return len(v) == 0
        return v in _EMPTY_VALUES

    def missing_slots(self) -> list[str]:
        with self._lock:
            return [k for k in self._keys if self._in_scope(k) and self._is_empty(k)]

    def filled_slots(self) -> dict:
        with self._lock:
            return {
                k: self._data[k] for k in self._keys if self._in_scope(k) and not self._is_empty(k)
            }

    def all_filled_slots(self) -> dict:
        """Filled slots regardless of scope — used for correction prompts."""
        with self._lock:
            return {k: self._data[k] for k in self._keys if not self._is_empty(k)}

    def available_slots(self) -> list[str]:
        """Slots eligible to receive values: in scope, and empty (or list_str which always accept more)."""
        with self._lock:
            return [
                k
                for k in self._keys
                if self._in_scope(k) and (self._is_empty(k) or self._types[k] == "list_str")
            ]

    def modifiable_slots(self) -> list[str]:
        """All in-scope slots the user may update — superset of available_slots, includes filled scalars
        so the LLM can detect mid-gathering corrections."""
        with self._lock:
            return [k for k in self._keys if self._in_scope(k)]

    def current_value(self, slot: str):
        with self._lock:
            return self._data.get(slot)

    def conditions_for(self, slot: str) -> list[tuple[str, object]]:
        with self._lock:
            return list(self._conditions.get(slot, []))

    def is_empty(self, slot: str) -> bool:
        with self._lock:
            return self._is_empty(slot)

    def next_slot(self) -> str | None:
        """The slot to ask next. Prioritises empty scalars over partially-filled list_str slots."""
        available = self.available_slots()
        if not available:
            return None
        with self._lock:
            empty = [k for k in available if self._is_empty(k)]
            candidates = empty if empty else available
            return max(candidates, key=lambda k: self._attempts.get(k, 0))

    def is_complete(self) -> bool:
        return len(self.missing_slots()) == 0

    def slot_type(self, slot: str) -> str:
        return self._types.get(slot, "str")

    def canonical_values(self, slot: str) -> list[str]:
        return list(self._canonical_values.get(slot, []))

    def amend_canonical_values(
        self,
        slot: str,
        add: list[str] | tuple[str, ...] = (),
        remove: list[str] | tuple[str, ...] = (),
    ) -> bool:
        """Mutate the canonical-values set of a slot. Used by the post-hoc schema audit.
        Allows creating a set from scratch when the slot has none yet.
        Removals that would empty the set are rejected. Returns True if anything changed."""
        with self._lock:
            if slot not in self._data:
                return False
            current = list(self._canonical_values.get(slot, []))
            before = set(current)
            for v in add:
                norm = str(v).lower().strip()
                if norm and norm not in current:
                    current.append(norm)
            if remove:
                to_drop = {str(v).lower().strip() for v in remove}
                trimmed = [v for v in current if v not in to_drop]
                if trimmed:
                    current = trimmed
            if set(current) == before:
                return False
            self._canonical_values[slot] = current
            return True

    def all_keys(self) -> list[str]:
        return list(self._keys)

    # ==== PRESENTATION ====

    def describe_slots(self) -> str:
        """Multi-line human-readable summary used inside prompts."""
        with self._lock:
            lines = []
            for k in self._keys:
                if not self._in_scope(k):
                    continue
                v = self._data[k]
                t = self._types[k]
                conds = self._conditions.get(k, [])
                cond_str = f" [active when {conds[0][0]}={conds[0][1]!r}]" if conds else ""
                val_str = f"= {v!r}" if not self._is_empty(k) else "MISSING"
                canon = self._canonical_values.get(k, [])
                canon_str = f" [one of: {' | '.join(repr(c) for c in canon)}]" if canon else ""
                lines.append(f"  - {k} ({t}): {val_str}{cond_str}{canon_str}")
            return "\n".join(lines) if lines else "  (no active slots)"

    def describe_filled_for_correction(self) -> str:
        """Compact summary of filled slots for correction-extraction prompts."""
        with self._lock:
            lines = []
            for k in self._keys:
                if self._is_empty(k):
                    continue
                v = self._data[k]
                canon = self._canonical_values.get(k, [])
                hint = f" [one of: {' | '.join(repr(c) for c in canon)}]" if canon else ""
                lines.append(f"  - {k} = {v!r}{hint}")
            return "\n".join(lines) if lines else "  (none)"

    # ==== HISTORY ====

    def add_turn(self, role: str, content: str) -> None:
        with self._lock:
            self._history.append({"role": role, "content": content})
            if len(self._history) > self._max_history:
                self._history = self._history[-(self._max_history // 2) :]

    def last_turns(self, n: int) -> list[dict]:
        with self._lock:
            return list(self._history[-n:])

    def history_to_text(self, limit: int = 10) -> str:
        with self._lock:
            recent = self._history[-limit:] if limit > 0 else list(self._history)
        return "\n".join(f"  {t['role']}: {t['content']}" for t in recent) or "  (empty)"

    def turn_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._history if t["role"] == "user")

    # ==== SERIALISATION ====

    def to_dict(self) -> dict:
        with self._lock:
            return {
                k: self._data[k] for k in self._keys if self._in_scope(k) and not self._is_empty(k)
            }

    # ==== JSON SCHEMAS FOR LLM STRUCTURED OUTPUT ====

    def schema_for_extraction(self) -> dict:
        """Schema for single-pass NLU extraction. Values may be plain strings,
        arrays, or explicit list operations ({_add|_remove|_replace, items})."""
        value = {
            "anyOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}},
                {
                    "type": "object",
                    "properties": {
                        "_add": {"type": "boolean"},
                        "_remove": {"type": "boolean"},
                        "_replace": {"type": "boolean"},
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                },
            ]
        }
        return {
            "type": "object",
            "properties": {
                "extractions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slot": {"type": "string", "enum": self._keys},
                            "value": value,
                            "source_span": {"type": "string"},
                        },
                        "required": ["slot", "value", "source_span"],
                    },
                }
            },
            "required": ["extractions"],
        }

    def schema_for_intent(self) -> dict:
        """Schema for the confirming-phase intent classifier."""
        operation = {
            "anyOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "properties": {
                        "_add": {"type": "boolean"},
                        "_remove": {"type": "boolean"},
                        "_replace": {"type": "boolean"},
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                },
            ]
        }
        return {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": ["confirms", "corrects", "question", "unclear"],
                },
                "corrections": {
                    "type": "object",
                    "properties": {k: operation for k in self._keys},
                },
            },
            "required": ["intent", "corrections"],
        }

    # ==== HELPERS ====

    @staticmethod
    def _key(value: Any) -> str:
        return str(value).lower().strip()

    @staticmethod
    def _clean_items(items: list) -> list[str]:
        return [str(i).strip() for i in items if i is not None and str(i).strip()]

    # Language-independent bool synonyms. Language-specific variants are handled
    # by the LLM during extraction; these are only a last-resort parsing fallback.
    _BOOL_TRUE = frozenset({"true", "yes", "1", "ok", "okay", "correct"})
    _BOOL_FALSE = frozenset({"false", "no", "0", "nope"})

    @staticmethod
    def _normalize(v: Any, slot_type: str) -> Any | None:
        if v is None:
            return None
        if isinstance(v, (dict, list)):
            if slot_type == "list_str" and isinstance(v, list):
                items = DialogFrame._clean_items(v)
                return items if items else None
            return None
        if isinstance(v, str) and v.lower().strip() in _EMPTY_VALUES:
            return None
        if slot_type == "list_str":
            s = str(v).strip()
            return [s] if s else None
        if slot_type == "bool":
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(v)
            if isinstance(v, str):
                low = v.lower().strip()
                if low in DialogFrame._BOOL_TRUE:
                    return True
                if low in DialogFrame._BOOL_FALSE:
                    return False
            return None
        if slot_type in ("int", "float"):
            try:
                return int(v) if slot_type == "int" else float(v)
            except (ValueError, TypeError):
                m = re.search(r"-?\d+\.?\d*", str(v))
                if m:
                    return int(m.group()) if slot_type == "int" else float(m.group())
            return None
        return str(v).strip() or None

    @staticmethod
    def _infer_type(v: Any) -> str:
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, int):
            return "int"
        if isinstance(v, float):
            return "float"
        return "str"
