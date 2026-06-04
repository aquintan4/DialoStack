"""Unit tests for DialogFrame: schema, type normalisation, conditional slots,
list operations, history, and JSON construction from slot definitions."""

import threading

import pytest

from ros2_dialog_manager.dialog_frame import DialogFrame, _MAX_HISTORY

# ==== HELPERS ====


def simple_frame():
    return DialogFrame(
        {"nombre": None, "edad": None},
        {"nombre": "str", "edad": "int"},
    )


def conditional_frame():
    return DialogFrame(
        {"tipo": None, "detalle_a": None, "detalle_b": None},
        {"tipo": "str", "detalle_a": "str", "detalle_b": "str"},
        conditions={
            "detalle_a": [("tipo", "A")],
            "detalle_b": [("tipo", "B")],
        },
    )


def list_frame():
    return DialogFrame({"items": None}, {"items": "list_str"})


def canon_frame():
    return DialogFrame(
        {"size": None},
        {"size": "str"},
        canonical_values={"size": ["small", "medium", "large"]},
    )


# ==== BASIC SCHEMA ====


def test_all_keys():
    assert set(simple_frame().all_keys()) == {"nombre", "edad"}


def test_new_frame_not_complete():
    assert not simple_frame().is_complete()


def test_frame_complete_after_fill():
    f = simple_frame()
    f.try_update({"nombre": "Ana", "edad": 30})
    assert f.is_complete()


def test_missing_slots_all():
    assert set(simple_frame().missing_slots()) == {"nombre", "edad"}


def test_missing_slots_partial():
    f = simple_frame()
    f.try_update({"nombre": "Ana"})
    assert f.missing_slots() == ["edad"]


def test_filled_slots():
    f = simple_frame()
    f.try_update({"nombre": "Ana", "edad": 25})
    assert f.filled_slots() == {"nombre": "Ana", "edad": 25}


def test_to_dict_empty():
    assert simple_frame().to_dict() == {}


def test_to_dict_filled():
    f = simple_frame()
    f.try_update({"nombre": "Ana", "edad": 30})
    assert f.to_dict() == {"nombre": "Ana", "edad": 30}


# ==== TYPE NORMALISATION ====


def test_int_from_string():
    f = simple_frame()
    f.try_update({"edad": "30"})
    assert f.current_value("edad") == 30


def test_int_extracted_from_text():
    f = simple_frame()
    f.try_update({"edad": "tengo 25 años"})
    assert f.current_value("edad") == 25


def test_float_coercion():
    f = DialogFrame({"precio": None}, {"precio": "float"})
    f.try_update({"precio": "3.5"})
    assert f.current_value("precio") == pytest.approx(3.5)


def test_empty_sentinel_values_rejected():
    f = simple_frame()
    for v in ("none", "null", "", "unknown", "n/a", None):
        f.try_update({"nombre": v})
        assert f.current_value("nombre") is None


def test_bool_true_variants():
    f = DialogFrame({"activo": None}, {"activo": "bool"})
    for v in ("true", "yes", "1", "ok", "okay", "correct"):
        f.try_update({"activo": None})  # reset
        f._data["activo"] = None
        f.try_update({"activo": v})
        assert f.current_value("activo") is True, f"Expected True for {v!r}"


def test_bool_false_variants():
    f = DialogFrame({"activo": None}, {"activo": "bool"})
    for v in ("no", "false", "0", "nope"):
        f._data["activo"] = None
        f.try_update({"activo": v})
        assert f.current_value("activo") is False, f"Expected False for {v!r}"


# ==== CONDITIONAL SLOTS ====


def test_conditional_hidden_before_parent():
    f = conditional_frame()
    available = f.available_slots()
    assert "tipo" in available
    assert "detalle_a" not in available
    assert "detalle_b" not in available


def test_conditional_visible_when_parent_matches():
    f = conditional_frame()
    f.try_update({"tipo": "A"})
    assert "detalle_a" in f.available_slots()
    assert "detalle_b" not in f.available_slots()


def test_conditional_resets_when_parent_changes():
    f = conditional_frame()
    f.try_update({"tipo": "A"})
    f.try_update({"detalle_a": "something"})
    assert f.current_value("detalle_a") == "something"
    f.try_update({"tipo": "B"})
    assert f.current_value("detalle_a") is None


def test_attempts_reset_on_conditional_parent_change():
    f = conditional_frame()
    f.try_update({"tipo": "A"})
    f.increment_attempts("detalle_a")
    f.increment_attempts("detalle_a")
    f.try_update({"tipo": "B"})
    assert f.attempts("detalle_a") == 0


def test_complete_with_conditional_out_of_scope():
    f = conditional_frame()
    # detalle_b is out of scope when tipo=A
    f.try_update({"tipo": "A", "detalle_a": "x"})
    assert f.is_complete()


def test_incomplete_with_conditional_in_scope():
    f = conditional_frame()
    f.try_update({"tipo": "A"})
    assert not f.is_complete()


# ==== LIST_STR OPERATIONS ====


def test_list_add():
    f = list_frame()
    f.add_to_list("items", ["a", "b"])
    assert f.current_value("items") == ["a", "b"]


def test_list_add_dedup():
    f = list_frame()
    f.add_to_list("items", ["a", "b"])
    f.add_to_list("items", ["b", "c"])
    assert f.current_value("items") == ["a", "b", "c"]


def test_list_remove():
    f = list_frame()
    f.add_to_list("items", ["a", "b", "c"])
    f.remove_from_list("items", ["b"])
    assert f.current_value("items") == ["a", "c"]


def test_list_remove_case_insensitive():
    f = list_frame()
    f.add_to_list("items", ["Pizza", "Pasta"])
    f.remove_from_list("items", ["pizza"])
    assert f.current_value("items") == ["Pasta"]


def test_list_replace():
    f = list_frame()
    f.add_to_list("items", ["a", "b"])
    f.replace_list("items", ["x", "y"])
    assert f.current_value("items") == ["x", "y"]


def test_list_empty_is_not_complete():
    assert not list_frame().is_complete()


def test_list_complete_when_has_items():
    f = list_frame()
    f.add_to_list("items", ["a"])
    assert f.is_complete()


def test_list_via_try_update_appends():
    f = list_frame()
    f.try_update({"items": ["x", "y"]})
    f.try_update({"items": ["z"]})
    val = f.current_value("items")
    assert "x" in val and "z" in val


# ==== CANONICAL VALUES ====


def test_canonical_values_returned():
    assert canon_frame().canonical_values("size") == ["small", "medium", "large"]


def test_canonical_values_missing_slot():
    assert simple_frame().canonical_values("nombre") == []


# ==== ATTEMPT TRACKING ====


def test_attempts_increment():
    f = simple_frame()
    f.increment_attempts("nombre")
    f.increment_attempts("nombre")
    assert f.attempts("nombre") == 2


def test_attempts_start_at_zero():
    assert simple_frame().attempts("nombre") == 0


def test_reset_attempts():
    f = simple_frame()
    f.increment_attempts("nombre")
    f.reset_attempts("nombre")
    assert f.attempts("nombre") == 0


# ==== HISTORY ====


def test_history_records_turns():
    f = simple_frame()
    f.add_turn("user", "Hola")
    f.add_turn("assistant", "¿En qué puedo ayudarte?")
    turns = f.last_turns(10)
    assert len(turns) == 2
    assert turns[0] == {"role": "user", "content": "Hola"}


def test_last_turns_respects_limit():
    f = simple_frame()
    for i in range(20):
        f.add_turn("user", f"msg {i}")
    assert len(f.last_turns(5)) == 5


def test_turn_count_only_user():
    f = simple_frame()
    f.add_turn("user", "a")
    f.add_turn("assistant", "b")
    f.add_turn("user", "c")
    assert f.turn_count() == 2


def test_history_cap_trims_oldest():
    f = simple_frame()
    for i in range(_MAX_HISTORY + 10):
        f.add_turn("user", f"msg {i}")
    # Trim fires when limit is exceeded, cutting to half. Subsequent adds bring
    # the size back up, but it never exceeds _MAX_HISTORY again.
    assert len(f._history) <= _MAX_HISTORY
    # The oldest messages should be gone; only recent ones remain.
    contents = [t["content"] for t in f._history]
    assert "msg 0" not in contents


# ==== NEXT SLOT ====


def test_next_slot_returns_a_slot():
    f = simple_frame()
    assert f.next_slot() in {"nombre", "edad"}


def test_next_slot_none_when_complete():
    f = simple_frame()
    f.try_update({"nombre": "Ana", "edad": 30})
    assert f.next_slot() is None


# ==== DESCRIBE SLOTS ====


def test_describe_slots_filled_shows_value():
    f = simple_frame()
    f.try_update({"nombre": "Ana"})
    desc = f.describe_slots()
    assert "Ana" in desc


def test_describe_slots_missing_shows_missing():
    desc = simple_frame().describe_slots()
    assert "MISSING" in desc


# ==== JSON SCHEMAS ====


def test_schema_for_extraction_structure():
    schema = simple_frame().schema_for_extraction()
    assert schema["type"] == "object"
    props = schema["properties"]
    assert "extractions" in props
    items = props["extractions"]["items"]
    required = items["required"]
    assert "slot" in required and "value" in required


def test_schema_for_intent_structure():
    schema = simple_frame().schema_for_intent()
    assert "intent" in schema["properties"]
    assert "corrections" in schema["properties"]
    intent_enum = schema["properties"]["intent"]["enum"]
    assert "confirms" in intent_enum
    assert "corrects" in intent_enum


# ==== THREAD SAFETY ====


def test_concurrent_try_update():
    f = DialogFrame(
        {f"slot_{i}": None for i in range(20)},
        {f"slot_{i}": "str" for i in range(20)},
    )
    errors = []

    def writer(i):
        try:
            for _ in range(50):
                f.try_update({f"slot_{i % 20}": f"val_{i}"})
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_concurrent_add_to_list():
    f = DialogFrame({"items": None}, {"items": "list_str"})
    errors = []

    def adder(i):
        try:
            for _ in range(20):
                f.add_to_list("items", [f"item_{i}"])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=adder, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


# ==== FROM_TYPED_JSON ====


def test_from_typed_json_basic():
    raw = '{"name": {"type": "str"}, "age": {"type": "int"}}'
    f = DialogFrame.from_typed_json(raw)
    assert set(f.all_keys()) == {"name", "age"}
    assert f.slot_type("age") == "int"


def test_from_typed_json_not_object_raises():
    with pytest.raises(ValueError):
        DialogFrame.from_typed_json("[1, 2, 3]")


# ==== FROM_SLOTS_JSON: VALID INPUTS ====


def test_from_slots_json_basic():
    raw = '{"slots": [{"name": "nombre", "type": "str"}, {"name": "edad", "type": "int"}]}'
    f = DialogFrame.from_slots_json(raw)
    assert set(f.all_keys()) == {"nombre", "edad"}
    assert f.slot_type("nombre") == "str"
    assert f.slot_type("edad") == "int"


def test_from_slots_json_all_scalar_types():
    raw = """{
        "slots": [
            {"name": "a", "type": "str"},
            {"name": "b", "type": "int"},
            {"name": "c", "type": "float"},
            {"name": "d", "type": "bool"}
        ]
    }"""
    f = DialogFrame.from_slots_json(raw)
    assert f.slot_type("a") == "str"
    assert f.slot_type("b") == "int"
    assert f.slot_type("c") == "float"
    assert f.slot_type("d") == "bool"


def test_from_slots_json_list_str_type():
    raw = '{"slots": [{"name": "items", "type": "list_str"}]}'
    f = DialogFrame.from_slots_json(raw)
    assert f.slot_type("items") == "list_str"


def test_from_slots_json_with_canonical_values():
    raw = """{
        "slots": [
            {"name": "size", "type": "str",
             "canonical_values": ["small", "medium", "large"]}
        ]
    }"""
    f = DialogFrame.from_slots_json(raw)
    assert f.canonical_values("size") == ["small", "medium", "large"]


def test_from_slots_json_canonical_values_lowercased():
    raw = '{"slots": [{"name": "color", "type": "str", "canonical_values": ["Red", "BLUE"]}]}'
    f = DialogFrame.from_slots_json(raw)
    assert f.canonical_values("color") == ["red", "blue"]


def test_from_slots_json_with_condition():
    raw = """{
        "slots": [
            {"name": "tipo",   "type": "str",
             "canonical_values": ["a", "b"]},
            {"name": "detalle", "type": "str",
             "condition_slot": "tipo", "condition_value": "a"}
        ]
    }"""
    f = DialogFrame.from_slots_json(raw)
    assert "tipo" in f.available_slots()
    assert "detalle" not in f.available_slots()
    f.try_update({"tipo": "a"})
    assert "detalle" in f.available_slots()


def test_from_slots_json_name_normalised_to_snake_case():
    raw = '{"slots": [{"name": "NombreUsuario", "type": "str"}]}'
    f = DialogFrame.from_slots_json(raw)
    assert "nombre_usuario" in f.all_keys()
    assert "NombreUsuario" not in f.all_keys()


def test_from_slots_json_default_type_is_str():
    raw = '{"slots": [{"name": "campo"}]}'
    f = DialogFrame.from_slots_json(raw)
    assert f.slot_type("campo") == "str"


def test_from_slots_json_accepts_dict_directly():
    data = {"slots": [{"name": "producto", "type": "str"}]}
    f = DialogFrame.from_slots_json(data)
    assert "producto" in f.all_keys()


def test_from_slots_json_empty_canonical_values_allowed():
    """An empty canonical_values list means no constraint — slot accepts any value."""
    raw = '{"slots": [{"name": "nota", "type": "str", "canonical_values": []}]}'
    f = DialogFrame.from_slots_json(raw)
    assert f.canonical_values("nota") == []


def test_from_slots_json_frame_starts_incomplete():
    raw = '{"slots": [{"name": "nombre", "type": "str"}]}'
    f = DialogFrame.from_slots_json(raw)
    assert not f.is_complete()


def test_from_slots_json_history_max_turns_respected():
    raw = '{"slots": [{"name": "x", "type": "str"}]}'
    f = DialogFrame.from_slots_json(raw, history_max_turns=10)
    assert f._max_history == 10


# ==== FROM_SLOTS_JSON: INVALID INPUTS ====


def test_from_slots_json_not_json_raises():
    with pytest.raises(ValueError):
        DialogFrame.from_slots_json("not json at all")


def test_from_slots_json_not_object_raises():
    with pytest.raises(ValueError):
        DialogFrame.from_slots_json('[{"name": "a", "type": "str"}]')


def test_from_slots_json_missing_slots_key_raises():
    with pytest.raises(ValueError, match="'slots'"):
        DialogFrame.from_slots_json('{"schema": []}')


def test_from_slots_json_slots_not_list_raises():
    with pytest.raises(ValueError):
        DialogFrame.from_slots_json('{"slots": "not a list"}')


def test_from_slots_json_empty_slots_raises():
    with pytest.raises(ValueError):
        DialogFrame.from_slots_json('{"slots": []}')


def test_from_slots_json_slot_not_dict_raises():
    with pytest.raises(ValueError, match="index 0"):
        DialogFrame.from_slots_json('{"slots": ["bad"]}')


def test_from_slots_json_slot_missing_name_raises():
    with pytest.raises(ValueError, match="'name'"):
        DialogFrame.from_slots_json('{"slots": [{"type": "str"}]}')


def test_from_slots_json_slot_empty_name_raises():
    with pytest.raises(ValueError, match="'name'"):
        DialogFrame.from_slots_json('{"slots": [{"name": "  ", "type": "str"}]}')


def test_from_slots_json_invalid_type_raises():
    with pytest.raises(ValueError, match="invalid type"):
        DialogFrame.from_slots_json('{"slots": [{"name": "x", "type": "list"}]}')


def test_from_slots_json_duplicate_name_raises():
    raw = '{"slots": [{"name": "x", "type": "str"}, {"name": "x", "type": "int"}]}'
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        DialogFrame.from_slots_json(raw)


def test_from_slots_json_duplicate_after_normalisation_raises():
    """Two names that normalise to the same snake_case are also duplicates."""
    raw = '{"slots": [{"name": "MySlot", "type": "str"}, {"name": "my_slot", "type": "str"}]}'
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        DialogFrame.from_slots_json(raw)


def test_from_slots_json_condition_slot_only_raises():
    raw = '{"slots": [{"name": "x", "type": "str"}, {"name": "y", "type": "str", "condition_slot": "x"}]}'
    with pytest.raises(ValueError, match="condition_value"):
        DialogFrame.from_slots_json(raw)


def test_from_slots_json_condition_value_only_raises():
    raw = '{"slots": [{"name": "x", "type": "str"}, {"name": "y", "type": "str", "condition_value": "v"}]}'
    with pytest.raises(ValueError, match="condition_slot"):
        DialogFrame.from_slots_json(raw)


def test_from_slots_json_condition_nonexistent_parent_raises():
    raw = """{
        "slots": [
            {"name": "child", "type": "str",
             "condition_slot": "ghost", "condition_value": "v"}
        ]
    }"""
    with pytest.raises(ValueError, match="'ghost'"):
        DialogFrame.from_slots_json(raw)


def test_from_slots_json_condition_on_list_str_raises():
    raw = """{
        "slots": [
            {"name": "items", "type": "list_str"},
            {"name": "child", "type": "str",
             "condition_slot": "items", "condition_value": "something"}
        ]
    }"""
    with pytest.raises(ValueError, match="list_str"):
        DialogFrame.from_slots_json(raw)


def test_from_slots_json_condition_value_not_in_canon_raises():
    raw = """{
        "slots": [
            {"name": "tipo", "type": "str", "canonical_values": ["a", "b"]},
            {"name": "child", "type": "str",
             "condition_slot": "tipo", "condition_value": "c"}
        ]
    }"""
    with pytest.raises(ValueError, match="condition_value"):
        DialogFrame.from_slots_json(raw)


def test_from_slots_json_canonical_values_not_list_raises():
    raw = '{"slots": [{"name": "x", "type": "str", "canonical_values": "small|large"}]}'
    with pytest.raises(ValueError, match="canonical_values"):
        DialogFrame.from_slots_json(raw)
