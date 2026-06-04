"""Unit tests for the strategy base layer: FSMConfig, operations, the strategy
registry, build/register helpers, and the shared cancel-confirmation flow."""

import pytest

# Import strategies package to trigger @register_strategy decorators.
import ros2_dialog_manager.strategies  # noqa: F401

from ros2_dialog_manager.strategies.base import (
    FSMConfig,
    OpKind,
    Operation,
    _STRATEGY_REGISTRY,
    available_modes,
    build_strategy,
    register_strategy,
)
from ros2_dialog_manager.dialog_context import DialogContext
from ros2_dialog_manager.dialog_frame import DialogFrame

# ==== FSMCONFIG DEFAULTS ====


def test_fsm_config_defaults():
    c = FSMConfig()
    assert c.max_turns == 0
    assert c.max_timeouts == 2
    assert c.max_unclear == 3
    assert c.max_attempts == 3


def test_fsm_config_custom():
    c = FSMConfig(max_turns=10, max_timeouts=5, max_unclear=2, max_attempts=4)
    assert c.max_turns == 10
    assert c.max_timeouts == 5


# ==== OPERATION / OPKIND ====


def test_operation_set():
    op = Operation(slot="nombre", kind=OpKind.SET, value="Ana")
    assert op.slot == "nombre"
    assert op.kind == OpKind.SET
    assert op.value == "Ana"


def test_opkind_values():
    assert OpKind.ADD.value == "add"
    assert OpKind.REMOVE.value == "remove"
    assert OpKind.REPLACE.value == "replace"
    assert OpKind.SET.value == "set"


# ==== STRATEGY REGISTRY: REAL STRATEGIES ====


def test_slot_filling_registered():
    assert "slot_filling" in _STRATEGY_REGISTRY


def test_explanation_registered():
    assert "explanation" in _STRATEGY_REGISTRY


def test_quiz_registered():
    assert "quiz" in _STRATEGY_REGISTRY


def test_available_modes_is_sorted():
    modes = available_modes()
    assert modes == sorted(modes)


def test_available_modes_includes_known():
    modes = available_modes()
    for expected in ("slot_filling", "explanation", "quiz"):
        assert expected in modes


# ==== BUILD STRATEGY ====


def test_build_strategy_unknown_mode():
    with pytest.raises(ValueError, match="Unknown dialog mode"):
        build_strategy(
            "_nonexistent_xyz",
            llm=None,
            config=FSMConfig(),
            ctx=DialogContext(),
        )


def test_build_strategy_returns_correct_type(monkeypatch):
    from ros2_dialog_manager.strategies.base import BaseDialogStrategy

    class _TestStrategy(BaseDialogStrategy):
        def on_init(self, task):
            return "hi"

        def on_user_turn(self, task, text):
            return "ok", False

        def succeeded(self):
            return True

        def current_data(self):
            return {}

    test_mode = "_test_mode_build"
    monkeypatch.setitem(_STRATEGY_REGISTRY, test_mode, _TestStrategy)
    s = build_strategy(test_mode, llm=None, config=FSMConfig(), ctx=DialogContext())
    assert isinstance(s, _TestStrategy)


# ==== REGISTER_STRATEGY: DUPLICATE RAISES AT IMPORT TIME ====


def test_duplicate_registration_raises(monkeypatch):
    from ros2_dialog_manager.strategies.base import BaseDialogStrategy

    class _StratA(BaseDialogStrategy):
        def on_init(self, t):
            return ""

        def on_user_turn(self, t, u):
            return "", False

        def succeeded(self):
            return True

        def current_data(self):
            return {}

    test_mode = "_test_dup_mode"
    monkeypatch.setitem(_STRATEGY_REGISTRY, test_mode, _StratA)

    with pytest.raises(ValueError, match="already registered"):
        register_strategy(test_mode)(_StratA)


# ==== CANCEL FLOW: BaseDialogStrategy._cancel_pre_check ====


class _FakeLLM:
    def __init__(self, cancel_intent=False, cancel_confirm=False):
        self._cancel_intent = cancel_intent
        self._cancel_confirm = cancel_confirm

    def detect_cancel_intent(self, text, ctx, strict=False):
        return self._cancel_intent

    def detect_cancel_confirmation(self, text, ctx):
        return self._cancel_confirm

    def ask_cancel_confirmation(self, task, ctx):
        return "¿Seguro que quieres cancelar?"

    def cancel_confirmed_response(self, task, frame, ctx):
        return "Cancelado."

    def cancel_denied_response(self, task, frame, ctx):
        return "Seguimos."

    # Minimal stubs so SlotFillingStrategy.__init__ doesn't crash.
    def create_frame(self, task, ctx):
        return DialogFrame({"x": None}, {"x": "str"})

    def audit_frame(self, frame, task, ctx):
        return 0

    def get_opening(self, task, frame, ctx):
        return "hola"


def _make_slot_strategy(fake_llm=None):
    from ros2_dialog_manager.strategies.slot_filling import SlotFillingStrategy

    llm = fake_llm or _FakeLLM()
    return SlotFillingStrategy(llm=llm, config=FSMConfig(), ctx=DialogContext(), request=None)


def test_cancel_pre_check_no_intent_returns_none():
    s = _make_slot_strategy(_FakeLLM(cancel_intent=False))
    result = s._cancel_pre_check("task", "una pizza")
    assert result is None


def test_cancel_pre_check_intent_starts_confirmation():
    s = _make_slot_strategy(_FakeLLM(cancel_intent=True))
    reply, done = s._cancel_pre_check("task", "cancela")
    assert not done
    assert s._awaiting_cancel_confirmation is True


def test_cancel_pre_check_confirmed_cancels():
    s = _make_slot_strategy(_FakeLLM(cancel_intent=True, cancel_confirm=True))
    # First call: detect cancel intent → asks for confirmation.
    s._cancel_pre_check("task", "cancela")
    # Second call: user confirms → done = True.
    reply, done = s._cancel_pre_check("task", "sí")
    assert done is True
    assert s._user_cancelled is True


def test_cancel_pre_check_denied_clears_flag():
    s = _make_slot_strategy(_FakeLLM(cancel_intent=True, cancel_confirm=False))
    s._cancel_pre_check("task", "cancela")
    reply, done = s._cancel_pre_check("task", "no")
    assert done is False
    assert s._awaiting_cancel_confirmation is False
    assert s._user_cancelled is False
