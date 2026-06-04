"""Unit tests for text utilities: accent removal, normalisation, input cleaning,
local cancel detection, snake_case conversion, and loose JSON parsing."""

import pytest

from ros2_dialog_manager.utils import (
    clean_user_input,
    local_cancel_check,
    normalize_text,
    parse_loose_json,
    remove_accents,
    to_snake_case,
)

# ==== REMOVE_ACCENTS ====


def test_remove_accents_basic():
    assert remove_accents("héllo") == "hello"


def test_remove_accents_spanish():
    assert remove_accents("José María") == "Jose Maria"


def test_remove_accents_no_accents():
    assert remove_accents("hello") == "hello"


# ==== NORMALIZE_TEXT ====


def test_normalize_text_lowercase():
    assert normalize_text("HOLA") == "hola"


def test_normalize_text_strips_accents():
    assert normalize_text("¿Cómo estás?") == "como estas"


def test_normalize_text_strips_punctuation():
    assert normalize_text("hola, ¿qué tal?") == "hola que tal"


def test_normalize_text_collapses_whitespace():
    assert normalize_text("  hola   mundo  ") == "hola mundo"


def test_normalize_text_empty():
    assert normalize_text("") == ""


# ==== CLEAN_USER_INPUT ====


def test_clean_user_input_valid():
    assert clean_user_input("Quiero una pizza") == "Quiero una pizza"


def test_clean_user_input_empty():
    assert clean_user_input("") is None


def test_clean_user_input_whitespace_only():
    assert clean_user_input("   ") is None


def test_clean_user_input_noise_phrase():
    assert clean_user_input("gracias por ver") is None


def test_clean_user_input_noise_filler():
    assert clean_user_input("mm") is None


def test_clean_user_input_pure_punctuation():
    assert clean_user_input("...!!!") is None


def test_clean_user_input_preserves_original():
    # The original (non-normalised) string is returned.
    result = clean_user_input("Hola, buenos días")
    assert result == "Hola, buenos días"


def test_clean_user_input_single_word():
    assert clean_user_input("sí") == "sí"


# ==== LOCAL_CANCEL_CHECK ====


def test_cancel_check_exact_cancel():
    assert local_cancel_check("cancel") is True


def test_cancel_check_exact_stop():
    assert local_cancel_check("stop") is True


def test_cancel_check_exact_quit():
    assert local_cancel_check("quit") is True


def test_cancel_check_exact_abort():
    assert local_cancel_check("abort") is True


def test_cancel_check_no_cancel_phrase():
    assert local_cancel_check("quiero una pizza") is False


def test_cancel_check_unrelated_para():
    # "para mi" is not a cancel command.
    assert local_cancel_check("para mi es suficiente") is False


def test_cancel_check_ambiguous_pattern_returns_none():
    # "cancel please" contains a cancel-coloured token → ambiguous → None.
    assert local_cancel_check("cancel please") is None


def test_cancel_check_strict_suppresses_ambiguous():
    assert local_cancel_check("cancel please", strict=True) is False


def test_cancel_check_strict_exact_still_true():
    assert local_cancel_check("cancel", strict=True) is True


def test_cancel_check_strict_non_cancel():
    assert local_cancel_check("quiero continuar", strict=True) is False


# ==== TO_SNAKE_CASE ====


def test_to_snake_case_space():
    assert to_snake_case("nombre completo") == "nombre_completo"


def test_to_snake_case_camel():
    assert to_snake_case("TipoConsulta") == "tipo_consulta"


def test_to_snake_case_hyphen():
    assert to_snake_case("tipo-consulta") == "tipo_consulta"


def test_to_snake_case_already_snake():
    assert to_snake_case("nombre_completo") == "nombre_completo"


def test_to_snake_case_mixed_case_and_spaces():
    assert to_snake_case("Nombre Completo") == "nombre_completo"


def test_to_snake_case_special_chars():
    assert to_snake_case("slot!@#") == "slot"


def test_to_snake_case_empty_gives_slot():
    assert to_snake_case("") == "slot"


def test_to_snake_case_leading_trailing_underscores():
    result = to_snake_case("  nombre  ")
    assert not result.startswith("_")
    assert not result.endswith("_")


def test_to_snake_case_multiple_spaces():
    assert to_snake_case("a   b") == "a_b"


def test_to_snake_case_mixed_camel_and_space():
    assert to_snake_case("userName Email") == "user_name_email"


# ==== PARSE_LOOSE_JSON ====


def test_parse_loose_json_clean_object():
    assert parse_loose_json('{"key": "val"}') == {"key": "val"}


def test_parse_loose_json_markdown_fence():
    raw = '```json\n{"key": "val"}\n```'
    assert parse_loose_json(raw) == {"key": "val"}


def test_parse_loose_json_trailing_comma():
    assert parse_loose_json('{"a": 1,}') == {"a": 1}


def test_parse_loose_json_already_dict():
    d = {"x": 1}
    assert parse_loose_json(d) is d


def test_parse_loose_json_already_list():
    lst = [1, 2]
    assert parse_loose_json(lst) is lst


def test_parse_loose_json_array():
    assert parse_loose_json("[1, 2, 3]") == [1, 2, 3]


def test_parse_loose_json_trailing_comma_array():
    assert parse_loose_json("[1, 2,]") == [1, 2]


def test_parse_loose_json_no_json_raises():
    with pytest.raises(ValueError):
        parse_loose_json("this is not json at all")


def test_parse_loose_json_with_preamble():
    raw = 'Sure, here is the output: {"a": 1}'
    assert parse_loose_json(raw) == {"a": 1}


def test_parse_loose_json_nested():
    raw = '{"outer": {"inner": [1, 2]}}'
    result = parse_loose_json(raw)
    assert result["outer"]["inner"] == [1, 2]
