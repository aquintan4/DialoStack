"""Unit tests for ProcedureStrategy: step parsing, navigation and results."""

import json

import pytest

from ros2_dialog_manager.dialog_context import DialogContext, Resource
from ros2_dialog_manager.llm_client import LLMDialogClient
from ros2_dialog_manager.strategies.base import FSMConfig
from ros2_dialog_manager.strategies.procedure import ProcedureStrategy

from test_prompt_builder import production_builder


class _FakeLLM:
    """Returns scripted intents and echoes the step for every NLG call."""

    def __init__(self, intents=()):
        self._intents = list(intents)
        self.help_calls = 0

    def detect_cancel_intent(self, user_text, ctx, strict=False):
        return False

    def classify_step_turn(self, user_text, step, check, history, ctx):
        return self._intents.pop(0) if self._intents else "unclear"

    def procedure_opening(self, task, total, ctx):
        return f"Intro {total}."

    def procedure_step(self, step, n, total, situation, ctx):
        return f"[{situation} {n}/{total}] {step}"

    def procedure_answer_question(self, user_text, task, step, history, ctx):
        return "Answer."

    def procedure_help_step(self, task, step, history, attempt_number, ctx):
        self.help_calls += 1
        return f"Help {attempt_number}: {step}"

    def procedure_remind(self, step, ctx):
        return "Tell me when done."

    def procedure_summary(self, task, completed, total, not_done, ctx):
        return f"Summary {completed}/{total} missing={not_done}"


def _ctx(steps) -> DialogContext:
    return DialogContext(resources=[Resource("steps", "Procedure steps", json.dumps(steps))])


def _make(intents=(), steps=None, max_attempts=3, skip_intro=False):
    if steps is None:
        steps = ["Open the box", {"step": "Plug it in", "check": "green light"}, "Press start"]
    request = type("Req", (), {"skip_intro": skip_intro})()
    llm = _FakeLLM(intents)
    s = ProcedureStrategy(
        llm=llm, config=FSMConfig(max_attempts=max_attempts), ctx=_ctx(steps), request=request
    )
    return s, llm


# ==== PARSING ====


def test_parses_strings_and_objects():
    s, _ = _make()
    assert [x["step"] for x in s._steps] == ["Open the box", "Plug it in", "Press start"]
    assert s._steps[1]["check"] == "green light"


def test_accepts_instruction_key_and_skips_empty_entries():
    s, _ = _make(steps=[{"instruction": "A"}, "", {"check": "x"}, 3, "B"])
    assert [x["step"] for x in s._steps] == ["A", "B"]


def test_on_init_without_steps_raises():
    s = ProcedureStrategy(llm=_FakeLLM(), config=FSMConfig(), ctx=DialogContext(), request=None)
    with pytest.raises(ValueError):
        s.on_init("task")


# ==== FLOW ====


def test_opening_includes_intro_and_first_step():
    s, _ = _make()
    assert s.on_init("task") == "Intro 3. [first 1/3] Open the box"


def test_skip_intro_goes_straight_to_first_step():
    s, _ = _make(skip_intro=True)
    assert s.on_init("task") == "[first 1/3] Open the box"


def test_done_advances_and_last_step_closes():
    s, _ = _make(["done", "done", "done"])
    s.on_init("task")
    reply, done = s.on_user_turn("task", "ok")
    assert reply == "[next 2/3] Plug it in" and not done
    s.on_user_turn("task", "light is green")
    reply, done = s.on_user_turn("task", "pressed")
    assert done and reply.startswith("Summary 3/3")
    assert s.succeeded()
    assert s.current_phase() == "done"


def test_question_and_unclear_stay_on_step():
    s, _ = _make(["question", "unclear"])
    s.on_init("task")
    assert s.on_user_turn("task", "which box?") == ("Answer.", False)
    assert s.on_user_turn("task", "hmm") == ("Tell me when done.", False)
    assert s.current_phase() == "step_1_of_3"


def test_repeat_and_back():
    s, _ = _make(["done", "repeat", "back"])
    s.on_init("task")
    s.on_user_turn("task", "done")
    assert s.on_user_turn("task", "again?")[0] == "[repeat 2/3] Plug it in"
    assert s.on_user_turn("task", "go back")[0] == "[back 1/3] Open the box"
    # Going back re-opens the step: it no longer counts as completed.
    assert s.current_data()["completed"] == 0


def test_back_on_first_step_stays():
    s, _ = _make(["back"])
    s.on_init("task")
    assert s.on_user_turn("task", "back")[0] == "[back 1/3] Open the box"


def test_skip_is_recorded_and_reported_in_summary():
    s, _ = _make(["skip", "done", "done"])
    s.on_init("task")
    s.on_user_turn("task", "skip it")
    s.on_user_turn("task", "done")
    reply, done = s.on_user_turn("task", "done")
    assert done and "Summary 2/3" in reply and "Open the box" in reply
    data = s.current_data()
    assert data["skipped"] == 1 and data["completed"] == 2
    assert data["results"][0] == {"step": "Open the box", "status": "skipped"}


def test_problem_helps_then_moves_on_after_max_attempts():
    s, llm = _make(["problem", "problem"], max_attempts=2)
    s.on_init("task")
    assert s.on_user_turn("task", "I can't")[0] == "Help 2: Open the box"
    reply, done = s.on_user_turn("task", "still stuck")
    assert reply == "[next 2/3] Plug it in" and not done
    assert llm.help_calls == 1
    assert s.current_data()["results"][0]["status"] == "stuck"


def test_help_attempts_reset_per_step():
    s, llm = _make(["problem", "done", "problem"], max_attempts=2)
    s.on_init("task")
    s.on_user_turn("task", "stuck")
    s.on_user_turn("task", "done")
    assert s.on_user_turn("task", "stuck again")[0] == "Help 2: Plug it in"


def test_turn_count_counts_user_turns():
    s, _ = _make(["unclear", "done"])
    s.on_init("task")
    s.on_user_turn("task", "a")
    s.on_user_turn("task", "b")
    assert s.turn_count() == 2


# ==== LLM CLIENT AND PROMPTS ====


def _client(responses):
    """Real LLMDialogClient over the production prompts and a scripted infer_fn."""
    calls = []

    def infer(sid, prompt, max_tokens, schema):
        calls.append(prompt)
        return responses.pop(0) if responses else None

    return LLMDialogClient("nlu", "nlg", infer, production_builder()), calls


def test_classify_step_turn_parses_and_validates_intent():
    llm, calls = _client(['{"intent": "skip"}', '{"intent": "dance"}'])
    assert llm.classify_step_turn("skip it", "Open the box", "", [], None) == "skip"
    assert llm.classify_step_turn("x", "Open the box", "", [], None) == "unclear"
    assert 'CURRENT STEP: "Open the box"' in calls[0]


def test_procedure_fallbacks_when_llm_is_down():
    llm, _ = _client([])
    assert llm.classify_step_turn("ok", "A", "", [], None) == "unclear"
    assert llm.procedure_step("Open the box", 1, 3, "first") == "Step 1 of 3: Open the box"
    assert llm.procedure_help_step("task", "Open the box", [], 2) == "Open the box"
    assert llm.procedure_summary("task", 3, 3, []) == "We have finished the procedure."


def test_procedure_templates_render():
    pb = production_builder()
    assert "STEP 2 of 4" in pb.procedure_step("Plug it in", 2, 4, "next")
    prompt, schema = pb.classify_step_turn("ready", "Plug it in", "green light", [], None)
    assert "green light" in prompt and "skip" in schema["properties"]["intent"]["enum"]
    assert "(none)" in pb.procedure_summary("task", 2, 2, "")
