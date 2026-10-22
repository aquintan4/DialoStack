"""Unit tests for RoleplayStrategy: scene parsing, turn routing, limits and scoring."""

import json

import pytest

from ros2_dialog_manager.dialog_context import DialogContext, Resource
from ros2_dialog_manager.llm_client import LLMDialogClient
from ros2_dialog_manager.strategies.base import FSMConfig
from ros2_dialog_manager.strategies.roleplay import RoleplayStrategy

from test_prompt_builder import production_builder

_SCENE = {
    "scenario": "Job interview for a robotics internship",
    "role": "The interviewer",
    "user_goal": "Get the internship",
    "criteria": ["Answers clearly", "Gives concrete examples"],
}

_EVAL = {
    "scores": [
        {
            "criterion": "Answers clearly",
            "score": 4,
            "evidence": "I studied robotics.",
            "comment": "Clear.",
        }
    ],
}


class _FakeLLM:
    def __init__(self, intents=(), evaluation=None):
        self._intents = list(intents)
        self._evaluation = _EVAL if evaluation is None else evaluation
        self.reply_calls = 0
        self.evaluated_history = None

    def detect_cancel_intent(self, user_text, ctx, strict=False):
        return False

    def roleplay_intro(self, task, scene, ctx):
        return "Intro."

    def roleplay_reply(self, scene, history, ctx):
        self.reply_calls += 1
        return f"Line {self.reply_calls}."

    def classify_roleplay_turn(self, user_text, scene, history, ctx):
        return self._intents.pop(0) if self._intents else "continue"

    def roleplay_coach(self, user_text, scene, history, ctx):
        return "Hint."

    def evaluate_roleplay(self, scene, history, ctx):
        self.evaluated_history = list(history)
        return self._evaluation

    def roleplay_feedback(self, scene, evaluation, ended_by, ctx):
        return {
            "text": f"Feedback ({ended_by}).",
            "highlight": "Good closing question.",
            "improve": "Give examples.",
        }


def _ctx(scene) -> DialogContext:
    return DialogContext(
        resources=[Resource("scene", "Roleplay scene", json.dumps(scene))]
    )


def _make(intents=(), scene=None, max_turns=0, skip_intro=False, evaluation=None):
    request = type("Req", (), {"skip_intro": skip_intro})()
    llm = _FakeLLM(intents, evaluation)
    s = RoleplayStrategy(
        llm=llm,
        config=FSMConfig(max_turns=max_turns),
        ctx=_ctx(scene if scene is not None else _SCENE),
        request=request,
    )
    return s, llm


# ==== PARSING AND LIMITS ====


def test_parses_scene_and_criteria_objects():
    s, _ = _make(scene={**_SCENE, "criteria": ["A", {"name": "B"}, "", 3]})
    assert s._scene["criteria"] == ["A", "B"]
    assert s._scene["user_goal"] == "Get the internship"


def test_missing_scene_or_criteria_raises():
    s = RoleplayStrategy(
        llm=_FakeLLM(), config=FSMConfig(), ctx=DialogContext(), request=None
    )
    with pytest.raises(ValueError):
        s.on_init("task")
    s, _ = _make(scene={**_SCENE, "criteria": []})
    with pytest.raises(ValueError):
        s.on_init("task")


def test_exchange_limit_defaults_and_is_capped_by_max_turns():
    assert _make()[0]._max_exchanges == 10
    assert _make(scene={**_SCENE, "max_exchanges": 4})[0]._max_exchanges == 4
    assert (
        _make(scene={**_SCENE, "max_exchanges": 20}, max_turns=6)[0]._max_exchanges == 6
    )


# ==== FLOW ====


def test_opening_is_intro_plus_first_character_line():
    s, _ = _make()
    assert s.on_init("task") == "Intro. Line 1."


def test_skip_intro_starts_in_character():
    s, _ = _make(skip_intro=True)
    assert s.on_init("task") == "Line 1."


def test_continue_gets_a_character_reply():
    s, _ = _make(["continue"])
    s.on_init("task")
    assert s.on_user_turn("task", "I love robots") == ("Line 2.", False)
    assert s.current_phase() == "scene_1_of_10"


def test_coach_hint_is_kept_out_of_the_transcript():
    s, llm = _make(["coach", "end"])
    s.on_init("task")
    assert s.on_user_turn("task", "what should I say?") == ("Hint.", False)
    s.on_user_turn("task", "let's stop")
    contents = [t["content"] for t in llm.evaluated_history]
    assert "what should I say?" not in contents and "Hint." not in contents


def test_user_end_evaluates_and_reports():
    s, _ = _make(["continue", "end"])
    s.on_init("task")
    s.on_user_turn("task", "hi")
    reply, done = s.on_user_turn("task", "stop")
    assert done and reply == "Feedback (user)."
    data = s.current_data()
    assert data["ended_by"] == "user" and data["average"] == 4.0
    assert data["highlight"] == "Good closing question."
    assert s.succeeded() and s.current_phase() == "done"


def test_scene_end_is_reported_as_scene():
    s, _ = _make(["scene_end"])
    s.on_init("task")
    assert s.on_user_turn("task", "goodbye, thank you") == ("Feedback (scene).", True)


def test_limit_closes_the_scene_on_the_last_turn():
    s, _ = _make(scene={**_SCENE, "max_exchanges": 2})
    s.on_init("task")
    assert s.on_user_turn("task", "a")[1] is False
    reply, done = s.on_user_turn("task", "b")
    assert done and reply == "Feedback (limit)."


def test_failed_evaluation_still_finishes():
    s, _ = _make(["end"], evaluation={})
    s.on_init("task")
    assert s.on_user_turn("task", "stop")[1] is True
    assert s.current_data()["scores"] == [] and s.current_data()["average"] is None


# ==== LLM CLIENT AND PROMPTS ====


def _client(responses):
    calls = []

    def infer(sid, prompt, max_tokens, schema):
        calls.append(prompt)
        return responses.pop(0) if responses else None

    return LLMDialogClient("nlu", "nlg", infer, production_builder()), calls


def test_classify_defaults_to_continue():
    llm, _ = _client(['{"intent": "coach"}', '{"intent": "dance"}'])
    assert llm.classify_roleplay_turn("help", _SCENE, [], None) == "coach"
    assert llm.classify_roleplay_turn("x", _SCENE, [], None) == "continue"
    assert llm.classify_roleplay_turn("x", _SCENE, [], None) == "continue"  # LLM down


# ==== FIXES FROM THE FIRST LIVE SESSION ====


def test_scene_resource_is_kept_out_of_the_context():
    other = Resource("company", "About the company", "We build service robots.")
    ctx = DialogContext(
        resources=[Resource("scene", "Roleplay scene", json.dumps(_SCENE)), other]
    )
    RoleplayStrategy(llm=_FakeLLM(), config=FSMConfig(), ctx=ctx, request=None)
    assert ctx.resources == [other]
    block = ctx.to_prompt_block()
    assert "Gives concrete examples" not in block and "service robots" in block


def test_character_prompt_never_sees_the_rubric():
    prompt = production_builder().roleplay_reply(_SCENE, [], DialogContext(domain="hr"))
    assert "Answers clearly" not in prompt and "Gives concrete examples" not in prompt


def test_reply_keeps_only_the_first_question():
    llm, _ = _client(
        ["Good base. Can you give an example? Also, what would you do if it failed?"]
    )
    assert llm.roleplay_reply(_SCENE, []) == "Good base. Can you give an example?"
    llm, _ = _client(["We work in sprints. How do you organise yourself?"])
    assert (
        llm.roleplay_reply(_SCENE, [])
        == "We work in sprints. How do you organise yourself?"
    )


def test_reply_prompt_grows_by_appending_for_prefix_cache_reuse():
    pb = production_builder()
    turn1 = [
        {"role": "assistant", "content": "Hello, tell me about you."},
        {"role": "user", "content": "I studied robotics."},
    ]
    turn2 = turn1 + [
        {"role": "assistant", "content": "Which project?"},
        {"role": "user", "content": "A line follower."},
    ]
    a, b = pb.roleplay_reply(_SCENE, turn1), pb.roleplay_reply(_SCENE, turn2)
    shared = a[: a.index("I studied robotics.") + len("I studied robotics.")]
    assert b.startswith(shared)
    assert (
        a.cache_prefix_len > 1000 and a[: a.cache_prefix_len] == b[: b.cache_prefix_len]
    )
    assert "Character: Which project?" in b


def test_classifier_sees_only_the_exchange_before_the_reply():
    history = [
        {"role": "assistant", "content": "old line"},
        {"role": "user", "content": "old answer"},
        {"role": "assistant", "content": "Last question?"},
        {"role": "user", "content": "you're right"},
    ]
    prompt, _ = production_builder().classify_roleplay_turn(
        "you're right", _SCENE, history, None
    )
    tail = prompt[prompt.index("LAST EXCHANGE") :]
    assert "Character: Last question?" in tail and "old line" not in tail
    assert tail.count("you're right") == 1


def test_repeated_question_is_regenerated_once():
    history = [
        {"role": "assistant", "content": "Hello. Which simulator did you use?"},
        {"role": "user", "content": "I prefer good pay."},
    ]
    llm, calls = _client(
        ["I see. Which simulator did you use exactly?", "Fair. What do you enjoy most?"]
    )
    assert llm.roleplay_reply(_SCENE, history) == "Fair. What do you enjoy most?"
    assert len(calls) == 2 and "repeated a question you already asked" in calls[1]
    # The retry note goes at the end: the cached prefix is untouched.
    assert calls[1].startswith(calls[0].rstrip("\n"))


def test_new_question_is_not_regenerated():
    history = [
        {"role": "assistant", "content": "Hello. Which simulator did you use?"},
        {"role": "user", "content": "Gazebo."},
    ]
    llm, calls = _client(["Nice. How big was your team?"])
    assert llm.roleplay_reply(_SCENE, history) == "Nice. How big was your team?"
    assert len(calls) == 1


def test_imperative_repeat_is_detected_too():
    history = [
        {
            "role": "assistant",
            "content": "I see, but first tell me which simulator you used.",
        },
        {"role": "user", "content": "Pay matters."},
    ]
    llm, calls = _client(
        [
            "Right, but first tell me which simulator you used.",
            "Fair. What do you enjoy most?",
        ]
    )
    assert llm.roleplay_reply(_SCENE, history) == "Fair. What do you enjoy most?"


# ==== EVALUATION AND FEEDBACK ====

_HISTORY = [
    {"role": "assistant", "content": "Why this job?"},
    {"role": "user", "content": "I like robots."},
    {"role": "assistant", "content": "Anything to ask?"},
    {"role": "user", "content": "How is the team?"},
]


def test_evaluation_scores_each_criterion_with_verbatim_evidence():
    llm, calls = _client(
        [
            '{"lines": [2, 2, 9], "score": 9, "comment": "Asked about the team."}',
            '{"lines": [], "score": "bad", "comment": "x"}',  # unusable: retried
            '{"lines": [], "score": 1, "comment": "No examples."}',
        ]
    )
    out = llm.evaluate_roleplay(_SCENE, _HISTORY, None)
    assert out["scores"] == [
        {
            "criterion": "Answers clearly",
            "score": 5,
            "evidence": "How is the team?",
            "comment": "Asked about the team.",
        },
        {
            "criterion": "Gives concrete examples",
            "score": 1,
            "evidence": "",
            "comment": "No examples.",
        },
    ]
    assert len(calls) == 3


def test_criterion_calls_share_everything_but_the_criterion():
    pb = production_builder()
    lines = ["I like robots.", "How is the team?"]
    a, schema = pb.evaluate_roleplay_criterion(
        _SCENE, _HISTORY, lines, "Answers clearly"
    )
    b, _ = pb.evaluate_roleplay_criterion(
        _SCENE, _HISTORY, lines, "Gives concrete examples"
    )
    assert "  1. I like robots.\n  2. How is the team?" in a
    assert a.endswith('CRITERION: "Answers clearly"\n') and b.endswith(
        'CRITERION: "Gives concrete examples"\n'
    )
    assert a[: a.rindex("CRITERION")] == b[: b.rindex("CRITERION")]
    props = list(schema["properties"])
    assert props.index("lines") < props.index("comment") < props.index("score")


def test_feedback_speaks_every_score_after_the_closing():
    llm, calls = _client(
        [
            '{"closing": "Time is up.", "highlight": "Great question.", "improve": "Add examples."}'
        ]
    )
    evaluation = {
        "scores": [
            {
                "criterion": "Answers clearly",
                "score": 4,
                "evidence": "",
                "comment": "c",
            },
            {
                "criterion": "Gives concrete examples",
                "score": 2,
                "evidence": "e",
                "comment": "d",
            },
        ]
    }
    out = llm.roleplay_feedback(_SCENE, evaluation, "limit")
    assert out["text"] == (
        "Time is up. Your scores: Answers clearly, 4 out of 5; Gives concrete examples, 2 out of 5. "
        "Great question. Add examples."
    )
    assert (
        out["highlight"] == "Great question."
        and "the time for the practice ran out" in calls[0]
    )


def test_evaluation_and_feedback_fallbacks():
    llm, _ = _client([])
    assert llm.evaluate_roleplay(_SCENE, _HISTORY, None) == {}
    assert (
        llm.roleplay_feedback(_SCENE, {}, "user")["text"]
        == "We have finished the practice. Well done!"
    )
    # Scores survive a failed feedback call.
    out = llm.roleplay_feedback(_SCENE, _EVAL, "user")
    assert (
        out["text"]
        == "We have finished the practice. Well done! Your scores: Answers clearly, 4 out of 5."
    )
    assert llm.roleplay_reply(_SCENE, []) == "Go on, I'm listening."
