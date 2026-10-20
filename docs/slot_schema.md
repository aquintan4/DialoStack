# Slot Schema Reference

This document describes the slot schema accepted by the slot-filling strategy
through the `frame_schema_json` field of the `/dialog/execute_task` goal. See
[architecture.md](architecture.md) for how the `DialogFrame` fits into the
dialogue engine.

When `frame_schema_json` is empty, the LLM designs the schema from the task
description. When it is set, LLM generation is skipped and the schema is
validated before the dialogue starts: any structural error aborts the goal with
a descriptive message instead of failing mid-conversation.

The Frame Builder page of the GUI produces this same JSON, so everything below
can also be edited visually.

## Structure

```json
{
  "slots": [
    {"name": "drink", "type": "str", "canonical_values": ["coffee", "tea"]},
    {"name": "size",  "type": "str", "canonical_values": ["small", "large"]},
    {"name": "sugar_spoons", "type": "int", "minimum": 0, "maximum": 5},
    {"name": "age", "type": "int", "minimum": 0, "maximum": 120},
    {"name": "senior_discount", "type": "bool",
     "condition_slot": "age", "condition_minimum": 65}
  ]
}
```

The top-level object must contain a non-empty `slots` array. Slots are asked in
the order they appear, skipping those whose condition does not hold; a slot the
user has already failed to answer keeps priority until it is filled.

## Slot fields

| Field | Type | Applies to | Description |
| --- | --- | --- | --- |
| `name` | string | all | Required. Normalized to `snake_case`; names must be unique after normalization. |
| `type` | string | all | `str` (default), `int`, `float`, `bool` or `list_str`. |
| `canonical_values` | string[] | `str`, `list_str` | Closed set of allowed values (stored lowercase). Values outside the set are discarded. |
| `minimum` | number | `int`, `float` | Value must be `>=` this. |
| `exclusive_minimum` | number | `int`, `float` | Value must be `>` this. |
| `maximum` | number | `int`, `float` | Value must be `<=` this. |
| `exclusive_maximum` | number | `int`, `float` | Value must be `<` this. |
| `condition_slot` | string | all | Parent slot. The slot is only active when the condition on the parent holds. |
| `condition_value` | string | all | Equality condition: active when the parent equals this value. |
| `condition_minimum`, `condition_exclusive_minimum`, `condition_maximum`, `condition_exclusive_maximum` | number | all (parent must be `int`/`float`) | Range condition: active when the parent value falls within the range. |

`list_str` slots accumulate items across turns, and the user can add, remove or
replace items ("add milk", "remove the sugar", "actually only tea").

## Numeric bounds

Bounds restrict the values an `int` or `float` slot accepts. Each side is
optional, so they express "greater than", "less than" and "between":

```json
{"name": "age",         "type": "int",   "minimum": 18, "maximum": 99}
{"name": "temperature", "type": "float", "exclusive_minimum": 35, "maximum": 42}
{"name": "guests",      "type": "int",   "exclusive_minimum": 0}
```

At runtime, a value outside the range is **not stored**:

- **Gathering:** the value is rejected and counts as a failed attempt on the
  slot. The robot tells the user the allowed range and asks again
  ("It has to be between 18 and 99. How old are you?").
- **Confirming:** an out-of-range correction empties the slot (the old value
  was declared wrong by the user, the new one is invalid) and the dialogue
  returns to gathering to ask for it again.
- **`initial_frame_json`:** out-of-range seed values are ignored and logged.

The check is deterministic (`DialogFrame.try_update`). The LLM is only told the
range so it can extract the number and phrase the explanation.

## Conditions

A conditional slot becomes active only when its condition on `condition_slot`
holds. Each slot has at most one condition, of one of two kinds.

**Equality**, with `condition_value`. The comparison is case-insensitive; on an
`int`/`float` parent it compares numbers (`"0"` matches `0.0`):

```json
{"name": "detail", "type": "str", "condition_slot": "size", "condition_value": "large"}
```

**Range**, with the bound keys prefixed by `condition_`. Only for `int`/`float`
parents:

```json
{"name": "pension",  "type": "bool", "condition_slot": "age", "condition_minimum": 65}
{"name": "guardian", "type": "str",  "condition_slot": "age", "condition_exclusive_maximum": 18}
{"name": "school",   "type": "str",  "condition_slot": "age",
 "condition_minimum": 6, "condition_maximum": 12}
```

Runtime behavior:

- While the parent is empty, its conditional children are not asked.
- When the parent changes so that the condition stops holding, the child's
  value is cleared (e.g. age 70 to 30 clears `pension`). Changes that keep the
  condition true (70 to 80) preserve it.
- If the user gives a value for a child whose **equality** condition is not met
  yet, the parent is set to the required value automatically. **Range**
  conditions have no single parent value, so the parent is asked first.

## Validation errors

The schema is rejected before the dialogue starts when:

- the JSON is malformed, `slots` is missing or empty, or a slot is not an object;
- a `name` is empty or duplicated after `snake_case` normalization;
- a `type` is not one of the five valid types;
- `canonical_values` is not a list;
- bounds are set on a non-numeric slot, are not numbers (`"18"` and `true` are
  rejected), combine `minimum` with `exclusive_minimum` (or the two maximums),
  or describe an empty range (`minimum: 10, maximum: 5`);
- `condition_slot` appears without a test, a test appears without
  `condition_slot`, or `condition_value` is combined with a range condition;
- `condition_slot` references an unknown slot or a `list_str` slot;
- a range condition targets a non-numeric parent, is empty, or can never hold
  given the parent's own bounds (parent `maximum: 120`, condition
  `condition_exclusive_minimum: 120`);
- an equality condition on a numeric parent is not a number or lies outside the
  parent's bounds;
- `condition_value` is not among the parent's `canonical_values`.

## Prompt overrides

The rejection explanation relies on the `{rejected_summary}` placeholder of the
`generate_response` prompt. If you override that prompt (GUI prompt editor or a
custom `prompts.yaml`), keep `{rejected_summary}` and its rule, or the robot
will still reject out-of-range values but will not say why.
