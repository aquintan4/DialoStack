"""
Unit tests for SlotFillingStrategy — acknowledgment rotation, phase transitions,
and frame sourcing (LLM-generated vs user-supplied schema).
"""

import pytest

from ros2_dialog_manager.dialog_context import DialogContext
from ros2_dialog_manager.dialog_frame import DialogFrame
from ros2_dialog_manager.strategies.base import FSMConfig
from ros2_dialog_manager.strategies.slot_filling import SlotFillingStrategy

# Ack phrases used to configure FSMConfig in tests.
_TEST_ACK_PHRASES = ("Noted.", "Done.", "Got it.", "OK.", "Understood.")


# ==== HELPERS ====


class _FullFakeLLM:
    """Fake LLM that allows controlling extract_slots and generate_response outputs."""

    def __init__(self, extractions=None, next_q="¿Cuál es tu edad?", confirm_q="¿Confirmas?"):
        self._extractions = extractions or []
        self._next_q = next_q
        self._confirm_q = confirm_q

    @property
    def history_max_turns(self):
        return 200

    # NLU
    def create_frame(self, task, ctx):
        return DialogFrame({"nombre": None, "edad": None}, {"nombre": "str", "edad": "int"})

    def audit_frame(self, frame, task, ctx):
        return 0

    def extract_slots(self, user_text, frame, ctx):
        return self._extractions

    def classify_intent(self, user_text, frame, ctx):
        return "unclear", {}

    def detect_cancel_intent(self, text, ctx, strict=False):
        return False

    def detect_cancel_confirmation(self, text, ctx):
        return False

    # NLG
    def get_opening(self, task, frame, ctx):
        return "Hola, ¿cuál es tu nombre?"

    def get_resume_opening(self, task, frame, next_slot, ctx):
        return "Continuamos."

    def generate_response(self, task, frame, user_text, extracted_slots, attempts_exceeded, ctx):
        return self._next_q

    def get_confirmation_question(self, task, frame, ctx):
        return self._confirm_q

    def response_to_intent(self, task, intent, corrections, frame, ctx):
        return "De acuerdo."

    def ask_cancel_confirmation(self, task, ctx):
        return "¿Seguro?"

    def cancel_confirmed_response(self, task, frame, ctx):
        return "Cancelado."

    def cancel_denied_response(self, task, frame, ctx):
        return "Seguimos."


def _make_strategy(llm=None):
    l = llm or _FullFakeLLM()
    cfg = FSMConfig(ack_phrases=_TEST_ACK_PHRASES)
    s = SlotFillingStrategy(llm=l, config=cfg, ctx=DialogContext(), request=None)
    s._frame = DialogFrame({"nombre": None, "edad": None}, {"nombre": "str", "edad": "int"})
    s._phase = "gathering"
    return s


# ==== ACK ROTATION ====


def test_pop_ack_cycles_through_phrases():
    s = _make_strategy()
    seen = set()
    for _ in range(len(_TEST_ACK_PHRASES) * 2):
        seen.add(s._pop_ack())
    assert seen == set(_TEST_ACK_PHRASES)


def test_pop_ack_first_call_is_first_phrase():
    s = _make_strategy()
    assert s._pop_ack() == _TEST_ACK_PHRASES[0]


def test_pop_ack_never_repeats_consecutively():
    s = _make_strategy()
    prev = None
    # _TEST_ACK_PHRASES has 5 entries; cycling guarantees no two consecutive repeats.
    for _ in range(len(_TEST_ACK_PHRASES)):
        current = s._pop_ack()
        assert current != prev, f"Repeated phrase '{current}' twice in a row"
        prev = current


# ==== ACK INJECTED ONLY WHEN SOMETHING WAS APPLIED ====


def test_ack_prepended_when_extraction_succeeds():
    llm = _FullFakeLLM(
        extractions=[{"slot": "nombre", "value": "Ana", "source_span": "Ana"}],
        next_q="¿Cuál es tu edad?",
    )
    s = _make_strategy(llm)
    reply, done = s._handle_gathering("task", "Me llamo Ana")
    # Reply must start with one of the ack phrases followed by the question.
    assert any(reply.startswith(p) for p in _TEST_ACK_PHRASES), f"Expected ack prefix in {reply!r}"
    assert "edad" in reply.lower() or "¿" in reply


def test_no_ack_when_nothing_extracted():
    llm = _FullFakeLLM(extractions=[], next_q="No te he entendido, ¿cuál es tu nombre?")
    s = _make_strategy(llm)
    reply, done = s._handle_gathering("task", "hmmm")
    # Reply must NOT start with any ack phrase.
    assert not any(
        reply.startswith(p) for p in _TEST_ACK_PHRASES
    ), f"Unexpected ack prefix in {reply!r}"


def test_ack_does_not_accumulate_without_extractions():
    """Repeated turns without extractions must not count up the ack index."""
    llm = _FullFakeLLM(extractions=[], next_q="¿Cuál es tu nombre?")
    s = _make_strategy(llm)
    for _ in range(5):
        s._handle_gathering("task", "...")
    assert s._ack_idx == 0


# ==== PHASE TRANSITION: GATHERING TO CONFIRMING ====


def test_transition_to_confirming_when_complete():
    """When the last slot is filled, reply must contain the confirmation question."""
    llm = _FullFakeLLM(
        extractions=[{"slot": "edad", "value": "30", "source_span": "30"}],
        confirm_q="¿Confirmas nombre=Ana, edad=30?",
    )
    s = _make_strategy(llm)
    s._frame.try_update({"nombre": "Ana"})  # pre-fill nombre; edad remains
    reply, done = s._handle_gathering("task", "tengo 30 años")
    assert s._phase == "confirming", "Phase should be 'confirming' after last slot is filled"
    assert "Confirmas" in reply or "30" in reply
    assert done is False


def test_ack_included_when_transitioning_to_confirming():
    """Ack must also be prepended when the last slot triggers the confirmation question."""
    llm = _FullFakeLLM(
        extractions=[{"slot": "edad", "value": "25", "source_span": "25"}],
        confirm_q="¿Es correcto?",
    )
    s = _make_strategy(llm)
    s._frame.try_update({"nombre": "Ana"})
    reply, done = s._handle_gathering("task", "25 años")
    assert any(
        reply.startswith(p) for p in _TEST_ACK_PHRASES
    ), f"Expected ack prefix before confirmation question, got {reply!r}"
    assert "correcto" in reply.lower() or "¿" in reply


def test_no_ack_before_confirmation_question_when_nothing_extracted():
    """If extraction fails for the last turn and the frame was already complete, no ack."""
    llm = _FullFakeLLM(extractions=[], confirm_q="¿Es correcto?")
    s = _make_strategy(llm)
    # Pre-fill all slots directly.
    s._frame.try_update({"nombre": "Ana", "edad": 30})
    # Frame is already complete; gathering detects is_complete() → confirming.
    reply, done = s._handle_gathering("task", "anything")
    assert s._phase == "confirming"
    assert not any(
        reply.startswith(p) for p in _TEST_ACK_PHRASES
    ), f"Unexpected ack when nothing was extracted, got {reply!r}"


# ==== CONDITIONAL SLOTS ====


def test_conditional_last_slot_triggers_confirmation():
    """When the last required slot is conditional and gets filled, the strategy
    must transition to confirming."""
    frame = DialogFrame(
        {"tipo": None, "detalle_a": None},
        {"tipo": "str", "detalle_a": "str"},
        conditions={"detalle_a": [("tipo", "A")]},
        canonical_values={"tipo": ["A", "B"]},
    )

    class _ConditionalLLM(_FullFakeLLM):
        def extract_slots(self, user_text, frame, ctx):
            return [{"slot": "detalle_a", "value": "valor_x", "source_span": "valor_x"}]

        def get_confirmation_question(self, task, frame, ctx):
            return "¿Confirmas tipo=A, detalle_a=valor_x?"

    llm = _ConditionalLLM()
    s = SlotFillingStrategy(
        llm=llm, config=FSMConfig(ack_phrases=_TEST_ACK_PHRASES), ctx=DialogContext(), request=None
    )
    s._frame = frame
    s._phase = "gathering"
    s._frame.try_update({"tipo": "A"})  # parent set; detalle_a now in scope

    reply, done = s._handle_gathering("task", "valor_x")
    assert s._phase == "confirming", "Expected confirming phase after last conditional slot filled"
    assert done is False
    assert "Confirmas" in reply or "valor_x" in reply


# ==== FRAME SOURCING: USER-SUPPLIED SCHEMA VS LLM GENERATION ====


class _TrackingLLM(_FullFakeLLM):
    """Extends _FullFakeLLM to count create_frame calls."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.create_frame_calls = 0

    def create_frame(self, task, ctx):
        self.create_frame_calls += 1
        return super().create_frame(task, ctx)


class _FakeRequest:
    """Minimal stand-in for a ROS2 DialogTask goal."""

    def __init__(self, frame_schema_json="", initial_frame_json=""):
        self.frame_schema_json = frame_schema_json
        self.initial_frame_json = initial_frame_json


_VALID_SCHEMA = '{"slots": [{"name": "nombre", "type": "str"}, {"name": "edad", "type": "int"}]}'


def test_on_init_uses_provided_schema_skips_llm():
    """When frame_schema_json is set, create_frame must NOT be called."""
    llm = _TrackingLLM()
    req = _FakeRequest(frame_schema_json=_VALID_SCHEMA)
    s = SlotFillingStrategy(llm=llm, config=FSMConfig(), ctx=DialogContext(), request=req)
    s.on_init("Collect user info")
    assert (
        llm.create_frame_calls == 0
    ), "create_frame should not be called when frame_schema_json is provided"


def test_on_init_schema_produces_correct_slots():
    """Frame built from schema must contain exactly the declared slots."""
    llm = _TrackingLLM()
    req = _FakeRequest(frame_schema_json=_VALID_SCHEMA)
    s = SlotFillingStrategy(llm=llm, config=FSMConfig(), ctx=DialogContext(), request=req)
    s.on_init("Collect user info")
    assert set(s._frame.all_keys()) == {"nombre", "edad"}
    assert s._frame.slot_type("nombre") == "str"
    assert s._frame.slot_type("edad") == "int"


def test_on_init_calls_llm_when_schema_absent():
    """When frame_schema_json is empty, create_frame must be called once."""
    llm = _TrackingLLM()
    req = _FakeRequest(frame_schema_json="")
    s = SlotFillingStrategy(llm=llm, config=FSMConfig(), ctx=DialogContext(), request=req)
    s.on_init("Collect user info")
    assert llm.create_frame_calls == 1


def test_on_init_calls_llm_when_request_is_none():
    """When request is None (no frame_schema_json at all), LLM is used."""
    llm = _TrackingLLM()
    s = SlotFillingStrategy(llm=llm, config=FSMConfig(), ctx=DialogContext(), request=None)
    s.on_init("Collect user info")
    assert llm.create_frame_calls == 1


def test_on_init_raises_on_invalid_schema():
    """Malformed frame_schema_json must raise ValueError before the dialog starts."""
    llm = _FullFakeLLM()
    req = _FakeRequest(frame_schema_json='{"slots": []}')
    s = SlotFillingStrategy(llm=llm, config=FSMConfig(), ctx=DialogContext(), request=req)
    with pytest.raises(ValueError):
        s.on_init("task")


def test_on_init_raises_on_bad_type_in_schema():
    """A slot with an unknown type must raise ValueError."""
    llm = _FullFakeLLM()
    req = _FakeRequest(frame_schema_json='{"slots": [{"name": "x", "type": "uuid"}]}')
    s = SlotFillingStrategy(llm=llm, config=FSMConfig(), ctx=DialogContext(), request=req)
    with pytest.raises(ValueError, match="invalid type"):
        s.on_init("task")


def test_on_init_schema_combined_with_initial_frame_json():
    """
    frame_schema_json defines the schema; initial_frame_json pre-fills values.
    Both must work together: the pre-filled slot must be visible in the frame.
    """
    llm = _TrackingLLM()
    schema = '{"slots": [{"name": "nombre", "type": "str"}, {"name": "edad", "type": "int"}]}'
    req = _FakeRequest(
        frame_schema_json=schema,
        initial_frame_json='{"nombre": "Ana"}',
    )
    s = SlotFillingStrategy(llm=llm, config=FSMConfig(), ctx=DialogContext(), request=req)
    s.on_init("task")
    assert llm.create_frame_calls == 0
    assert s._frame.current_value("nombre") == "Ana"
    assert s._frame.current_value("edad") is None
